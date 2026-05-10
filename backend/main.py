from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import models
from database import engine, Base
from routers import auth, users, labs, agent, gatekeeper, admin, blacklist

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Lab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(labs.router)
app.include_router(agent.router)
app.include_router(gatekeeper.router)
app.include_router(admin.router)
app.include_router(blacklist.router)


@app.get("/")
def root():
    return {"message": "Welcome to Smart Lab API", "status": "Online"}