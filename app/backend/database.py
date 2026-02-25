from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# SQLite database URL
DATABASE_URL = "sqlite:///./leads.db"

# Create engine
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
