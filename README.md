# CommitFlow: AI-Powered Redmine Worklog Automation

CommitFlow is a production-grade, extensible Python application designed to automate the daily logging of developer tasks into Redmine. By analyzing Git commit logs and file changes from GitHub and GitLab, and leveraging advanced Large Language Models (LLMs), CommitFlow maps your daily coding activities directly onto Redmine Features (Parent Issues) and files child work logs under them automatically.

---

## Quick Run (every day)

### CLI (unchanged — still works)

Open a terminal and run:

```bash
cd "/home/hello/Documents/My projects /CommitFlow"

# 1) Check connections
.venv/bin/python3 -m app.cli test-connection

# 2) Preview only (no Redmine write)
.venv/bin/python3 -m app.cli sync --today --dry-run

# 3) Full sync — creates to-dos + logs 8 hours in Redmine
.venv/bin/python3 -m app.cli sync --today
```

| Step | What it does |
|------|----------------|
| `test-connection` | Checks GitHub, GitLab, and Redmine are working |
| `sync --today --dry-run` | Preview only — shows to-dos/hours, **does not write to Redmine** |
| `sync --today` | Finds today's commits (skips merge/PR commits), creates to-dos, logs **8 hours** in Redmine |

For a past date:

```bash
.venv/bin/python3 -m app.cli sync --date 2026-07-09 --dry-run
.venv/bin/python3 -m app.cli sync --date 2026-07-09
```

### Web app (multi-user — additive)

Anyone can register, save their own tokens in Settings, then dry-run / sync from the UI.
Your local CLI + `.env` keep working independently.

```bash
# Install API deps (once)
.venv/bin/pip install -e .

# Terminal A — API
.venv/bin/uvicorn api.main:app --reload --port 8000

# Terminal B — frontend
cd web && npm install && npm run dev
```

Open http://localhost:5173 → Sign up → Settings (paste tokens) → Sync.

Optional Docker:

```bash
docker compose up --build
```

### Deploy API on Railway (Gmail SMTP)

Render blocks outbound Gmail SMTP. Host the API on **Railway** so your Gmail App Password works.

1. Push this repo to GitHub (if not already).
2. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub** → select CommitFlow.
3. Railway will use `Dockerfile.api` via `railway.toml`.
4. Open the service → **Variables** → paste values from `railway.env.example` (use your real secrets).
   - Reuse the same **Render Postgres External URL** as `API_DATABASE_URL` so existing users stay.
   - Set `EMAIL_PROVIDER=smtp` + Gmail `SMTP_USER` / `SMTP_PASSWORD` (App Password).
5. Generate a public domain (Railway → Settings → Networking → Generate Domain).
6. Set `API_PUBLIC_URL` to that HTTPS URL (e.g. `https://….up.railway.app`).
7. On **Vercel** (frontend): set `VITE_API_URL` to the Railway URL → redeploy.
8. Smoke-test: `GET https://YOUR-RAILWAY-URL/api/health` then try Forgot password.
9. Stop/delete the old Render **Web Service** (keep Postgres if you still use that URL).

Frontend stays on Vercel. Only the API moves.

### Deploy API on Vercel (experimental)

Root `main.py` exports the FastAPI `app` (avoids Vercel treating the `api/`
**package** as serverless file routes). Config: `[tool.vercel] entrypoint = "main:app"`.

1. Backend Vercel project → **Settings → Build & Development**:
   - Framework: Other / auto (do **not** use Vite)
   - Build Command: empty, Override **off** (never `vite build` / `npm run build`)
   - Install Command: `pip install -r requirements.txt`
   - Root Directory: repo root (**not** `web/`)
2. **Clear cache and redeploy**
3. Env vars from `vercel.env.example`
4. Check `https://YOUR-API.vercel.app/api/health`
5. Frontend: `VITE_API_URL=https://YOUR-API.vercel.app` → redeploy

**Note:** Vercel usually blocks Gmail SMTP. OTP may still need a mail bridge or Resend.

---

## Architecture Overview

```mermaid
graph TD
    A[Git Commits - GitHub/GitLab] --> B[Fetch commits for target date]
    B --> C[Resolver mapping - Repo to Redmine Project]
    C --> D[Retrieve Redmine project Features]
    D --> E[Check Cache - SQLite/SQLAlchemy]
    E -- Cache Hit --> H[Group by Target Feature]
    E -- Cache Miss --> F[Learning System Context + AI Classifier]
    F --> G[Save predictions to Cache DB]
    G --> H
    H --> I[Check if Daily Issue exists under Feature in Redmine]
    I -- Exists --> J[Append Commits as Comments/Notes]
    I -- New --> K[Create Child Work Log Issue]
    H --> L[Generate Markdown, HTML, CSV reports]
```

### Key Architectural Concepts

- **SOLID & Clean Architecture**: Logic layers are clearly decoupled. Integrations (GitHub, GitLab, Redmine) are abstracted behind separate clients.
- **AI Classification**: Leverages system-instructed prompt templates and string similarity checks (`rapidfuzz`) to assign work logs to actual Redmine issues, avoiding invented features.
- **AI Decision Cache**: Avoids duplicate calls to AI APIs by logging processed commit hashes in a local SQLite database cache.
- **Few-Shot Learning System**: If the AI makes a mistake, logging the correction via `commitflow add-feedback` appends it as few-shot training rules in subsequent prompts to automatically adjust recommendations.
- **Duplicate Prevention**: Searches Redmine issues prior to writing. If a work log issue already exists for the day under a Feature, new commits are cleanly appended as journal updates instead of creating duplicate items.

---

## Project Structure

```
app/
    ai/
        provider.py               # Abstract provider interface
        openai_provider.py        # OpenAI completions integration
        gemini_provider.py        # Google Gemini integration
        anthropic_provider.py     # Anthropic Claude integration
        ollama_provider.py        # Local Ollama integration
        openrouter_provider.py    # OpenRouter API integration
    config/
        settings.py               # Pydantic environment configurations
    database/
        connection.py             # SQLAlchemy session and engine initialization
        models.py                 # SQLite Declarative Base tables
        repository.py             # Database read/write functions
    github/
        client.py                 # GitHub REST API client
    gitlab/
        client.py                 # GitLab REST API client
    mappings/
        resolver.py               # YAML repo-to-project resolver mapping loader
    models/
        domain.py                 # Unified domains schemas
    redmine/
        client.py                 # Redmine API Client
    services/
        classifier.py             # Prompt builder, AI runner & similarity resolver
        reporting.py              # Markdown, HTML, CSV summary exporter
        sync.py                   # Main synchronization workflow orchestrator
    utils/
        helpers.py                # Retry decorators and utility logic
    cli.py                        # Typer CLI application wrapper
configs/
    repo_mappings.yaml            # Repo to Redmine project mapping configuration
tests/                            # Full Pytest test suites
README.md                         # Product manual
pyproject.toml                    # Packages configuration and CLI setup
requirements.txt                  # Direct package requirements
```

---

## Installation

### Prerequisites
- Python 3.12 or higher installed.

### Setup Steps
1. Clone the project and navigate to the project directory:
   ```bash
   cd CommitFlow
   ```
2. Install the package in editable mode alongside required packages:
   ```bash
   pip install -e .
   ```
   *Note: This command will install dependencies and register the executable command `commitflow` globally within your active environment.*

---

## Configuration

1. **Environment Settings**: Copy `.env.example` to `.env` and fill out your tokens, API keys, and timezone settings:
   ```bash
   cp .env.example .env
   ```
   **Key Configuration Settings:**
   - `AUTHOR_NAME`: Your exact git committer name (used to filter commits).
   - `TIMEZONE`: Local timezone (e.g. `Asia/Kolkata`, `America/New_York`) to isolate date queries.
   - `AI_PROVIDER`: Choose from `openai`, `gemini`, `anthropic`, `openrouter`, or `ollama`.
   - `AI_CONFIDENCE_THRESHOLD`: Fallback threshold (default: 80). Confidence ratings below this map commits to the `DEFAULT_FEATURE`.

2. **Mappings**: Edit `configs/repo_mappings.yaml` to specify which Git repositories correspond to which Redmine projects:
   ```yaml
   repositories:
     digiflux-ezytix/be-api:
       redmine_project: Ezytix Tech
     digiflux-ezytix/web-app:
       redmine_project: Ezytix Tech
     digiflux-erp/backend:
       redmine_project: ERP
   ```

---

## CLI Usage

All commands use:

```bash
.venv/bin/python3 -m app.cli <command>
```

Verify installation:
```bash
.venv/bin/python3 -m app.cli --help
```

### 1. Test Connections
Test API keys, endpoints, and credentials for Redmine, GitLab, and GitHub:
```bash
.venv/bin/python3 -m app.cli test-connection
```

### 2. View Redmine Projects
Lists all Redmine projects with their identifiers:
```bash
.venv/bin/python3 -m app.cli list-projects
```

### 3. List Project Features
Lists all available Parent Features (parent tasks) for a project:
```bash
.venv/bin/python3 -m app.cli list-features "Ezytix Tech"
```

### 4. Sync Git Commits
Pull today's commits, run classification, and log features to Redmine:
```bash
# Preview first (recommended)
.venv/bin/python3 -m app.cli sync --today --dry-run

# Sync today's work logs (writes to Redmine)
.venv/bin/python3 -m app.cli sync --today

# Sync work logs for a specific past date
.venv/bin/python3 -m app.cli sync --date 2026-07-01
```

### 5. Add AI Correction Feedback
If the AI maps a commit to the wrong Feature, teach the system the correction:
```bash
.venv/bin/python3 -m app.cli add-feedback \
  --commit "a1b2c3d4" \
  --repo "digiflux-ezytix/be-api" \
  --msg "Added payments integration" \
  --predicted "General Development" \
  --corrected "Payment"
```
*Subsequent synchronizations containing similar commits will use this correction as context to increase classification accuracy.*

### 6. Manage Cache
```bash
# Inspect prediction cache
.venv/bin/python3 -m app.cli show-cache

# Purge cache
.venv/bin/python3 -m app.cli clear-cache
```

### 7. Export Summaries
Output Markdown, HTML, and CSV logs locally:
```bash
.venv/bin/python3 -m app.cli export-report 2026-07-06
```
Reports are output to the `./reports` directory.

---

## Running Tests

Tests are handled using `pytest` and mock configurations to avoid hitting external APIs.
To run the full suite:
```bash
pytest tests/
```
