# Application

Python application in `newsalert/`:

- `collector/`: GDELT + RSS into scored events (auto / review / drop); Wikipedia as an independent check.
- `web/`: register, login, notification destinations (email, Slack), test sends, delivery history, and an admin view.
- `delivery/`: dispatcher and channel adapters.
- `db/`: one shared SQLite schema for all of the above.

No subscriptions or personalized event filters: the system selects important events, users choose where they go.

Fastest way to see it work: `scripts/demo.sh` (see `scripts/README.md`), or `docker compose up` (see the root README).

## Setup

From the repository root:

```sh
uv sync --python 3.12
cp .env.example .env
```

Generate a private secret using the command in `.env.example` and replace the example
value in `.env`. Set `NEWSALERT_COOKIE_SECURE=true` when serving over HTTPS.

Create the tables once (all models, WAL mode; reads `NEWSALERT_DATABASE_URL` from the environment or `.env`):

```sh
uv run python -m newsalert.db.init
```

`create_all` only adds missing tables. After a column change, recreate the development database.

Then start the web app:

```sh
uv run uvicorn newsalert.web.app:create_app --factory --reload
```

Open `http://127.0.0.1:8000/register`. Add an email or an existing Slack incoming webhook
on `/settings`. Pause or enable destinations there. To replace an address/webhook,
pause its destination and add a new one, preserving delivery history.

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/login`, `/register`, `/settings` | User screens |
| GET | `/api/auth/csrf` | Establish session and retrieve CSRF token |
| POST | `/api/auth/register` | Email/password registration and sign-in |
| POST | `/api/auth/login` | Sign in |
| POST | `/api/auth/logout` | Clear browser session |
| GET | `/api/auth/me` | Current user |
| GET, POST | `/api/destinations` | List or create own destinations |
| PATCH | `/api/destinations/{id}` | Set own destination's `enabled` flag |
| POST | `/api/destinations/{id}/test` | Submit a test using the saved destination |
| GET | `/api/deliveries?limit=50&offset=0` | Paginated own delivery history |

Mutating API requests require the `X-CSRF-Token` header and session cookie. Fetch a
fresh token after registering or logging in, since authentication rotates it. The
browser UI handles this through a full navigation after sign-in.

Destination inputs:

```json
{"type": "email", "email_address": "reader@example.com"}
```

```json
{"type": "slack", "webhook_url": "https://hooks.slack.com/services/T123/B456/secret"}
```

Saved webhook URLs are never returned to the browser. Passwords use Argon2 through
pwdlib. Sessions use Starlette's signed, HttpOnly cookies with a 12-hour expiry;
they contain an account ID and CSRF token, never passwords or webhook URLs.
Logout removes the browser cookie; server-side session revocation is not implemented.
The private SQLite volume contains webhook credentials and must stay out of version control.

## Shared integration contract

- `newsalert.db.base.Base` is the shared SQLAlchemy metadata; collector models should
  inherit from it. `newsalert.db.users` defines `User`, `Destination` and `Delivery`.
- Collector owns `events`. `Delivery.event_id` and the collector's `Event.id` both
  use TEXT IDs; their models share the same metadata.
- Use the same SQLite database URL and secret across web processes. The session
  helper enables foreign keys and a busy timeout. WAL belongs to shared DB setup.
- A delivery's `created_at`, `next_attempt_at` and `sent_at` are ISO 8601 UTC text;
  status is `pending`, `sent`, `failed` or `skipped`. Event/destination is unique.
- Delivery history joins the collector's event model to display its headline.
- `newsalert.delivery` owns submission and dispatch; `newsalert.collector` owns events and the collector tables.

## Notification sending

Start Mailpit locally (or use the Mailpit service in the shared Compose setup):

```sh
docker run --rm --name newsalert-mailpit \
  -p 127.0.0.1:1025:1025 -p 127.0.0.1:8025:8025 axllent/mailpit
```

The defaults in `.env.example` point SMTP at `127.0.0.1:1025`; Mailpit's inbox is
`http://127.0.0.1:8025`. With a containerized web/dispatcher, set SMTP host to the
Mailpit service name. External SMTP can use `starttls` or `tls` and credentials.

After the joint database setup, start one dispatcher alongside the web process:

```sh
uv run python -m newsalert.delivery.dispatcher
# Or process one bounded batch:
uv run python -m newsalert.delivery.dispatcher --once
```

The dispatcher:

1. Reads `selected` events with `selected_at` and records one job per existing
   destination. New destinations do not receive historical selected events.
2. Records paused destinations as `skipped` when first observed, preventing those
   same jobs being backfilled on re-enable. Existing pending jobs also recheck
   destination enabled state before submission.
3. Renders headline, summary and up to three safe source links from collector evidence.
   Email includes text and HTML; Slack uses escaped text and source links.
4. Submits outside database transactions, then records acceptance or a sanitized error.
5. Retries temporary SMTP errors, Slack HTTP 429/5xx and connection failures. Defaults:
   three attempts total, 30-second then 60-second backoff. Slack `Retry-After` can
   extend that delay. Permanent failures become `failed` without more attempts.

Slack requests use the saved incoming webhook, do not follow redirects, and are
paced at one per second per sender process. Only Slack-hosted incoming webhook URLs
are accepted. No Slack app installation is performed by this application.

The single dispatcher uses a lock file beside the SQLite file to prevent duplicate
worker processes on the shared local volume (Linux/macOS). Attempts are recorded
before submission; an interrupted attempt is reconsidered after a two-minute delay.
Timeouts/crashes after provider acceptance can still cause an external duplicate.
The database constraint prevents duplicate jobs, not exactly-once external delivery.

“Send test” works for an owned destination even while paused, submits once through
the same adapter, and reports acceptance/failure immediately. It creates neither a
fake event nor a delivery row and is not automatically retried.

## Collector

One window (for testing past days; `--rss-dir` loads a saved RSS snapshot first):

```sh
uv run python -m newsalert.collector.run --start 2026-11-05 --end 2026-11-06
```

Continuously (what the `collector` container runs): every 15 minutes, poll RSS and process the last 24 hours of GDELT:

```sh
uv run python -m newsalert.collector.worker          # --once for a single cycle
```

Each run: GDELT articles are grouped into stories, scored by independent outlets (syndicated copies count once), confirmed by the five RSS feeds, and banded:
`auto` (outlets >= 100 and >= 2 RSS feeds) becomes `selected` and is sent; `review` (outlets >= 30) waits in the admin view; the rest is `drop`.
Thresholds are settings (`NEWSALERT_AUTO_MIN_OUTLETS`, `NEWSALERT_AUTO_MIN_RSS`, `NEWSALERT_REVIEW_MIN_OUTLETS`).
A story seen again in a later, overlapping window keeps its event id (matched by shared articles), so it is never sent twice.
`selected` is final, and the collector never overrides an admin decision.
Wikipedia is fetched for the window plus two earlier days and only written to `wiki_checks`; scoring never reads it.
Network use is fetch-only (GDELT files, RSS feeds, Wikipedia API). Wikimedia requires a User-Agent with contact details: set `NEWSALERT_HTTP_USER_AGENT` to your repository URL.

## Admin view

Set `NEWSALERT_ADMIN_EMAILS` (comma-separated) to the accounts that may open `/admin`; others get 403.

| Page | Shows |
| --- | --- |
| `/admin` | collector runs, event counts per band/status, delivery counts, Wikipedia agreement |
| `/admin/events` | events filterable by band/status: outlets, RSS confirmations, score, Wikipedia check |
| `/admin/events/{id}` | evidence (GDELT clusters, RSS articles), Wikipedia match and shared terms, deliveries; buttons to select a `review` event or drop a candidate |
| `/admin/deliveries` | delivery log with status, attempts and errors (webhook URLs never shown) |

## Adding a channel

Channel-neutral today: `Notification` and `Target` (`delivery/messages.py`), the dispatcher, retries, and delivery history.
A new channel (for example Teams) needs four small changes:

1. `delivery/channels.py`: a `_teams()` method and a branch in `ChannelSender.send`.
2. `web/schemas.py`: add the type to `DestinationCreate` and validate its address.
3. `db/users.py`: add the type to the `ck_destination_type` constraint (and an address column, or reuse `webhook_url`).
4. `web/templates/settings.html`: the form option.

Known limitation: the type is spread over four files instead of one registry; a registry is the next refactor if more channels come.

## Verification

```sh
uv run pytest -q
uv run ruff check src tests
```

Tests create disposable SQLite tables only inside test fixtures. They cover account
normalization and password hashing, login/logout, CSRF, ownership isolation, webhook
validation and redaction, delivery uniqueness/history, and absence of startup DDL.
Delivery tests additionally cover fan-out, no historical backfill, paused destinations,
three-attempt retries, `Retry-After`, worker locking, source-link rendering, SMTP error
classification and Slack request/response handling. Slack requests are mocked.

To opt into the real local Mailpit test while it is running:

```sh
NEWSALERT_TEST_MAILPIT_URL=http://127.0.0.1:8025 \
  uv run pytest tests/test_delivery.py -k local_mailpit -q
```

That test submits a fixture event and an API test notification through actual SMTP,
then checks Mailpit's captured text/HTML. It requires loopback Mailpit/SMTP hosts and
does not contact external mailboxes or Slack. No migrations or app tables are created
by the dispatcher or web startup; schemas in tests are disposable.
