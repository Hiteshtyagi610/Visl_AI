"""
SQLite database layer. Using SQLite (not Postgres) deliberately: zero setup,
file-based, perfectly fine for an assignment-scale dataset, and the schema
below is written so swapping to Postgres later is a one-line connection
string change (see architecture.md, 'Scalability considerations').
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "screening.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    return conn

def clear_session():
    conn = get_conn()
    c = conn.cursor()

    # Clear previous screening data
    c.execute("DELETE FROM candidates")
    c.execute("DELETE FROM job_description")
    c.execute("DELETE FROM interviews")

    # Reset AUTOINCREMENT tables
    c.execute("DELETE FROM sqlite_sequence WHERE name='job_description'")
    c.execute("DELETE FROM sqlite_sequence WHERE name='interviews'")

    conn.commit()
    conn.close()


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS candidates (
        s_no INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT,
        college TEXT,
        branch TEXT,
        cgpa REAL,
        best_ai_project TEXT,
        research_work TEXT,
        github TEXT,
        resume TEXT,
        resume_text TEXT,
        resume_skills TEXT,
        github_score REAL,
        github_breakdown TEXT,
        jd_score REAL,
        cgpa_score REAL,
        test_score REAL,
        final_score REAL,
        score_breakdown TEXT,
        status TEXT DEFAULT 'uploaded',
        test_la REAL,
        test_code REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS job_description (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS google_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_json TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS interviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        s_no INTEGER,
        name TEXT,
        email TEXT,
        meet_link TEXT,
        event_id TEXT,
        scheduled_time TEXT
    )
    """)

    conn.commit()
    conn.close()
