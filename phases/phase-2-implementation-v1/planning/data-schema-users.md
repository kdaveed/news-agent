# Data schema: users and notifications (Codex)

Storage: the same SQLite application database as the collector.
Scope: the system selects important events; users choose enabled notification destinations. No subscriptions, topic filters or per-user thresholds.


# Tables

users - one row per account
  id INTEGER primary key
  email TEXT not null, unique (trimmed and normalized consistently at signup/login)
  password_hash TEXT not null (authentication-library hash, never a plain password)
  created_at TEXT not null (UTC)

destinations - one row per user-configured email address or Slack webhook
  id INTEGER primary key
  user_id INTEGER not null, references users.id
  type TEXT not null: email | slack
  email_address TEXT (email destinations only)
  webhook_url TEXT (Slack destinations only; secret, masked in responses and logs)
  enabled INTEGER not null, default 1 (0 or 1)
  created_at TEXT not null (UTC)
  constraint: email requires email_address and no webhook_url; Slack requires webhook_url and no email_address

deliveries - one notification job per event and destination, updated on each attempt
  id INTEGER primary key
  event_id not null, references events.id (same ID type as the collector)
  destination_id INTEGER not null, references destinations.id
  status TEXT not null, default pending: pending | sent | failed | skipped
  attempts INTEGER not null, default 0
  next_attempt_at TEXT (UTC; scheduled retry when pending)
  last_error TEXT (sanitized; never include the Slack webhook secret)
  created_at TEXT not null (UTC)
  sent_at TEXT (UTC; populated after successful submission)
  unique: event_id + destination_id
  index: status + next_attempt_at

Retrying updates the same delivery row; there is no separate attempt-history table in V1. sent means accepted by Slack or the SMTP server, not proof of inbox delivery or reading.


# Shared contract with collector and sending

The collector owns events; do not create a second events table. See [collector schema](data-schema-collector.md).
Only status = selected is eligible for delivery. band alone does not authorize sending.
Delivery references the stable events.id and reads headline, summary and selected_at. Source links come through event_evidence and the source tables; there is no events.source_url field in the current collector schema.
Selected events are sent once per destination. Later edits to the same event do not create another notification in V1.
Codex owns the users/destinations implementation and this delivery schema. The sending component creates and updates delivery rows; the collector never writes them. The admin panel can read these tables for operational views.
Enable SQLite foreign keys on every connection. Keep database transactions short; do not hold one open during HTTP or SMTP calls.


# Flow

1 User registers/logs in and adds email addresses or client-supplied Slack webhook URLs.
2 When an event becomes selected, create pending deliveries for enabled destinations. Use the unique event/destination pair to make repeated enqueueing harmless.
  The dispatcher also records already-paused destinations as skipped on first observation, so re-enabling does not backfill those events.
3 One V1 sender worker reads due pending jobs and rechecks that the destination is enabled. Disabled destinations become skipped.
4 Submit email through configured SMTP (Mailpit locally), or Slack through an HTTP POST.
5 Successful submission becomes sent. Temporary failures stay pending with a delayed retry; permanent errors or exhausted retries become failed. Proposed V1 limit: three attempts total.

New destinations receive future selected events, not historical backfill; require destination.created_at <= event.selected_at when enqueueing. Re-enabling a destination does not resend existing sent/skipped/failed jobs. Network timeouts can leave acceptance uncertain, so retries may still produce external duplicates; the unique constraint only prevents duplicate local jobs.


# User views

Login/register.
My destinations: add, edit, enable/disable and send a test notification.
Delivery history: event headline, destination type, status, attempts and error.

Every user operation checks ownership through destinations.user_id. Test sends use the same adapters without inventing an event or inserting a normal event-delivery row; return their result directly to the user.
Disable destinations rather than deleting rows referenced by delivery history. Do not change their address/type while deliveries are pending; disable the old destination and add a new one.


# Points to align before implementation

The implemented collector Event.id and Delivery.event_id both use TEXT IDs on the shared SQLAlchemy Base. Delivery history reads the collector's event headline directly.
Use one shared database migration sequence so both components agree on the events foreign key and table definitions.
