# app/db/test_connection.py
from sqlalchemy import text
from app.db.session import engine

with engine.connect() as conn:
    version = conn.execute(text("select version();")).scalar()
    print("Connected to:", version)