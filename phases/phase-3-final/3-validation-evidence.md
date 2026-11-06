# Validation evidence (phase 3)

Checks run on AI output during the night, and what they changed. Full commands and outputs: 3-transcripts/claude-main.md.


# Codex review findings, verified before fixing

Source: artifacts/codex-review.md (Codex, read-only sandbox).

1. Event id changes across windows. Confirmed: the key hashed the alphabetically first URL, while the docs said "earliest". Fixed: key from the earliest article, plus matching by shared articles (at least 3 and 20%) to events of the last 3 days.
2. Outlet inflation. Confirmed with Codex's own probe: 100 syndicated headlines on the same 3 sites gave 100 voices. Fixed: a syndicated copy adds a voice only for outlets not yet counted. Same probe now gives at most 1.
3. URL collisions. Confirmed: /article?id=1 and ?id=2 had the same canonical form. Fixed: identifying query parameters kept, tracking parameters (utm, at_, maca, ...) dropped.
4. Test emails to any address, no rate limit. Confirmed, medium. Not fixed; listed as a known limitation.
5. Syndicated links displace RSS links in emails. Confirmed. Fixed in two places: RSS evidence written first, and the dispatcher orders RSS first.
6. db.init ignored .env. Confirmed. Fixed: it reads the same settings as the app.


# Checks on tonight's own work

Tests: 49 passed, 1 skipped (was 31). New: tests/test_collector.py (12), tests/test_admin.py (6). Ruff clean.
Mutation check: with cross-run matching switched off, the identity test fails, so it tests what it claims.
Real data, two overlapping windows on Thursday (00-24 h, then 06-30 h): the second run reused 210 events; the 2 selected stories kept their ids; no duplicate selections.
Real data, Wikipedia window two days back: agreement went from 12 of 37 to 18 of 31 checked events.
Docker: image builds, init creates all tables, web /health returns 200, one collector worker cycle runs in a container (2,595 stories, 2 auto, 33 review).
Demo script: end to end on a separate database, 2 emails in the local Mailpit; data/newsalert.db unchanged (same size and timestamp before and after).


# Final review by a fresh sub-agent, verified before fixing

Source: a read-only sub-agent reviewing the whole uncommitted change. No security or state-transition defects; checked and fine: admin access, CSRF, autoescaping, webhook masking, selected-is-final, demo isolation, Docker secrets.
1. The worker wrote a new DuckDB file every cycle (about 3 GB a day). Fixed: one rolling file, raw GDELT files older than the window deleted, RSS snapshots kept for 3 days.
2. Cross-run matching re-read every stored URL every cycle and the stored URLs grew without limit. Fixed: only each event's newest cluster is read and keeps its URLs.
3. A story that grew five-fold could get a new id and be sent again. Fixed: the 20% is taken of the smaller cluster. A new test failed at first and exposed a second bug in my fix (matching used only the first 500 URLs); fixed, test passes.
4. A small unrelated cluster could take over an event with 3 shared articles. Fixed: at least 5 shared articles.
5. Compose ports were open on all interfaces. Fixed: bound to 127.0.0.1.
6. Review candidates fell to drop as the window moved, before an admin could look. Fixed: they stay reviewable.
7. Two comments contradicted the code. Fixed.
8. Existing databases lacked the new column. Fixed: db.init adds it; data/newsalert.db was upgraded with its user and 161 RSS items intact.

After the fixes: demo end to end again (2 emails, BBC and Guardian links first), admin pages on the demo data (a selected event has no select button, a review event has one).

# Guardrails

Codex runs stopped after the no-POST rule (it sends the repository to an external API). Its run log was checked: it did not read the .env file.
Network use was fetch-only: GDELT files, RSS feeds, Wikipedia API, Docker images. Email went only to the local Mailpit; no Slack request was made.
