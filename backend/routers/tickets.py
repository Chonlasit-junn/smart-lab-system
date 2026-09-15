from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from routers.users import get_current_user
import models, schemas

router = APIRouter()
ALLOWED_TICKET_STATUSES = {"open", "in_progress", "closed"}


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
):
    _require_admin(current_user, db)
    tickets = db.query(models.Ticket).order_by(models.Ticket.created_at.desc()).all()
    return {"data": tickets}


# User ดูเฉพาะ Ticket ของตัวเอง
@router.get("/tickets/me")
def get_my_tickets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tickets = db.query(models.Ticket).filter(
        models.Ticket.user_id == current_user.id,
    ).order_by(models.Ticket.created_at.desc()).all()
    return {"data": tickets}


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
