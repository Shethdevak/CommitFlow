"""
Quick test: verify GitLab auth + commit fetching only.
Does NOT touch Redmine or AI.
Run: python test_fetch.py [YYYY-MM-DD]   (defaults to today)
"""
import sys
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

from app.config.settings import load_settings
from app.gitlab.client import GitLabClient
from app.mappings.resolver import MappingResolver

# ── Settings ─────────────────────────────────────────────────────────────────
try:
    settings = load_settings()
except Exception as e:
    print(f"[ERROR] Could not load settings: {e}")
    sys.exit(1)

# ── Date range ────────────────────────────────────────────────────────────────
date_str = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
try:
    parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
except ValueError:
    print(f"[ERROR] Invalid date format: {date_str}. Use YYYY-MM-DD.")
    sys.exit(1)

tz = ZoneInfo(settings.timezone or "UTC")
utc_since = datetime.combine(parsed_date, dtime.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
utc_until = datetime.combine(parsed_date, dtime.max, tzinfo=tz).astimezone(ZoneInfo("UTC"))

print(f"\n{'='*60}")
print(f"  CommitFlow — Fetch Test (NO Redmine / NO AI)")
print(f"{'='*60}")
print(f"  Date     : {date_str}")
print(f"  UTC range: {utc_since.isoformat()} → {utc_until.isoformat()}")

# ── GitLab client ─────────────────────────────────────────────────────────────
if not settings.gitlab_token:
    print("\n[ERROR] GITLAB_TOKEN is not set in .env")
    sys.exit(1)

gitlab = GitLabClient(token=settings.gitlab_token, base_url=settings.gitlab_api_url)

# ── Auto-detect author ────────────────────────────────────────────────────────
author_name = settings.author_name
if not author_name:
    print("\n[INFO] AUTHOR_NAME not set — auto-detecting from GitLab token...")
    author_name = gitlab.get_authenticated_user()
    if author_name:
        print(f"[OK]   Detected author : '{author_name}'")
    else:
        print("[ERROR] Could not detect author from token. Please set AUTHOR_NAME in .env")
        sys.exit(1)
else:
    print(f"\n[INFO] Using configured author: '{author_name}'")

# ── Load repo mappings ────────────────────────────────────────────────────────
resolver = MappingResolver(mappings_path=settings.mappings_path)
repos = list(resolver.mappings.keys())
if not repos:
    print("\n[WARN] No repositories found in configs/repo_mappings.yaml")
    sys.exit(0)

print(f"\n[INFO] Repositories to scan: {repos}\n")

# ── Fetch commits ─────────────────────────────────────────────────────────────
total = 0
for repo in repos:
    print(f"  → Fetching from: {repo}")
    try:
        commits = gitlab.fetch_commits(
            repository=repo,
            author_name=author_name,
            since=utc_since,
            until=utc_until
        )
        if commits:
            for c in commits:
                print(f"      [{c.hash[:8]}] {c.committed_date.strftime('%H:%M')}  {c.message}")
            total += len(commits)
        else:
            print(f"      (no commits by '{author_name}' on {date_str})")
    except Exception as e:
        print(f"      [ERROR] {e}")

print(f"\n{'='*60}")
print(f"  Total commits found: {total}")
print(f"{'='*60}\n")
