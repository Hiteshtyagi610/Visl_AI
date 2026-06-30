"""
Downloads candidate resumes from Google Drive share links and extracts text.
Google Drive share links look like:
  https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing
We convert these to direct-download URLs and pull the PDF, then extract text
with PyMuPDF (fitz).
"""

import os
import re
import requests
import fitz  # PyMuPDF

from db import get_conn

DRIVE_ID_PATTERN = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")


def _extract_drive_id(url: str) -> str | None:
    if not url:
        return None
    match = DRIVE_ID_PATTERN.search(url)
    if match:
        return match.group(1)
    # also handle ?id=FILE_ID style links
    if "id=" in url:
        return url.split("id=")[-1].split("&")[0]
    return None


def _download_drive_file(file_id: str, dest_path: str) -> bool:
    """Downloads a Google Drive file, handling the 'large file' confirm-token page."""
    base_url = "https://drive.google.com/uc?export=download"
    session = requests.Session()
    try:
        response = session.get(base_url, params={"id": file_id}, stream=True, timeout=30)
        token = None
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                token = value
        if token:
            response = session.get(
                base_url, params={"id": file_id, "confirm": token}, stream=True, timeout=30
            )
        if response.status_code != 200:
            return False
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(32768):
                if chunk:
                    f.write(chunk)
        return True
    except requests.RequestException:
        return False


def _extract_text_from_pdf(path: str) -> str:
    try:
        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception:
        return ""


# A lightweight, easily-extended skill vocabulary used for keyword-level
# signal alongside the semantic JD-similarity score computed in scorer.py.
SKILL_VOCAB = [
    "python", "java", "c++", "javascript", "typescript", "sql", "r",
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn", "pandas",
    "numpy", "opencv", "nlp", "cnn", "rnn", "lstm", "transformer", "bert",
    "gpt", "llm", "langchain", "rag", "vector database", "huggingface",
    "flask", "fastapi", "django", "react", "node.js", "docker", "kubernetes",
    "aws", "gcp", "azure", "mlops", "spark", "hadoop", "tableau", "power bi",
    "git", "github", "linux", "mongodb", "mysql", "postgresql", "redis",
]


def _extract_skills(text: str) -> list[str]:
    text_lower = text.lower()
    return [skill for skill in SKILL_VOCAB if skill in text_lower]


def process_all_resumes(resume_dir: str) -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT s_no, resume FROM candidates").fetchall()

    success, failed = 0, 0
    for s_no, resume_url in rows:
        file_id = _extract_drive_id(resume_url)
        if not file_id:
            failed += 1
            continue

        dest = os.path.join(resume_dir, f"{s_no}.pdf")
        ok = _download_drive_file(file_id, dest)
        if not ok:
            failed += 1
            continue

        text = _extract_text_from_pdf(dest)
        skills = _extract_skills(text)

        conn.execute(
            "UPDATE candidates SET resume_text = ?, resume_skills = ? WHERE s_no = ?",
            (text, ", ".join(skills), s_no),
        )
        success += 1

    conn.commit()
    conn.close()
    return {"success": success, "failed": failed, "total": len(rows)}
