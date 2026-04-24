from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# แก้ไข Username ให้มี Project ID ต่อท้าย (เพื่อใช้งานกับ Pooler พอร์ต 6543)
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.lilvtjyupffpilyossfv:CDic4WyMcKtFKZOf@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()