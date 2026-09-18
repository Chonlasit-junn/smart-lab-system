from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from database import get_db
from routers.users import get_current_user  # import มาจากไฟล์ users.py
import models, schemas

router = APIRouter()

# 1. User ส่ง ticket — user_id ดึงจาก token ไม่ใช่จาก body
@router.post("/tickets", response_model=schemas.TicketResponse)
def create_ticket(
    ticket: schemas.TicketCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_ticket = models.Ticket(
        user_id=current_user.id,
        subject=ticket.subject,
        message=ticket.message,
        status="open"
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return new_ticket

# 2. Admin ดึงทั้งหมด (ยังคงเดิม — แนะนำเพิ่ม admin-only check ในอนาคต)
@router.get("/tickets")
def get_tickets(db: Session = Depends(get_db)):
    tickets = db.query(models.Ticket)\
                .options(joinedload(models.Ticket.user))\
                .order_by(models.Ticket.created_at.desc())\
                .all()
    return {"data": tickets}

# 3. Admin อัปเดตสถานะ
@router.patch("/admin/tickets/{ticket_id}")
def update_ticket_status(
    ticket_id: int,
    status_update: schemas.TicketUpdateStatus,
    db: Session = Depends(get_db)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket.status = status_update.status
    db.commit()
    db.refresh(ticket)
    return {"message": "Ticket status updated successfully", "data": ticket}

# 4. User ดู ticket ของตัวเอง — ดึงจาก token เท่านั้น ห้ามส่ง user_id มาเลือกเอง
@router.get("/tickets/me")
def get_my_tickets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tickets = db.query(models.Ticket)\
                .filter(models.Ticket.user_id == current_user.id)\
                .order_by(models.Ticket.created_at.desc())\
                .all()
    return {"data": tickets}