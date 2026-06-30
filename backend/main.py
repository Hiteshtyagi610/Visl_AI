"""
Visl AI Labs — Candidate Screening Platform
Main FastAPI application: wires together upload, scoring, GitHub analysis,
email automation, and Google Calendar scheduling into one workflow.
"""

import os
import shutil
import sqlite3
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from db import init_db, get_conn, clear_session
from ingest import ingest_candidates_csv, ingest_test_results_csv
from resume_processor import process_all_resumes
from github_analyzer import analyze_all_github_profiles
from scorer import score_all_candidates
from emailer import send_test_links_to_shortlisted
from calendar_integration import schedule_interview_for_candidate, get_auth_url, handle_oauth_callback

app = FastAPI(title="Visl AI Candidate Screening Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
RESUME_DIR = os.path.join(UPLOAD_DIR, "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)

init_db()


# ---------------------------------------------------------------------------
# 1. Candidate dataset upload
# ---------------------------------------------------------------------------
@app.post("/api/upload-candidates")
async def upload_candidates(file: UploadFile = File(...)):
    """Recruiter uploads a CSV of candidate info. Stored fresh each run."""

    clear_session()

    # Save uploaded CSV
    path = os.path.join(UPLOAD_DIR, "candidates.csv")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Import fresh candidates
    count = ingest_candidates_csv(path)

    return {
        "status": "ok",
        "candidates_loaded": count
    }


# ---------------------------------------------------------------------------
# 2. Job description input
# ---------------------------------------------------------------------------
@app.post("/api/job-description")
async def set_job_description(jd_text: str = Form(...)):
    conn = get_conn()
    conn.execute("DELETE FROM job_description")
    conn.execute("INSERT INTO job_description (text) VALUES (?)", (jd_text,))
    conn.commit()
    conn.close()
    return {"status": "ok", "length": len(jd_text)}


# ---------------------------------------------------------------------------
# 3. Resume download + processing
# ---------------------------------------------------------------------------
@app.post("/api/process-resumes")
async def process_resumes():
    """Downloads resumes from stored Drive links and extracts text/skills."""
    result = process_all_resumes(RESUME_DIR)
    return {"status": "ok", "processed": result}


# ---------------------------------------------------------------------------
# 4. GitHub analysis
# ---------------------------------------------------------------------------
@app.post("/api/analyze-github")
async def analyze_github():
    result = analyze_all_github_profiles()
    return {"status": "ok", "analyzed": result}


# ---------------------------------------------------------------------------
# 5. Scoring + ranking (the AI evaluation core)
# ---------------------------------------------------------------------------
@app.post("/api/score-candidates")
async def score_candidates():
    result = score_all_candidates()
    return {"status": "ok", "scored": result}


@app.get("/api/candidates")
async def list_candidates():
    conn = get_conn()
    rows = conn.execute(
        """SELECT s_no, name, email, college, branch, cgpa, github, resume,
                  jd_score, github_score, cgpa_score, test_score, final_score,
                  score_breakdown, status, test_la, test_code
           FROM candidates ORDER BY final_score DESC"""
    ).fetchall()
    conn.close()
    cols = ["s_no", "name", "email", "college", "branch", "cgpa", "github", "resume",
            "jd_score", "github_score", "cgpa_score", "test_score", "final_score",
            "score_breakdown", "status", "test_la", "test_code"]
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# 6. Shortlist + send test links
# ---------------------------------------------------------------------------
@app.post("/api/shortlist-and-email")
async def shortlist_and_email(top_n: int = Form(5)):
    result = send_test_links_to_shortlisted(top_n)
    return {"status": "ok", "emailed": result}


# ---------------------------------------------------------------------------
# 7. Test result upload
# ---------------------------------------------------------------------------
@app.post("/api/upload-test-results")
async def upload_test_results(file: UploadFile = File(...)):
    path = os.path.join(UPLOAD_DIR, "test_results.csv")
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    count = ingest_test_results_csv(path)
    return {"status": "ok", "results_loaded": count}


# ---------------------------------------------------------------------------
# 8. Final shortlist based on test performance
# ---------------------------------------------------------------------------
@app.post("/api/finalize-shortlist")
async def finalize_shortlist(test_la_min: int = Form(50), test_code_min: int = Form(60)):
    conn = get_conn()
    conn.execute(
        """UPDATE candidates SET status = 'interview_ready'
           WHERE status = 'test_sent' AND test_la >= ? AND test_code >= ?""",
        (test_la_min, test_code_min),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT name, email, test_la, test_code FROM candidates WHERE status='interview_ready'"
    ).fetchall()
    conn.close()
    return {"status": "ok", "qualified": [dict(zip(["name", "email", "test_la", "test_code"], r)) for r in rows]}


# ---------------------------------------------------------------------------
# 9 & 10. Google Calendar OAuth + interview scheduling with Meet links
# ---------------------------------------------------------------------------
@app.get("/api/google/auth-url")
async def google_auth_url():
    return {"auth_url": get_auth_url()}


@app.get("/api/google/oauth2callback")
async def google_oauth_callback(code: str):
    print("========== CALLBACK HIT ==========")
    print("CODE RECEIVED:", code[:20])

    try:
        handle_oauth_callback(code)
        print("TOKEN SAVED SUCCESSFULLY")
        return {"status": "connected"}
    except Exception as e:
        print("CALLBACK FAILED:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/schedule-interviews")
async def schedule_interviews(start_hour: int = Form(11)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT s_no, name, email FROM candidates WHERE status='interview_ready'"
    ).fetchall()
    conn.close()

    results = []
    for i, (s_no, name, email) in enumerate(rows):
        res = schedule_interview_for_candidate(s_no, name, email, slot_offset=i, start_hour=start_hour)
        results.append(res)
    return {"status": "ok", "scheduled": results}


# ---------------------------------------------------------------------------
# Frontend (single dashboard page)
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="../frontend"), name="static")


@app.get("/")
async def root():
    return FileResponse("../frontend/index.html")
