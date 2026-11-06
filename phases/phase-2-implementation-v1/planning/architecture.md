# Architecture and folder structure (V1)

Shared by both threads. Change it only after checking with the other side.


# Stack

Python for everything. SQLite (WAL mode) as the app database. DuckDB only for raw GDELT processing.
Web: FastAPI with server-rendered templates (Jinja, HTMX). Email: SMTP (Mailpit locally). Slack: incoming webhook over HTTP.


# Containers (Docker Compose, one image, different commands)

collector - every 15 minutes processes the latest time window into events; daily Wikipedia check.
web - FastAPI: user screens and admin panel.
dispatcher - reads selected events, creates deliveries, sends them through the channel adapters, retries failures.
mailpit - local SMTP server with a browser inbox for the demo.

Shared volume: the SQLite file and the raw GDELT/RSS/Wikipedia files.
No message queue: the deliveries table is the queue. No cron container: each worker runs its own loop.


# Folder structure

src/newsalert/                 one package name, so our modules don't clash with installed packages
  collector/                   Claude - ingest (GDELT, RSS, Wikipedia), grouping, events, Wikipedia check
  delivery/                    Codex - dispatcher, channel adapters (email, slack)
  web/                         users screens (Codex), admin panel (owner to be decided)
  db/                          schema and models
    collector tables           Claude - gdelt_clusters, rss_items, wiki_entries, events, event_evidence, wiki_checks, collector_runs
    user and delivery tables   Codex - users, destinations, deliveries
docker-compose.yml
Dockerfile

Imports: from newsalert.collector import ..., from newsalert.db import ...


# Ownership

Claude: collector and its models in db/, including the shared events table.
Codex: users, destinations, deliveries and delivery/.
Shared: events. The collector writes it; delivery reads events with status "selected". See data-schema-collector.md, "Contract with delivery".
