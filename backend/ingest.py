"""
Ingests recruiter-uploaded CSVs into the database.
Handles both the candidate dataset and the test-results dataset, matching
the exact field names specified in the assignment brief.
"""

import csv
from db import get_conn


def _to_float(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def ingest_candidates_csv(path: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            s_no = row.get("s_no") or row.get("S.No") or row.get("S_No")
            if not s_no:
                continue
            c.execute("""
                INSERT INTO candidates
                    (s_no, name, email, college, branch, cgpa,
                     best_ai_project, research_work, github, resume, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'uploaded')
                ON CONFLICT(s_no) DO UPDATE SET
                    name=excluded.name, email=excluded.email,
                    college=excluded.college, branch=excluded.branch,
                    cgpa=excluded.cgpa, best_ai_project=excluded.best_ai_project,
                    research_work=excluded.research_work, github=excluded.github,
                    resume=excluded.resume
            """, (
                int(s_no),
                row.get("name"),
                row.get("email"),
                row.get("college"),
                row.get("branch"),
                _to_float(row.get("cgpa")),
                row.get("best_ai_project"),
                row.get("research_work"),
                row.get("github"),
                row.get("resume"),
            ))
            count += 1
    conn.commit()
    conn.close()
    return count


def ingest_test_results_csv(path: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            s_no = row.get("s_no")
            if not s_no:
                continue
            c.execute("""
                UPDATE candidates
                SET test_la = ?, test_code = ?, status = 'test_sent'
                WHERE s_no = ?
            """, (
                _to_float(row.get("test_la")),
                _to_float(row.get("test_code")),
                int(s_no),
            ))
            count += 1
    conn.commit()
    conn.close()
    return count
