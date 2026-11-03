from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from routers.users import get_current_user
import models, schemas

router = APIRouter()
ALLOWED_TICKET_STATUSES = {"open", "in_progress", "closed"}
TICKET_REPLY_STATUS_TO_TICKET_STATUS = {
    "received": "open",
    "in_progress": "in_progress",
    "resolved": "closed",
}


def _require_admin(current_user: models.User, db: Session) -> None:
    is_admin = db.query(models.Role.id).join(
        models.UserRole,
        models.UserRole.role_id == models.Role.id,
    ).filter(
        models.UserRole.user_id == current_user.id,
        models.Role.name == "admin",
    ).first() is not None
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")


def _serialize_replies(db: Session, ticket_ids: list[int]) -> dict[int, list[dict]]:
    if not ticket_ids:
        return {}
    replies = db.query(models.TicketReply).filter(
        models.TicketReply.ticket_id.in_(ticket_ids),
    ).order_by(
        models.TicketReply.created_at.asc(),
        models.TicketReply.id.asc(),
    ).all()
    by_ticket: dict[int, list[dict]] = {ticket_id: [] for ticket_id in ticket_ids}
    for reply in replies:
        by_ticket[reply.ticket_id].append({
            "id": reply.id,
            "ticket_id": reply.ticket_id,
            "admin_id": reply.admin_id,
            "responder_name": reply.responder_name,
            "message": reply.message,
            "status": reply.status,
            "is_resolved": reply.is_resolved,
            "created_at": reply.created_at,
        })
    return by_ticket


def _serialize_ticket(ticket: models.Ticket, replies: list[dict], user_name: str | None = None) -> dict:
    data = {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "subject": ticket.subject,
        "message": ticket.message,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "replies": replies,
    }
    if user_name is not None:
        data["user_name"] = user_name
    return data


# User ส่ง Ticket โดยผูกเจ้าของจาก access token เท่านั้น
@router.post("/tickets", response_model=schemas.TicketResponse)
def create_ticket(
    ticket: schemas.TicketCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subject = ticket.subject.strip()
    message = ticket.message.strip()
    if not subject or not message:
        raise HTTPException(status_code=422, detail="Subject and message are required.")

    new_ticket = models.Ticket(
        user_id=current_user.id,
        subject=subject,
        message=message,
        status="open",
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return new_ticket


# Admin ดึงรายการ Ticket ทั้งหมด
@router.get("/tickets")
def get_tickets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _require_admin(current_user, db)
    page_number = page if isinstance(page, int) else 1
    page_limit = page_size if isinstance(page_size, int) else 20
    total = db.query(models.Ticket).order_by(None).count()
    ticket_rows = db.query(
        models.Ticket,
        models.User.first_name,
        models.User.last_name,
    ).outerjoin(
        models.User,
        models.User.id == models.Ticket.user_id,
    ).order_by(
        models.Ticket.created_at.desc(),
        models.Ticket.id.desc(),
    ).offset((page_number - 1) * page_limit).limit(page_limit).all()
    tickets = []
    for ticket, first_name, last_name in ticket_rows:
        user_name = " ".join(
            part for part in (first_name, last_name) if part
        ) or None
        tickets.append((ticket, user_name))
    replies_by_ticket = _serialize_replies(db, [ticket.id for ticket, _ in tickets])
    return {
        "data": [
            _serialize_ticket(ticket, replies_by_ticket.get(ticket.id, []), user_name)
            for ticket, user_name in tickets
        ],
        "page": page_number,
        "page_size": page_limit,
        "total": total,
        "has_more": page_number * page_limit < total,
    }


# User ดูเฉพาะ Ticket ของตัวเอง
@router.get("/tickets/me")
def get_my_tickets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    page_number = page if isinstance(page, int) else 1
    page_limit = page_size if isinstance(page_size, int) else 20
    query = db.query(models.Ticket).filter(
        models.Ticket.user_id == current_user.id,
    )
    total = query.order_by(None).count()
    tickets = query.order_by(
        models.Ticket.created_at.desc(),
        models.Ticket.id.desc(),
    ).offset((page_number - 1) * page_limit).limit(page_limit).all()
    replies_by_ticket = _serialize_replies(db, [ticket.id for ticket in tickets])
    return {
        "data": [
            _serialize_ticket(ticket, replies_by_ticket.get(ticket.id, []))
            for ticket in tickets
        ],
        "page": page_number,
        "page_size": page_limit,
        "total": total,
        "has_more": page_number * page_limit < total,
    }


# Admin อัปเดตสถานะ Ticket
@router.patch("/admin/tickets/{ticket_id}")
def update_ticket_status(
    ticket_id: int,
    status_update: schemas.TicketUpdateStatus,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user, db)
    if status_update.status not in ALLOWED_TICKET_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid ticket status.")

    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = status_update.status
    db.commit()
    db.refresh(ticket)

    return {"message": "Ticket status updated successfully", "data": ticket}


@router.post("/admin/tickets/{ticket_id}/replies")
def create_ticket_reply(
    ticket_id: int,
    reply_data: schemas.TicketReplyCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user, db)
    message = reply_data.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Reply message is required.")
    reply_status = reply_data.status
    if reply_status is None:
        reply_status = "resolved" if reply_data.is_resolved else "in_progress"
    if reply_status not in TICKET_REPLY_STATUS_TO_TICKET_STATUS:
        raise HTTPException(status_code=422, detail="Invalid ticket reply status.")

    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    responder_name = " ".join(
        part for part in (current_user.first_name, current_user.last_name) if part
    ).strip() or current_user.email
    reply = models.TicketReply(
        ticket_id=ticket.id,
        admin_id=current_user.id,
        responder_name=responder_name,
        message=message,
        status=reply_status,
        is_resolved=reply_status == "resolved",
    )
    ticket.status = TICKET_REPLY_STATUS_TO_TICKET_STATUS[reply_status]
    db.add(reply)
    db.commit()
    db.refresh(reply)

    return {
        "message": "Ticket reply sent successfully",
        "data": {
            "id": reply.id,
            "ticket_id": reply.ticket_id,
            "admin_id": reply.admin_id,
            "responder_name": reply.responder_name,
            "message": reply.message,
            "status": reply.status,
            "is_resolved": reply.is_resolved,
            "created_at": reply.created_at,
        },
    }
