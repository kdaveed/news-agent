#!/usr/bin/env bash
# One-command local end-to-end demo (app runs with uv; only Mailpit runs in Docker).
#   Default (live): one collector cycle now = poll the 5 RSS feeds, process the last 24 h of GDELT,
#   check Wikipedia -> selected events -> dispatcher --once -> email in the local Mailpit inbox.
#   --replay: Thursday 2026-11-05 with the saved RSS snapshot (only if that snapshot exists locally),
#   to reproduce the documented phase 2/3 results.
# Uses a fresh data/demo.db and its own data/demo-data/ folder. Never touches data/newsalert.db.
set -euo pipefail

cd "$(dirname "$0")/.."

MODE=live
[[ "${1:-}" == "--replay" ]] && MODE=replay
START=2026-11-05
END=2026-11-06
DB_FILE=data/demo.db
RSS_DIR=phases/phase-1-event-source-discovery/research/data/rss/20261105T203836Z
DEMO_EMAIL=demo@example.com
DEMO_PASSWORD=demo-password-123
MAILPIT_UI=http://127.0.0.1:8025

step() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v uv >/dev/null || die "uv is required (https://docs.astral.sh/uv/)"
command -v curl >/dev/null || die "curl is required"

# Explicit settings: real environment variables take precedence over ./.env, so a local .env
# cannot redirect the demo to another database or SMTP server.
export NEWSALERT_DATABASE_URL="sqlite:///./${DB_FILE}"
export NEWSALERT_SMTP_HOST=127.0.0.1
export NEWSALERT_SMTP_PORT=1025
export NEWSALERT_SMTP_SECURITY=none
export NEWSALERT_SMTP_USERNAME=""
export NEWSALERT_SMTP_PASSWORD=""
export NEWSALERT_SMTP_FROM=alerts@example.com
export NEWSALERT_DATA_DIR=data/demo-data  # raw GDELT/RSS for the demo; the live worker prunes it
# Throwaway session secret, in memory only (never written or printed).
NEWSALERT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export NEWSALERT_SECRET_KEY

step "Mailpit (local SMTP 127.0.0.1:1025, inbox ${MAILPIT_UI})"
smtp_up() { (exec 3<>/dev/tcp/127.0.0.1/1025) 2>/dev/null; }
if curl -fsS -o /dev/null "${MAILPIT_UI}/api/v1/info" && smtp_up; then
  echo "reusing the Mailpit already listening on 1025/8025"
else
  command -v docker >/dev/null || die "Docker is required to start Mailpit"
  docker run -d --rm --name newsalert-mailpit \
    -p 127.0.0.1:1025:1025 -p 127.0.0.1:8025:8025 axllent/mailpit >/dev/null
  for _ in $(seq 1 30); do
    curl -fsS -o /dev/null "${MAILPIT_UI}/api/v1/info" && smtp_up && break
    sleep 1
  done
  curl -fsS -o /dev/null "${MAILPIT_UI}/api/v1/info" || die "Mailpit did not start"
  echo "started container newsalert-mailpit"
fi

step "Fresh database ${DB_FILE}"
rm -f "${DB_FILE}" "${DB_FILE}-shm" "${DB_FILE}-wal" "${DB_FILE%.db}.dispatcher.lock"
uv run python -m newsalert.db.init

step "Demo user ${DEMO_EMAIL} with an enabled email destination"
# Same records the UI creates: casefolded email, Argon2 hash, enabled email destination.
# Created before the collector run, so the dispatcher fans the new selected events out to it.
DEMO_EMAIL="${DEMO_EMAIL}" DEMO_PASSWORD="${DEMO_PASSWORD}" uv run python - <<'PY'
import os

from sqlalchemy.orm import Session

from newsalert.db import Destination, User
from newsalert.db.session import make_engine
from newsalert.web.security import passwords

email = os.environ["DEMO_EMAIL"].strip().casefold()
engine = make_engine(os.environ["NEWSALERT_DATABASE_URL"])
with Session(engine) as s:
    user = User(email=email, password_hash=passwords.hash(os.environ["DEMO_PASSWORD"]))
    s.add(user)
    s.flush()
    s.add(Destination(user_id=user.id, type="email", email_address=email, enabled=True))
    s.commit()
    print(f"user id={user.id} {email}; email destination enabled")
PY

if [[ "${MODE}" == "live" ]]; then
  step "Collector: one live cycle (RSS now + last 24 h of GDELT, ~20-40 MB download, about a minute)"
  uv run python -m newsalert.collector.worker --once
else
  [[ -d "${RSS_DIR}" ]] || die "--replay needs the saved RSS snapshot ${RSS_DIR} (not in the repository)"
  step "Collector: replay ${START}..${END} with the saved RSS snapshot"
  uv run python -m newsalert.collector.run --start "${START}" --end "${END}" --rss-dir "${RSS_DIR}"
fi

step "Dispatcher: one batch"
uv run python -m newsalert.delivery.dispatcher --once

step "Summary"
uv run python - <<'PY'
import os
import sqlite3

path = os.environ["NEWSALERT_DATABASE_URL"].removeprefix("sqlite:///")
con = sqlite3.connect(path)
print("events by band/status:")
for band, status, n in con.execute(
    "SELECT band, status, count(*) FROM events GROUP BY band, status ORDER BY band, status"
):
    print(f"  {band:7} {status:10} {n}")
print("deliveries by status:")
rows = con.execute("SELECT status, count(*) FROM deliveries GROUP BY status ORDER BY status").fetchall()
for status, n in rows or [("(none)", 0)]:
    print(f"  {status:10} {n}")
print("selected headlines (sent):")
sel = con.execute("SELECT headline FROM events WHERE status = 'selected' ORDER BY selected_at LIMIT 10").fetchall()
for (headline,) in sel:
    print(f"  - {headline}")
if not sel:
    print("  (none today: no story reached 100 outlets and 2 RSS feeds; see the review candidates)")
print("top review candidates (an admin can select them in /admin):")
for (headline, n) in con.execute(
    "SELECT headline, independent_outlets FROM events WHERE band = 'review' ORDER BY score DESC LIMIT 5"
):
    print(f"  - {headline} ({n} outlets)")
PY

total="$(curl -fsS "${MAILPIT_UI}/api/v1/search?query=to:${DEMO_EMAIL}" \
  | python3 -c 'import json, sys; print(json.load(sys.stdin).get("messages_count", "?"))' || echo "?")"

cat <<EOF

Done.
  Mailpit inbox:   ${MAILPIT_UI}   (${total} message(s) to ${DEMO_EMAIL} so far)
  Demo login:      ${DEMO_EMAIL} / ${DEMO_PASSWORD}
  Start the web UI on the demo database (generates its own session secret):

    NEWSALERT_DATABASE_URL=sqlite:///./${DB_FILE} NEWSALERT_ADMIN_EMAILS=${DEMO_EMAIL} \\
    NEWSALERT_SECRET_KEY="\$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \\
    uv run uvicorn newsalert.web.app:create_app --factory --port 8000

  then open http://127.0.0.1:8000/login
EOF
