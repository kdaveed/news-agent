# Phase 3 overview: final pass overnight

Closing the gaps of the phase 2 POC while I slept, with agents reviewing each other's work.
@me = what I asked or decided. @agent = what an agent produced. @consideration = my reasoning at that point.


# 1. Setting up the night

@me - Asked for an overnight job that leaves the homework submittable after a 10-15 minute review in the morning: finish code, flow and documentation, reviewed by other agents, without me approving each step.
@me - Set the rules: no secrets sent anywhere, no outgoing POST requests (only fetching), commit at the end.
@agent - Set a local allow-list so the work would not stall on prompts, with git commit, push, reset and rm -rf blocked until the end.
@consideration - Unattended agents need explicit guardrails; I could not watch them.


# 2. Independent review first

@agent - Ran Codex as a read-only reviewer of the whole repo against the brief. It reported missing pieces (admin view, continuous collection, a demo) and six code risks.
@agent - Checked every Codex finding against the code before fixing. All six held up; five were fixed, one (test emails to any address) documented. Two would have silently produced wrong alerts: event ids changed between runs, so a story could be sent twice; syndicated copies on the same three sites could count as a hundred outlets.
@agent - Stopped using Codex after my no-POST rule, since it sends the repository to an external API. Its log showed it had not read the .env file.


# 3. Fixes and the missing pieces

@agent - Fixed the collector: stable event ids across overlapping windows, stricter outlet counting, URL matching that keeps article ids, junk id words filtered, readable fallback headlines, RSS links first in emails, a wider Wikipedia window.
@agent - Added a continuous collector worker, the admin view (runs, candidates with evidence and the Wikipedia check, delivery log, select or drop a review event), Docker Compose and a one-command demo. Sub-agents built the admin view and the Docker setup in parallel; I finished the admin view after it was stopped halfway.
@agent - Checked the fixes on real data, not only in tests: two overlapping windows on Thursday reused 210 events and kept both selected stories with the same ids; Wikipedia agreement rose from 12 of 37 to 18 of 31 events.
@agent - Tested that the new tests can fail: with cross-run matching switched off, the identity test fails as it should.
@agent - A fresh sub-agent reviewed the whole change. It found no security problems, but the continuous worker would have filled the disk and slowed down over days, and growing stories could still be sent twice. All eight findings were verified and fixed; one new test exposed a bug in the fix itself.


# 4. Scope decisions

@consideration - Market movements and natural disasters are reached through general news coverage, not dedicated feeds. A market-data source (price thresholds) and USGS/GDACS for disasters are the next sources to add; they were out of reach in the time budget.
@consideration - A new channel still touches four small places (adapter, API type, database constraint, form). Documented instead of refactored.


# 5. Takeaways

- An independent reviewer found real bugs the builders missed; verifying its findings before fixing kept the false ones out.
- Real-data checks caught what unit tests would not, such as how many events a second window reuses.
- Guardrails have to be set before leaving agents alone: what they may change, what they may send, and what they must never touch.
