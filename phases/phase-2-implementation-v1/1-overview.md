# Phase 2 overview: implementation V1

Building the first working version on top of the phase 1 decision (GDELT detects, RSS confirms, Wikipedia checks).
@me = what I asked or decided. @agent = what an agent produced. @consideration = my reasoning at that point.


# 1. Splitting the work

@me - Split the build across two threads. Codex works on users and their alerts. Claude works on the actual sending and the admin panel.
@consideration - The admin panel feeds into sending: it shows the story candidates with their scores and notes, and the admin who oversees the process can settle ambiguous cases, possibly with AI validation as a tool.
@me - Asked Claude to check this against the brief and give feedback before building.
@agent - The idea fits the brief and the precision-first decision from phase 1: the automatic score is fragile, so a person reviewing borderline stories is the safety net.
@agent - Suggested changes:
  Three bands, so breaking news is not held up: auto-send the strongest stories, queue the borderline ones for the admin, drop the rest.
  The admin view should also cover operations: delivery log, failed sends, users and their alerts.
  Agree a shared contract with Codex (Story, Alert rule, Notification, and who owns what) before either side writes code.
  Decide who matches stories to users' alert rules.
  For V1, replay story candidates from the phase 1 data instead of waiting for a live pipeline.
  Choose a shared stack (Python, FastAPI, SQLite would reuse the phase 1 code).
@consideration - The admin panel is not mainly for manual validation. It is for inspecting the collector: testing the past few days of data and seeing what the data collection module produces.


# 2. Data collector: first draft

@me - Asked for the quickest way to build a first draft of the GDELT + RSS + Wikipedia collector, with two directions.
@agent - Direction 1, batch: one command processes a past time window (GDELT download, story grouping, RSS check, Wikipedia check) and writes candidates with scores to SQLite for the admin panel. Quickest and testable on past days, but not real-time, and RSS has no past.
@agent - Direction 2, live: a loop every 15 minutes keeps a rolling 72-hour window, and a daily Wikipedia check runs on yesterday's candidates. Shaped like the product, but more moving parts and slower to debug.
@agent - Recommended building 1 as a single "process a time window" function, so 2 is just that function on a schedule. Start saving the RSS feeds now, since their history cannot be recovered.
@me - Asked for the data structure first. Considered one row per day with JSON for each source, versus separate tables per source plus one cleaned aggregate.
@agent - Recommended separate tables: one row per item for GDELT clusters, RSS items and Wikipedia entries; one events table as the cleaned aggregate that goes out; Wikipedia results kept apart so they never feed into scoring. Raw GDELT stays outside the app database.
@me - Created a planning folder in phase 2, where each thread writes its own schema, so Claude and Codex can see each other's work. The shared point is the events table.


# 3. Codex thread: users and notifications

@me - Asked how much notification infrastructure the homework needs, then focused on the user side while Claude handles sending and admin.
@agent - Suggested Slack webhooks and SMTP with Mailpit, a local inbox that captures email without external delivery.
@me - Clarified that clients supply Slack webhook URLs; our application only sends the HTTP request.
@agent - Added subscriptions and per-user filters to the proposed schema.
@me - Challenged that: the brief does not require subscriptions. Keep users, enabled destinations and deliveries; the system chooses the important events.
@agent - Accepted the correction. It had turned an optional interpretation into a requirement.
@me - Codex's overview was too detailed. Asked it to use Phase 1 as the reference and make that a reusable skill for both agents.
@agent - Created one shared skill, linked for Claude and Codex, with reminders in CLAUDE.md and AGENTS.md. Shortened the overview accordingly.


# 4. Stack choice

@agent - Both threads proposed Python, FastAPI and SQLite, largely separately but with the existing Python processing work as shared context.
@consideration - Python follows naturally from the initial data processing. Agreement between the agents is useful, but not an independent comparison of stacks.
@me - Accepted the stack for V1.


# 5. Collector POC on real data

@me - Chose the approach for the Claude thread: build a quick POC first (initial schema, tables, collector), run it on real data, see the outcome, then adjust.
@me - Wanted to start with Wednesday 4 November, since Wikipedia lags.
@agent - Checked what each day has. RSS has no history, and the only snapshot covers Thursday 5 November best (about 130 items, versus about 28 for Wednesday); Wikipedia already lists 16 entries for Thursday.
@me - Chose Thursday 5 November as the first test day.
@me - Briefly considered keeping the collector tables in a separate database until both sides were ready, then decided on one shared database.
@agent - Put the collector tables on the shared schema and checked them in a throwaway database: all tables are created, deliveries link to events, and the user-side tests still pass.
@agent - First run on Thursday: 2,591 stories, 2 selected for sending, 35 for review; 12 of the 37 found on Wikipedia. The top stories were real. Weaknesses: keyword-based headlines when no RSS article matches, some junk clusters, and the Wikipedia check misses stories that started a day earlier.
@consideration - The two sides could stay a wireframe for now and be put together in a final phase.
@agent - Challenged that: the sides already share the database, so one hand-off test would show now whether the seam works, instead of finding problems in the last phase.
@me - Asked Claude to take over both threads and make phase 2 work end to end.
@agent - Ran it on a separate test database: test user, email destination, collector, dispatcher, Mailpit as the local inbox. Both selected stories arrived as emails; a second dispatcher run sent nothing new.
@agent - The emails exposed one more weakness: the source links are syndicated copies from UK local sites, although BBC and Guardian articles confirmed the stories.
