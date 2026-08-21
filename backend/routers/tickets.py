print("===== TICKETS ROUTER IS LOADING =====") # เพิ่มบรรทัดนี้
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db # ฟังก์ชันต่อ Database ของคุณ
import models, schemas

router = APIRouter()

# 1. API สำหรับ User กดส่ง Ticket (POST)
@router.post("/tickets", response_model=schemas.TicketResponse)
def create_ticket(ticket: schemas.TicketCreate, db: Session = Depends(get_db)):
    new_ticket = models.Ticket(
        user_id=ticket.user_id,
        subject=ticket.subject,
        message=ticket.message,
        status="open"
    )
    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)
    return new_ticket

# 2. API สำหรับ Admin ดึงรายการ Ticket ทั้งหมด (GET)
@router.get("/tickets")
def get_tickets(db: Session = Depends(get_db)):
    # เรียงลำดับจากตั๋วที่สร้างล่าสุดขึ้นก่อน
    tickets = db.query(models.Ticket).order_by(models.Ticket.created_at.desc()).all()
    
    # ห่อด้วย {"data": ...} เพื่อให้ตรงกับโค้ด React (ticketsRes.data?.data)
    return {"data": tickets}

# 3. API สำหรับ Admin อัปเดตสถานะ Ticket เช่น ปิดงาน (PATCH)
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