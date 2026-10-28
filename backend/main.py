from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from security_config import cors_origins

# Fail closed on invalid production configuration before any database startup.
allowed_origins = cors_origins()

import models
from database import engine, Base
from routers import auth, users, labs, agent, devices, gatekeeper, admin, blacklist, points, tickets, password_reset, reports
from utils import UPLOAD_ROOT

Base.metadata.create_all(
    bind=engine,
    tables=[table for table in Base.metadata.sorted_tables if not table.info.get("manual_migration")],
)

app = FastAPI(title="Smart Lab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After", "Content-Disposition"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")

app.include_router(auth.router)
app.include_router(password_reset.router)
app.include_router(users.router)
app.include_router(labs.router)
app.include_router(agent.router)
app.include_router(devices.router)
app.include_router(gatekeeper.router)
app.include_router(admin.router)
app.include_router(blacklist.router)
app.include_router(points.router)
app.include_router(tickets.router)
app.include_router(reports.router)

@app.get("/")
def root():
    return {"message": "Welcome to Smart Lab API", "status": "Online"}
