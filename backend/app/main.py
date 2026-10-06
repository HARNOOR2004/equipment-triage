from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import get_db, engine, Base
from app import models  # noqa: F401  (tables register hone ke liye)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Equipment Triage Assistant")

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True, "db": "connected"}