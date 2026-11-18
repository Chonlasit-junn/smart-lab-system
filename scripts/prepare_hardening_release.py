"""Prepare a scoped release snapshot without changing working files or Git index."""
import ast
import difflib
import io
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "build" / "hardening-release-20261028"
TREE = RELEASE / "tree"
TREE.mkdir(parents=True, exist_ok=False)
full = [
    "backend/Dockerfile", "backend/access_policy.py", "backend/login_security.py",
    "backend/security_config.py", "backend/face_service.py", "backend/main.py",
    "backend/utils.py", "backend/routers/agent.py", "backend/routers/auth.py",
    "backend/routers/gatekeeper.py", "backend/routers/labs.py",
    "backend/routers/password_reset.py", "backend/routers/points.py",
    "backend/routers/users.py", "backend/tests/test_access_policy.py",
    "backend/tests/test_login_security.py", "backend/tests/test_security_config.py",
    "backend/tests/test_auth_email_normalization.py",
    "backend/tests/test_device_registration.py", "backend/tests/test_labs_booking.py",
    "backend/tests/test_password_reset.py", "backend/tests/test_password_reset_postgres.py",
    "backend/tests/test_points.py", "backend/tests/test_registration_otp.py",
    "frontend/src/pages/Login.jsx", "frontend/src/utils/loginFeedback.js",
    "frontend/src/utils/registrationOtp.js", "frontend/src/utils/locales.js",
    "frontend/tests/loginFeedback.test.js", "frontend/tests/registrationOtp.test.js",
    "docs/ACCESS_LOGIN_REGISTER_HARDENING.md",
]
mixed = ["backend/tests/test_agent_telemetry.py", "smart-lab-agent/agent.pyw",
         "smart-lab-agent/tests/test_agent_http_policy_grace.py"]

def head(path):
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT).decode("utf-8")

def method(source, cls, name):
    c = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == cls)
    n = next(n for n in c.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    lines = source.splitlines(keepends=True)
    return n, "".join(lines[n.lineno - 1:n.end_lineno])

archive = subprocess.check_output(["git", "archive", "--format=zip", "HEAD", "backend", "frontend", "smart-lab-agent", "docs"], cwd=ROOT)
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    for item in z.infolist():
        target = (TREE / item.filename).resolve()
        assert target.is_relative_to(TREE.resolve())
    z.extractall(TREE)
for path in full:
    target = TREE / path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / path, target)

path = mixed[0]
base = head(path)
working = (ROOT / path).read_text(encoding="utf-8")
_, replacement = method(working, "AgentTelemetryTests", "test_legacy_session_telemetry_requires_owner_and_registered_device")
_, original = method(base, "AgentTelemetryTests", "test_legacy_session_telemetry_requires_owner_and_registered_device")
assert base.count(original) == 1
(TREE / path).write_text(base.replace(original, replacement), encoding="utf-8", newline="\n")

path = mixed[1]
base = head(path)
working = (ROOT / path).read_text(encoding="utf-8")
for cls, name in [("LoginOverlay", "_authenticate_and_start_session"),
                  ("LoginOverlay", "_handle_login_result"),
                  ("SmartLabAgent", "_handle_heartbeat_result")]:
    _, replacement = method(working, cls, name)
    _, original = method(base, cls, name)
    assert base.count(original) == 1
    base = base.replace(original, replacement)
(TREE / path).write_text(base, encoding="utf-8", newline="\n")

path = mixed[2]
base = head(path)
working = (ROOT / path).read_text(encoding="utf-8")
additions = []
for name in ["test_login_throttle_and_inactive_account_do_not_attempt_session_start",
             "test_ban_after_login_is_explained_and_session_not_confirmed",
             "test_revoked_device_heartbeat_returns_to_login",
             "test_booking_required_response_is_explained_to_agent_user"]:
    assert f"def {name}(" not in base
    additions.append(method(working, "AgentHttpTests", name)[1])
marker = "class AgentHttpTests(unittest.TestCase):\n"
assert base.count(marker) == 1
base = base.replace(marker, marker + "\n".join(s.rstrip() + "\n" for s in additions) + "\n")
(TREE / path).write_text(base, encoding="utf-8", newline="\n")

patch = ""
for path in mixed:
    patch += "".join(difflib.unified_diff(head(path).splitlines(keepends=True),
        (TREE / path).read_text(encoding="utf-8").splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}"))
(RELEASE / "selected.patch").write_text(patch, encoding="utf-8", newline="\n")
(RELEASE / "manifest.json").write_text(json.dumps({"full": full, "mixed": mixed}, indent=2), encoding="utf-8")
print(json.dumps({"snapshot": str(TREE), "full_files": len(full), "partial_files": len(mixed)}))
