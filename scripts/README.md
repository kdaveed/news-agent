# scripts

`demo.sh` runs a reproducible local end-to-end demo, with the app running directly through uv: `./scripts/demo.sh`.

1. Reuses a Mailpit already listening on 127.0.0.1:1025/8025, or starts `axllent/mailpit` with `docker run`.
2. Recreates `data/demo.db` (never touches `data/newsalert.db`) and runs `newsalert.db.init`.
3. Creates the user `demo@example.com` (password `demo-password-123`) with an enabled email destination.
4. Runs the collector for 2026-11-05..2026-11-06 with the saved phase-1 RSS snapshot (if present) and the Wikipedia check.
5. Runs `dispatcher --once` (email to the local Mailpit only), then prints events by band, deliveries by status, the inbox URL and the web start command.

Prerequisites: uv, Python 3.12, Docker (only for Mailpit), curl, and network access for GDELT and Wikipedia.
The first run downloads about 20 MB of GDELT into `data/gdelt/` (cached afterwards). It uses a throwaway in-memory session secret and ignores the DB and SMTP settings in `.env`.
