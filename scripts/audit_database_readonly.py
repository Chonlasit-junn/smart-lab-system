"""Read-only PostgreSQL audit. Outputs metadata and counts, never row contents.

Run from the repository root with backend/venv/Scripts/python.exe -B.
Does not import the application, create tables, run migrations or write reports.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


ROOT = Path(__file__).resolve().parents[1]
OPTIONS = (
    "-c default_transaction_read_only=on -c statement_timeout=8000 "
    "-c lock_timeout=1000 -c idle_in_transaction_session_timeout=15000"
)

METADATA = {
    "session": """SELECT current_setting('server_version') AS server_version,
        current_setting('transaction_read_only') AS read_only,
        current_setting('transaction_isolation') AS isolation,
        current_setting('TimeZone') AS timezone, now() AS snapshot_at,
        r.rolsuper AS superuser, r.rolbypassrls AS bypass_rls
        FROM pg_roles r WHERE r.rolname = current_user""",
    "tables": """SELECT c.relname AS table_name, c.relrowsecurity AS rls,
        c.relforcerowsecurity AS force_rls,
        c.reltuples::bigint AS estimated_rows,
        pg_total_relation_size(c.oid) AS total_bytes
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p')
        ORDER BY c.relname""",
    "columns": """SELECT table_name, column_name, data_type, is_nullable,
        is_identity, column_default IS NOT NULL AS has_default
        FROM information_schema.columns WHERE table_schema='public'
        ORDER BY table_name, ordinal_position""",
    "constraints": """SELECT t.relname AS table_name, c.conname AS name,
        c.contype AS type, c.convalidated AS validated,
        pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='public' ORDER BY t.relname,c.conname""",
    "indexes": """SELECT t.relname AS table_name, i.relname AS name,
        x.indisunique AS is_unique, x.indisvalid AS is_valid,
        pg_get_indexdef(i.oid) AS definition,
        pg_get_expr(x.indpred,x.indrelid) AS predicate
        FROM pg_index x JOIN pg_class t ON t.oid=x.indrelid
        JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='public' ORDER BY t.relname,i.relname""",
    "fk_types": """SELECT c.conname AS name, t.relname AS table_name,
        a.attname AS column_name, format_type(a.atttypid,a.atttypmod) AS type,
        p.relname AS referenced_table, b.attname AS referenced_column,
        format_type(b.atttypid,b.atttypmod) AS referenced_type,
        a.atttypid <> b.atttypid AS type_mismatch
        FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class p ON p.oid=c.confrelid
        CROSS JOIN LATERAL unnest(c.conkey,c.confkey) AS k(child_key,parent_key)
        JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.child_key
        JOIN pg_attribute b ON b.attrelid=p.oid AND b.attnum=k.parent_key
        WHERE c.contype='f' AND n.nspname='public'
        ORDER BY t.relname,c.conname""",
    "policies": """SELECT tablename AS table_name, policyname, roles, cmd,
        permissive, qual IS NOT NULL AS has_using,
        with_check IS NOT NULL AS has_check FROM pg_policies
        WHERE schemaname='public' ORDER BY tablename,policyname""",
    "api_grants": """SELECT t.relname AS table_name, r.rolname AS role,
        has_schema_privilege(r.oid,n.oid,'USAGE') AS schema_usage,
        has_table_privilege(r.oid,t.oid,'SELECT') AS can_select,
        has_table_privilege(r.oid,t.oid,'INSERT') AS can_insert,
        has_table_privilege(r.oid,t.oid,'UPDATE') AS can_update,
        has_table_privilege(r.oid,t.oid,'DELETE') AS can_delete
        FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
        CROSS JOIN pg_roles r WHERE n.nspname='public'
        AND t.relkind IN ('r','p') AND r.rolname IN ('anon','authenticated')
        ORDER BY t.relname,r.rolname""",
    "triggers": """SELECT c.relname AS table_name, t.tgname AS name,
        t.tgenabled AS enabled, p.proname AS function_name
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid
        WHERE n.nspname='public' AND NOT t.tgisinternal
        ORDER BY c.relname,t.tgname""",
}

# Predicates are fixed SQL, not input. Only aggregate counts leave the DB.
CHECKS = {
    "users": {
        "missing_name": "first_name IS NULL OR btrim(first_name)='' OR last_name IS NULL OR btrim(last_name)=''",
        "noncanonical_email": "email IS NULL OR email<>lower(btrim(email)) OR btrim(email)=''",
    },
    "students": {"missing_owner": "user_id IS NULL"},
    "user_passport": {"missing_owner": "user_id IS NULL"},
    "labs": {"invalid_capacity": "capacity IS NULL OR capacity<0", "invalid_status": "status IS NULL OR status NOT IN ('active','inactive','maintenance')"},
    "bookings": {
        "missing_owner": "user_id IS NULL",
        "invalid_participants": "total_participants IS NULL OR total_participants<=0",
        "invalid_time_order": "start_time>=end_time",
        "invalid_status": "status IS NULL OR status NOT IN ('reserved','attended','completed','cancelled','no_show')",
    },
    "lab_access_logs": {
        "invalid_time_order": "entry_time IS NULL OR exit_time<entry_time",
        "inconsistent_active_state": "(session_status='active' AND exit_time IS NOT NULL) OR (session_status IN ('completed','abandoned') AND exit_time IS NULL)",
        "future_entry": "entry_time>now()+interval '5 minutes'",
    },
    "program_usage_logs": {
        "missing_usage_times": "usage_start_time IS NULL OR usage_end_time IS NULL",
        "invalid_time_order": "usage_end_time<usage_start_time",
        "invalid_duration": "duration_seconds IS NULL OR duration_seconds<0",
    },
    "class_schedules": {
        "invalid_time_order": "start_time IS NULL OR end_time IS NULL OR start_time>=end_time",
        "invalid_date_order": "valid_from IS NULL OR valid_until IS NULL OR valid_from>valid_until",
    },
    "user_points": {"invalid_points": "points IS NULL OR points NOT BETWEEN 0 AND 100"},
    "user_daily_scores": {"invalid_score": "score IS NULL OR score NOT BETWEEN 0 AND 100"},
    "point_requests": {"invalid_amount": "requested_points IS NULL OR requested_points NOT BETWEEN 1 AND 100"},
    "user_otps": {
        "missing_created_at": "created_at IS NULL",
        "older_than_proposed_10_minute_ttl": "created_at<now()-interval '10 minutes'",
        "invalid_code_format": "otp_code IS NULL OR otp_code !~ '^[0-9]{6}$'",
    },
    "lab_device_enrollments": {"expired_unused": "used_at IS NULL AND expires_at<now()"},
    "usage_violations": {"future_detection": "detected_at>now()+interval '5 minutes'"},
}

DUPLICATES = {
    "email_canonical": "SELECT lower(btrim(email)) FROM public.users GROUP BY lower(btrim(email)) HAVING count(*)>1",
    "student_profile": "SELECT user_id FROM public.students WHERE user_id IS NOT NULL GROUP BY user_id HAVING count(*)>1",
    "guest_profile": "SELECT user_id FROM public.user_passport WHERE user_id IS NOT NULL GROUP BY user_id HAVING count(*)>1",
    "user_booking_slot": "SELECT user_id,booking_date,start_time FROM public.bookings WHERE user_id IS NOT NULL AND status IN ('reserved','attended','completed') GROUP BY user_id,booking_date,start_time HAVING count(*)>1",
    "active_user_session": "SELECT user_id FROM public.lab_access_logs WHERE session_status='active' AND exit_time IS NULL GROUP BY user_id HAVING count(*)>1",
    "active_device_session": "SELECT lab_device_id FROM public.lab_access_logs WHERE session_status='active' AND exit_time IS NULL AND lab_device_id IS NOT NULL GROUP BY lab_device_id HAVING count(*)>1",
    "pending_point_request": "SELECT user_id FROM public.point_requests WHERE status='pending' GROUP BY user_id HAVING count(*)>1",
}
for _table in ("program_usage_logs", "usage_violations", "point_logs"):
    DUPLICATES[_table + "_event"] = (
        f"SELECT event_id FROM public.{_table} WHERE event_id IS NOT NULL "
        "AND btrim(event_id)<>'' GROUP BY event_id HAVING count(*)>1"
    )


def error_summary(exc):
    """Do not emit exception strings: driver errors can contain connection URLs."""
    original = getattr(exc, "orig", exc)
    detail = str(original).lower()
    reason = "query_or_connection_error"
    for fragment, label in (
        ("could not translate host", "dns_resolution_failed"),
        ("password authentication failed", "authentication_failed"),
        ("connection timed out", "connection_timeout"),
        ("network is unreachable", "network_unreachable"),
        ("connection refused", "connection_refused"),
        ("certificate verify failed", "tls_verification_failed"),
    ):
        if fragment in detail:
            reason = label
            break
    return {"error_type": type(exc).__name__, "sqlstate": getattr(original, "pgcode", None), "reason": reason}


def audit(engine):
    report = {"metadata": {}, "checks": {}, "duplicates": {}, "errors": {}}
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ", postgresql_readonly=True,
    ) as connection:
        transaction = connection.begin()
        try:
            readonly = connection.execute(text("SHOW transaction_read_only")).scalar_one()
            if readonly != "on":
                raise RuntimeError("Read-only guard failed")

            def query(label, statement):
                savepoint = connection.begin_nested()
                try:
                    rows = [dict(row) for row in connection.execute(text(statement)).mappings()]
                    savepoint.commit()
                    return rows
                except Exception as exc:
                    savepoint.rollback()
                    report["errors"][label] = error_summary(exc)
                    return None

            for name, statement in METADATA.items():
                report["metadata"][name] = query(name, statement)
            tables = {row["table_name"] for row in report["metadata"].get("tables") or []}
            # Only application tables in the fixed allowlist are scanned.
            for table, predicates in CHECKS.items():
                if table not in tables:
                    report["errors"][table] = {"reason": "table_not_visible_or_missing"}
                    continue
                counts = ["count(*) AS total_rows"] + [
                    f'count(*) FILTER (WHERE {predicate}) AS "{name}"'
                    for name, predicate in predicates.items()
                ]
                report["checks"][table] = query(table, f"SELECT {', '.join(counts)} FROM public.{table}")
            for name, statement in DUPLICATES.items():
                report["duplicates"][name] = query(name, f"SELECT count(*) AS duplicate_groups FROM ({statement}) AS duplicates")
            report["read_only_at_end"] = connection.execute(text("SHOW transaction_read_only")).scalar_one()
        finally:
            transaction.rollback()
    return report


def main():
    load_dotenv(ROOT / "backend" / ".env", override=False)
    configured = os.getenv("SQLALCHEMY_DATABASE_URL")
    if not configured:
        print(json.dumps({"status": "failed", "reason": "database_configuration_missing"}))
        return 1
    engine = None
    try:
        url = make_url(configured)
        if url.get_backend_name() != "postgresql":
            raise ValueError("PostgreSQL required")
        engine = create_engine(
            url, poolclass=NullPool, hide_parameters=True,
            connect_args={"connect_timeout": 10, "options": OPTIONS},
        )
        result = audit(engine)
        result["status"] = "complete" if not result["errors"] else "partial"
        print(json.dumps(result, default=str, ensure_ascii=True))
        return 0 if result["status"] == "complete" else 2
    except Exception as exc:
        print(json.dumps({"status": "failed", **error_summary(exc)}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
