# Visl Screen — AI Candidate Screening Platform

An AI-powered candidate screening platform built for the Visl AI Labs Founding
AI Engineer assignment. Automates resume processing, GitHub repo-level
analysis, JD-relevance scoring, candidate ranking, test-link emailing, and
interview scheduling with real Google Calendar + Meet integration.

## Architecture at a glance

```
Frontend (single HTML dashboard)
        |
        v
FastAPI backend  ──>  SQLite (candidates, scores, interviews)
   |        |       |
   |        |       └──> Google Calendar API (OAuth2) — real Meet links
   |        └──────────> Gmail SMTP (your own account) — test link emails
   └───────────────────> GitHub REST API — repo-level analysis
                          sentence-transformers (local, open-source) — JD matching
```

See `architecture.md` for the full design rationale and AI evaluation approach.

## Setup

### 1. Clone and install

```bash
git clone <your-repo-url>
cd visl-screening/backend
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file (or export these directly) in `backend/`:

```bash
# GitHub API — without this you'll hit the 60 req/hr unauthenticated limit
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Gmail SMTP — for sending test links to shortlisted candidates
SENDER_EMAIL=you@gmail.com
SENDER_APP_PASSWORD=xxxxxxxxxxxxxxxx
TEST_LINK=https://forms.gle/your-actual-test-link

# Google Calendar OAuth — for real Calendar + Meet scheduling
GOOGLE_CLIENT_ID=xxxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx
GOOGLE_REDIRECT_URI=https://your-deployed-url.com/api/google/oauth2callback
```

Load them before running, e.g.:
```bash
export $(cat .env | xargs)
```

### 3. Run locally

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Visit `http://localhost:8000` for the dashboard.

### 4. Sample data

`data/candidates_sample.csv` and `data/test_results_sample.csv` contain the
provided assignment dataset, ready to upload directly through the dashboard
for a demo run.

## Workflow (matches assignment's expected pipeline)

1. Upload candidate CSV → `/api/upload-candidates`
2. Paste job description → `/api/job-description`
3. Process resumes (download + extract) → `/api/process-resumes`
4. Analyze GitHub profiles (repo-level) → `/api/analyze-github`
5. Score & rank candidates → `/api/score-candidates`
6. Email test links to top N → `/api/shortlist-and-email`
7. Upload test results CSV → `/api/upload-test-results`
8. Finalize shortlist by test thresholds → `/api/finalize-shortlist`
9. Connect Google Calendar (OAuth) → `/api/google/auth-url`
10. Schedule interviews with auto Meet links → `/api/schedule-interviews`

All steps are also triggerable from the dashboard UI in order.

## Tech stack

- **Backend:** FastAPI (Python)
- **Database:** SQLite (file-based, swappable for Postgres at scale)
- **AI/NLP:** sentence-transformers (`all-MiniLM-L6-v2`) — local, open-source,
  no API cost — for semantic JD-relevance scoring
- **Resume parsing:** PyMuPDF
- **GitHub analysis:** GitHub REST API, repo-level (commits, stars, README, recency)
- **Email:** SMTP via the recruiter's own Gmail account (App Password)
- **Calendar:** Google Calendar API v3 with OAuth2, `conferenceData` for auto Meet links

## Deployment

Deployed on [Render / Railway — fill in actual URL after deploy].
See `architecture.md` for scalability notes.
