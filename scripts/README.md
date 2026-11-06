# scripts

`demo.sh` runs a local end-to-end demo with live data, the app running directly through uv: `./scripts/demo.sh` (or `--replay`, see step 4).

1. Reuses a Mailpit already listening on 127.0.0.1:1025/8025, or starts `axllent/mailpit` with `docker run`.
2. Recreates `data/demo.db` (never touches `data/newsalert.db`) and runs `newsalert.db.init`.
3. Creates the user `demo@example.com` (password `demo-password-123`) with an enabled email destination.
4. Runs one live collector cycle: polls the 5 RSS feeds, fetches the last 24 h of GDELT, checks Wikipedia. `--replay` instead reprocesses Thursday 2026-11-05 with the saved phase-1 RSS snapshot; that snapshot is not in the repository, so replay only works where it was collected.
5. Runs `dispatcher --once` (email to the local Mailpit only), then prints events by band, deliveries, the selected headlines, the top review candidates, the inbox URL and the web start command.

Prerequisites: uv, Python 3.12, Docker (only for Mailpit), curl, and network access for GDELT and Wikipedia.
Each live run downloads about 20-40 MB of GDELT into `data/demo-data/` (older files are pruned). Network use is fetch-only. It uses a throwaway in-memory session secret and ignores the DB and SMTP settings in `.env`.
