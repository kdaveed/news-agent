# Review in 15 minutes

What happened overnight, and what is left for you to decide.


# 1. Read (5 min)

README.md - the story and how to run it.
phases/phase-3-final/1-overview.md - what the night did, in the same style as phases 1 and 2.
phases/phase-3-final/3-validation-evidence.md - what was checked, with numbers.


# 2. Try it (7 min)

  scripts/demo.sh

Then open http://127.0.0.1:8025: two emails (bomb threats across Europe; Russell Brand verdict), with BBC/Guardian links first.
Start the web app with the command the script prints, log in as demo@example.com / demo-password-123, open /admin:
  runs, events by band, one event's evidence and Wikipedia match, the delivery log.
  On a review event, "Select for delivery" works; on a selected one there is no such button (selected is final).


# 3. Decide (3 min)

Commit: everything from the night is in one commit on main, not pushed (see git log). Push when happy.
NEWSALERT_HTTP_USER_AGENT: set it to the repository URL; Wikimedia rejects requests without contact details.
Cleanup, if you like: branch backup-before-squash, .claude/worktrees/, the Mailpit container (docker stop mailpit).


# Known limitations (documented, not fixed)

Market movements and natural disasters come only through general news coverage; no price feed, no USGS/GDACS.
Thresholds (100 outlets + 2 RSS feeds for auto, 30 for review) are tuned on one day only.
Test emails can be sent to any address, without a rate limit.
A new channel touches four small places (adapter, API type, database constraint, form); see src/README.md.
SQLite with three processes is fine for the demo; Postgres is the step up.
RSS history only exists from the overnight poller on, so earlier days have little RSS confirmation.
