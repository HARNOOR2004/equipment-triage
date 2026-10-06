import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import get_db, engine, Base
from app import models  

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Equipment Triage Assistant")

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True, "db": "connected"}