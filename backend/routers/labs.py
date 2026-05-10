from datetime import datetime, timedelta, time, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from urllib.parse import unquote

import models, schemas
from database import get_db

router = APIRouter(tags=["Labs & Bookings"])

# slot 1-4 maps to fixed time windows for the whole system
VALID_TIME_SLOTS = {
    1: {"start": time(8, 40),  "end": time(11, 0)},
    2: {"start": time(12, 0),  "end": time(14, 20)},
    3: {"start": time(14, 30), "end": time(16, 50)},
    4: {"start": time(17, 0),  "end": time(19, 20)},
}


# --- Lab CRUD ---

@router.get("/labs")
def get_all_labs(db: Session = Depends(get_db)):
    return {"data": db.query(models.Lab).all()}


@router.post("/admin/labs")
def create_lab(lab: schemas.LabCreate, db: Session = Depends(get_db)):
    if db.query(models.Lab).filter(models.Lab.code == lab.code).first():
        raise HTTPException(status_code=400, detail="Lab code already exists.")

    new_lab = models.Lab(**lab.dict(), status="active")
    db.add(new_lab)
    db.commit()
    db.refresh(new_lab)
    return {"message": "Lab created successfully.", "lab": new_lab}


@router.put("/admin/labs/{lab_id}")
def update_lab_details(lab_id: int, lab_update: schemas.LabUpdate, db: Session = Depends(get_db)):
    lab = db.query(models.Lab).filter(models.Lab.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found.")

    # only check for code conflict if the code actually changed
    if lab.code != lab_update.code:
        if db.query(models.Lab).filter(models.Lab.code == lab_update.code).first():
            raise HTTPException(status_code=400, detail="Lab code is already in use.")

    lab.name = lab_update.name
    lab.code = lab_update.code
    lab.capacity = lab_update.capacity
    lab.location = lab_update.location
    db.commit()
    return {"message": "Lab updated successfully."}


@router.put("/admin/labs/{lab_id}/status")
def update_lab_status(lab_id: int, status_update: schemas.LabStatusUpdate, db: Session = Depends(get_db)):
    lab = db.query(models.Lab).filter(models.Lab.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found.")

    # ห้ามปิดห้องถ้ายังมีการจองที่ยังไม่ถึงวันใช้งาน
    if status_update.status != "active":
        upcoming = db.query(models.Booking).filter(
            models.Booking.lab_id == lab_id,
            models.Booking.booking_date >= date.today(),
        ).first()
        if upcoming:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot disable this lab — there are upcoming bookings. Please cancel them first."
            )

    lab.status = status_update.status
    db.commit()
    return {"message": f"Lab status updated to '{status_update.status}'."}


@router.put("/admin/labs/{lab_id}/capacity")
def update_lab_capacity(lab_id: int, cap_update: schemas.LabCapacityUpdate, db: Session = Depends(get_db)):
    lab = db.query(models.Lab).filter(models.Lab.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found.")
    lab.capacity = cap_update.capacity
    db.commit()
    return {"message": f"Lab capacity updated to {cap_update.capacity} seats."}


@router.delete("/admin/labs/{lab_id}")
def delete_lab(lab_id: int, db: Session = Depends(get_db)):
    lab = db.query(models.Lab).filter(models.Lab.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found.")

    # ห้ามลบห้องถ้ายังมีการจองที่ยังไม่ถึงวันใช้งาน
    upcoming = db.query(models.Booking).filter(
        models.Booking.lab_id == lab_id,
        models.Booking.booking_date >= date.today(),
    ).first()
    if upcoming:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete this lab — there are upcoming bookings. Please cancel them first."
        )

    # child records don't cascade-delete automatically via query, so clean them up first
    db.query(models.ClassSchedule).filter(models.ClassSchedule.lab_id == lab_id).delete()
    db.query(models.Booking).filter(models.Booking.lab_id == lab_id).delete()
    db.delete(lab)
    db.commit()
    return {"message": "Lab deleted successfully."}


# --- Class Schedules ---

@router.get("/labs/{lab_id}/schedules")
def get_lab_schedules(lab_id: int, semester: str = None, year: str = None, db: Session = Depends(get_db)):
    query = db.query(models.ClassSchedule).filter(models.ClassSchedule.lab_id == lab_id)
    if semester:
        query = query.filter(models.ClassSchedule.semester == semester)
    if year:
        query = query.filter(models.ClassSchedule.academic_year == year)
    return {"data": query.all()}


@router.post("/admin/schedules")
def create_schedule(schedule: schemas.ScheduleCreate, db: Session = Depends(get_db)):
    if schedule.slot_number not in VALID_TIME_SLOTS:
        raise HTTPException(status_code=400, detail="Invalid slot number (must be 1-4).")

    slot_times = VALID_TIME_SLOTS[schedule.slot_number]

    # check for time conflicts within the same lab/day/semester
    conflict = db.query(models.ClassSchedule).filter(
        models.ClassSchedule.lab_id == schedule.lab_id,
        models.ClassSchedule.day_of_week == schedule.day_of_week,
        models.ClassSchedule.start_time == slot_times["start"],
        models.ClassSchedule.semester == schedule.semester,
        models.ClassSchedule.academic_year == schedule.academic_year,
    ).first()
    if conflict:
        raise HTTPException(status_code=400, detail=f"Slot conflicts with existing course {conflict.course_code}.")

    db.add(models.ClassSchedule(
        lab_id=schedule.lab_id,
        course_code=schedule.course_code,
        course_name=schedule.course_name,
        instructor_name=schedule.instructor_name,
        start_time=slot_times["start"],
        end_time=slot_times["end"],
        day_of_week=schedule.day_of_week,
        semester=schedule.semester,
        academic_year=schedule.academic_year,
        valid_from=schedule.valid_from,
        valid_until=schedule.valid_until,
    ))
    db.commit()
    return {"message": "Schedule created successfully."}


@router.delete("/admin/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(models.ClassSchedule).filter(models.ClassSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    db.delete(schedule)
    db.commit()
    return {"message": "Schedule deleted successfully."}


@router.put("/admin/schedules/{schedule_id}")
def update_schedule(schedule_id: int, schedule: schemas.ScheduleCreate, db: Session = Depends(get_db)):
    existing = db.query(models.ClassSchedule).filter(models.ClassSchedule.id == schedule_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found.")

    if schedule.slot_number not in VALID_TIME_SLOTS:
        raise HTTPException(status_code=400, detail="Invalid slot number (must be 1-4).")

    slot_times = VALID_TIME_SLOTS[schedule.slot_number]

    # check conflict but exclude the schedule being edited
    conflict = db.query(models.ClassSchedule).filter(
        models.ClassSchedule.id != schedule_id,
        models.ClassSchedule.lab_id == schedule.lab_id,
        models.ClassSchedule.day_of_week == schedule.day_of_week,
        models.ClassSchedule.start_time == slot_times["start"],
        models.ClassSchedule.semester == schedule.semester,
        models.ClassSchedule.academic_year == schedule.academic_year,
    ).first()
    if conflict:
        raise HTTPException(status_code=400, detail=f"Slot conflicts with existing course {conflict.course_code}.")

    existing.course_code = schedule.course_code
    existing.course_name = schedule.course_name
    existing.instructor_name = schedule.instructor_name
    existing.day_of_week = schedule.day_of_week
    existing.start_time = slot_times["start"]
    existing.end_time = slot_times["end"]
    existing.semester = schedule.semester
    existing.academic_year = schedule.academic_year
    existing.valid_from = schedule.valid_from
    existing.valid_until = schedule.valid_until

    db.commit()
    return {"message": "Schedule updated successfully."}




@router.get("/bookings")
def get_all_bookings(db: Session = Depends(get_db)):
    # used by admin dashboard — eager-load user and lab to avoid N+1
    bookings = (
        db.query(models.Booking)
        .options(joinedload(models.Booking.user), joinedload(models.Booking.lab))
        .order_by(models.Booking.created_at.desc())
        .all()
    )
    return {"data": bookings}


@router.get("/labs/{lab_id}/availability")
def check_availability(lab_id: int, target_date: date, db: Session = Depends(get_db)):
    lab = db.query(models.Lab).filter(models.Lab.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found.")

    # return all slots as disabled if the lab isn't active
    if lab.status != "active":
        return {
            "date": target_date,
            "status": "closed",
            "slots": {s: {"status": "disabled", "remaining_seats": 0} for s in VALID_TIME_SLOTS},
        }

    max_seats = lab.capacity or 0
    day_name = target_date.strftime("%A")

    # find which slots are taken by scheduled classes on this day
    classes = db.query(models.ClassSchedule).filter(
        models.ClassSchedule.lab_id == lab_id,
        models.ClassSchedule.day_of_week == day_name,
        models.ClassSchedule.valid_from <= target_date,
        models.ClassSchedule.valid_until >= target_date,
    ).all()
    class_start_times = {c.start_time for c in classes}

    bookings = db.query(models.Booking).filter(
        models.Booking.lab_id == lab_id,
        models.Booking.booking_date == target_date,
    ).all()

    availability = {}
    for slot, times in VALID_TIME_SLOTS.items():
        if times["start"] in class_start_times:
            availability[slot] = {"status": "class", "remaining_seats": 0}
        else:
            seats_taken = sum(b.total_participants for b in bookings if b.start_time == times["start"])
            remaining = max(0, max_seats - seats_taken)
            availability[slot] = {
                "status": "full" if remaining <= 0 else "available",
                "remaining_seats": remaining,
            }

    return {
        "lab_id": lab_id,
        "date": target_date,
        "day": day_name,
        "total_capacity": max_seats,
        "slots": availability,
    }


@router.post("/bookings")
def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    if booking.slot_number not in VALID_TIME_SLOTS:
        raise HTTPException(status_code=400, detail="Invalid slot number (must be 1-4).")

    slot_times = VALID_TIME_SLOTS[booking.slot_number]
    now = datetime.now()
    booking_start_dt = datetime.combine(booking.booking_date, slot_times["start"])

    if booking_start_dt <= now:
        raise HTTPException(status_code=400, detail="This time slot has already passed.")
    if booking_start_dt < now + timedelta(hours=2):
        raise HTTPException(status_code=400, detail="Must book at least 2 hours in advance.")
    if booking.booking_date > now.date() + timedelta(days=2):
        raise HTTPException(status_code=400, detail="Cannot book more than 2 days in advance.")

    user = db.query(models.User).filter(models.User.email == booking.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    lab = db.query(models.Lab).filter(models.Lab.id == booking.lab_id).first()
    if not lab or lab.status != "active":
        raise HTTPException(status_code=400, detail="Lab is currently closed.")

    # prevent double-booking the same user in the same slot
    duplicate = db.query(models.Booking).filter(
        models.Booking.user_id == user.id,
        models.Booking.booking_date == booking.booking_date,
        models.Booking.start_time == slot_times["start"],
    ).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="You already have a booking in this time slot.")

    # reject if a class is scheduled in this slot
    class_conflict = db.query(models.ClassSchedule).filter(
        models.ClassSchedule.lab_id == booking.lab_id,
        models.ClassSchedule.day_of_week == booking.booking_date.strftime("%A"),
        models.ClassSchedule.start_time == slot_times["start"],
        models.ClassSchedule.valid_from <= booking.booking_date,
        models.ClassSchedule.valid_until >= booking.booking_date,
    ).first()
    if class_conflict:
        raise HTTPException(status_code=400, detail="Slot is reserved for a scheduled class.")

    # check remaining seat capacity
    existing = db.query(models.Booking).filter(
        models.Booking.lab_id == booking.lab_id,
        models.Booking.booking_date == booking.booking_date,
        models.Booking.start_time == slot_times["start"],
    ).all()
    seats_taken = sum(b.total_participants for b in existing)
    seats_left = lab.capacity - seats_taken
    if booking.total_participants > seats_left:
        raise HTTPException(status_code=400, detail=f"Not enough seats. ({seats_left} left)")

    db.add(models.Booking(
        lab_id=booking.lab_id,
        user_id=user.id,
        booking_date=booking.booking_date,
        start_time=slot_times["start"],
        end_time=slot_times["end"],
        purpose=booking.purpose,
        total_participants=booking.total_participants,
    ))
    db.commit()
    return {"message": f"Booking successful for {booking.total_participants} seat(s)."}


@router.get("/bookings/user/{email}")
def get_user_bookings(email: str, db: Session = Depends(get_db)):
    clean_email = unquote(email).strip()
    user = db.query(models.User).filter(models.User.email == clean_email).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{clean_email}' not found.")

    rows = (
        db.query(models.Booking, models.Lab)
        .join(models.Lab, models.Booking.lab_id == models.Lab.id)
        .filter(models.Booking.user_id == user.id)
        .order_by(models.Booking.booking_date.desc(), models.Booking.start_time.desc())
        .all()
    )

    return {
        "data": [
            {
                "id": b.id,
                "lab_code": lab.code,
                "lab_name": lab.name,
                "booking_date": b.booking_date,
                "start_time": b.start_time.strftime("%H:%M"),
                "end_time": b.end_time.strftime("%H:%M"),
                "purpose": b.purpose,
            }
            for b, lab in rows
        ]
    }


@router.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: int, email: str, db: Session = Depends(get_db)):
    clean_email = unquote(email).strip()
    user = db.query(models.User).filter(models.User.email == clean_email).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{clean_email}' not found.")

    booking = db.query(models.Booking).filter(
        models.Booking.id == booking_id,
        models.Booking.user_id == user.id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or unauthorized.")

    db.delete(booking)
    db.commit()
    return {"message": "Booking cancelled successfully."}