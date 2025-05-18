# db.py
import os
import sqlite3
from typing import List
from models import Card

DB_PATH = "contacts.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT,
                company         TEXT,
                email           TEXT UNIQUE,
                phone           TEXT,
                department      TEXT,
                job_title       TEXT,
                qualification   TEXT,
                company_address TEXT,
                company_url     TEXT,
                company_phone   TEXT,
                company_fax     TEXT
            );
        """)

def exists(email: str) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        return con.execute("SELECT 1 FROM contacts WHERE email=?", (email,)).fetchone() is not None

def save_cards(cards: List[Card]):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        for c in cards:
            # 安全にフィールド取得
            name = c.get("name", "")
            company = c.get("company", "")
            email = c.get("email", None)
            phone = c.get("phone", "")
            department = c.get("department", "")
            job_title = c.get("job_title", "")
            qualification = c.get("qualification", "")
            company_address = c.get("company_address", "")
            company_url = c.get("company_url", "")
            company_phone = c.get("company_phone", "")
            company_fax = c.get("company_fax", "")
            
            # メールアドレスがない場合は保存しない
            if not email:
                continue
                
            # 重複チェック
            if exists(email):
                cur.execute("""UPDATE contacts
                           SET name=?, company=?, phone=?, department=?, 
                               job_title=?, qualification=?, company_address=?,
                               company_url=?, company_phone=?, company_fax=?
                           WHERE email=?""",
                        (name, company, phone, department, job_title, qualification,
                         company_address, company_url, company_phone, company_fax, email))
            else:
                cur.execute("""INSERT INTO contacts
                           (name, company, email, phone, department, job_title, qualification,
                            company_address, company_url, company_phone, company_fax)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (name, company, email, phone, department, job_title, qualification,
                         company_address, company_url, company_phone, company_fax))
        con.commit()

def get_all_contacts():
    with sqlite3.connect(DB_PATH) as con:
        return con.execute("""
            SELECT name, company, email, phone, department, job_title, 
                   qualification, company_address, company_url, company_phone, company_fax 
            FROM contacts
        """).fetchall()
