# Architecture Document — Visl Screen

## 1. System Overview

Visl Screen automates the recruitment pipeline described in the assignment:
candidate ingestion → AI evaluation (resume + GitHub + JD-fit) → ranking →
test-link automation → results-based shortlisting → interview scheduling.

The system is intentionally built as a **modular monolith**: one FastAPI
process with clearly separated modules (ingestion, resume processing, GitHub
analysis, scoring, emailing, calendar integration), backed by SQLite. This
is the right choice for the assignment's scale and timeline — a
microservices split would add deployment complexity without adding
capability at this data volume, and the module boundaries already make a
future split straightforward if scale demanded it (see Section 5).

```
┌─────────────┐      ┌──────────────────────────────────────────────┐
│  Dashboard   │◄────►│                FastAPI Backend                │
│  (HTML/JS)   │      │  ┌────────┐ ┌──────────┐ ┌─────────────────┐ │
└─────────────┘      │  │ ingest │ │  resume  │ │ github_analyzer │ │
                      │  └────────┘ │processor │ └─────────────────┘ │
                      │  ┌────────┐ └──────────┘ ┌─────────────────┐ │
                      │  │ scorer │               │   calendar_     │ │
                      │  └────────┘ ┌──────────┐ │  integration    │ │
                      │  ┌────────┐ │ emailer  │ └─────────────────┘ │
                      │  │  db    │ └──────────┘                     │
                      │  └────┬───┘                                  │
                      └───────┼──────────────────────────────────────┘
                              ▼
                         SQLite (screening.db)
                              │
              ┌───────────────┼───────────────┬──────────────┐
              ▼               ▼               ▼              ▼
        GitHub REST API  Google Drive   Gmail SMTP   Google Calendar API
```

## 2. AI Evaluation Approach (core design decision)

The assignment explicitly invites "any LLM or AI framework, open-source
preferred." Two options were considered:

**Option A — Call a hosted LLM (e.g. GPT-4) to "read and judge" each resume
against the JD.**
Rejected as the primary mechanism because: (1) it's a black box — hard to
explain *why* a candidate scored what they did, which works against the
"Explainable AI" bonus point; (2) it introduces API cost and external
dependency risk during a live demo; (3) it doesn't showcase engineering
judgment — it just forwards text to someone else's model.

**Option B — Local, open-source sentence embeddings for semantic
similarity, combined with transparent rule-based sub-scores.**
This is what was built. Specifically:

- **JD relevance (40% of final score):** the job description and each
  candidate's combined text (resume + best AI project + research work) are
  embedded using `all-MiniLM-L6-v2` (via `sentence-transformers`, running
  locally, free, ~80MB model). Cosine similarity between the two embeddings
  produces a 0–100 relevance score. This captures *semantic* meaning, not
  just keyword overlap — a candidate describing "image classification with
  deep neural networks" matches a JD asking for "computer vision experience"
  even without shared words.

- **GitHub activity (25%):** repo-level analysis (Section 3).

- **Academic performance (10%):** CGPA normalized to a 0–100 scale. Weighted
  low deliberately — a high CGPA with no demonstrated technical activity is
  a weak signal for an Applied AI role; this is stated explicitly in the
  scoring code as a design choice, not hidden.

- **Test performance (25%):** logical aptitude (40%) + coding test (60%),
  weighted toward coding since this is an engineering role.

The final weighted formula is computed transparently, and the **complete
breakdown is stored and shown per-candidate** — every number in the final
score traces back to a visible, labeled sub-score and weight. This is the
explainable-AI bonus point: not a separate feature, but a property of how
the scorer was designed from the start.

## 3. GitHub Analysis Methodology (repo-level, per the constraint)

A profile-level check (just "does this account exist, how many followers")
would not satisfy the assignment's explicit requirement for repository-level
evaluation, and more importantly wouldn't catch the most common
resume-inflation pattern: claiming sophisticated AI projects with no
corresponding code.

For each candidate's GitHub username, the system:
1. Fetches all public repositories, filtering out forks (forks reflect
   browsing, not building).
2. For up to 15 most-recently-updated original repos, pulls: primary
   language, star count, last-push timestamp, and README presence.
3. Computes a weighted composite:
   - 40% — average recency/activity score (repos pushed in the last 30 days
     score highest; repos untouched for a year score lowest)
   - 25% — repo breadth (number of original repos, capped at 10)
   - 20% — documentation quality (fraction of repos with a README)
   - 15% — community signal (total stars, capped at 20)

This surfaces a real, observed discrepancy in the provided sample dataset:
one candidate's resume describes a sophisticated production RAG system, but
their GitHub account has 25 public repositories and **zero** that are
original (non-fork) work — a concrete, repo-level finding that a
profile-level check would have missed entirely.

**Rate limits:** GitHub's unauthenticated API allows 60 requests/hour, which
is exhausted quickly once README lookups are added per repo. A `GITHUB_TOKEN`
(personal access token, no special scopes needed for public data) raises
this to 5,000/hour — required for any realistic candidate volume.

## 4. Automation Pipeline

| Stage | Mechanism | Real or simulated? |
|---|---|---|
| Resume download | Google Drive direct-download URL conversion | Real |
| Resume text extraction | PyMuPDF | Real |
| GitHub analysis | GitHub REST API v3 | Real |
| JD scoring | Local sentence-transformer embeddings | Real |
| Test-link emails | SMTP via recruiter's own Gmail (App Password) | Real — per constraint, uses candidate's own email account |
| Calendar + Meet | Google Calendar API v3, OAuth2, `conferenceData` | Real — satisfies "Real Google Calendar integration is required" |

Nothing in the core pipeline is mocked or hardcoded; every stage hits a real
external service or performs real computation on the uploaded data.

## 5. Scalability Considerations (bonus point)

The current implementation prioritizes demo-ability within the assignment's
60-hour window, but each module is written to scale independently:

- **Database:** SQLite today; the schema has no SQLite-specific features
  (no triggers, no custom functions), so migrating to PostgreSQL is a
  connection-string change in `db.py`, not a rewrite.
- **GitHub/resume processing:** currently synchronous and sequential per
  request. At higher candidate volumes, this is the natural place to
  introduce a task queue (Celery + Redis, or even FastAPI `BackgroundTasks`
  for a lighter first step) so the upload endpoint returns immediately and
  processing happens asynchronously, with status polled from the dashboard.
- **Embedding model:** runs once per candidate per scoring pass. For large
  datasets, this is trivially batchable — `sentence-transformers` supports
  batch encoding natively, and the candidate corpus could be pre-embedded
  and cached, recomputing only the JD embedding per new search.
- **Rate-limited external APIs (GitHub, Gmail):** the current sequential
  loop with small sleep delays is the simplest correct approach for the
  assignment scale. At scale this becomes a worker pool with per-service
  rate limiters (e.g. `token-bucket` pattern) rather than a single thread
  sleeping between calls.
- **Stateless backend:** the FastAPI app holds no in-memory session state
  (the embedding model is the only "global," and it's read-only after load),
  so horizontal scaling behind a load balancer is straightforward once the
  database is moved off SQLite.

## 6. Known Limitations (stated explicitly, not hidden)

- Google Drive resume downloads can fail for files with sharing
  restrictions or Google's anti-bot interstitial on large files; the system
  logs failures per-candidate rather than blocking the whole batch.
- The skill-keyword extraction in `resume_processor.py` uses a fixed
  vocabulary list — a production version would extract skills via NER or an
  LLM call, but for the demo's purpose (a secondary signal alongside the
  primary embedding-based score) a vocabulary match is sufficient and fully
  transparent.
- Calendar scheduling currently assigns fixed 30-minute slots sequentially
  starting the next day; it does not yet check the recruiter's actual
  calendar for conflicts. The Calendar API call already returns enough data
  to add a free/busy check as a follow-up.
