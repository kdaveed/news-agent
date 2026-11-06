# News alerts: from a vague brief to a working system

Brief: task-04-feature-design-and-build.md. Users set up alerts for important world events (breaking news, market moves, disasters), delivered by email and Slack, with room for more channels and an admin view.

This repo documents how I directed AI agents (Claude Code, Codex) through the work. The process is the submission; the code is evidence.


# How I worked: four phases

Phase 1 - tackling the core problem: event source discovery (phases/phase-1-event-source-discovery/)
  The brief leaves open what counts as "important", so I started with the data, not the app: how do we find reliable sources, and how do we aggregate them?
  I ran two agents in parallel, Claude and Codex, each researching from its own start. Claude checked candidate sources live and, at my request, tested three GDELT algorithms with sub-agents against Wikipedia; Codex independently researched collection options and found concrete free RSS feeds.
  Bringing both threads together gave the three sources and their roles: GDELT detects how widely a story is covered, RSS (five publisher feeds) confirms it, and Wikipedia Current Events checks the result afterwards.

Phase 2 - the POC: making the parts work together (phases/phase-2-implementation-v1/)
  Claude built the data collector (GDELT + RSS into scored events) and Codex the users, notification destinations and delivery, both on one shared database planned in a common folder.
  I kept the scope small (no subscriptions: the system picks the events, users choose where they go) and closed the phase with one end-to-end test: real stories from Thursday 5 November reached a local inbox.

Phase 3 - a night agentic session that finished the work (phases/phase-3-final/)
  I set guardrails (no secrets, fetch-only network, no commits until the end) and left the agents working overnight.
  Codex reviewed the whole repository; Claude verified every finding before fixing it, while sub-agents built the admin view and the Docker setup. A fresh agent then reviewed the result, and the fixes were checked on real data, not only in tests.

Phase 4 - the morning review: testing and final thoughts (phases/phase-4-review/)
  With a fresh head I walked through the night's work and the data flow: what each source delivers, how the sources are joined, and how reliable each join is.
  Codex took the reviewer's role and ran the system from the READMEs in a separate environment; its two findings were fixed and verified. The demo was switched to live collection, and the session closed with the conclusion below.


# Process logging

Every phase folder documents how the work was done, at three levels of detail:

1 - overview (1-overview.md): the story of the phase in short @me / @agent / @consideration lines: what I asked or decided, what the agents produced, and my reasoning. Start here.
2 - threads (2-claude-thread.md, 2-codex-thread.md): my prompts, polished for grammar only, with each agent response condensed, one file per AI thread.
3 - evidence: 3-transcripts/ holds the exact sessions exported from the Claude Code and Codex logs; 3-validation-evidence.md (phases 1 and 3) lists the checks run on AI output and where to find them in the transcripts. Phase 1 also keeps my own unedited working notes (3-transcripts/my-working-notes.md).

Alongside the levels, a phase folder can hold:
  artifacts/ - write-ups, reviews and screenshots produced during the phase.
  planning/ - shared plans between the agents (phase 2).
  research/ and scripts/ - experiment code, evaluator and results, and the transcript export tools (phase 1).
src/ holds the product code.


# Run it

One command, local (needs uv; Docker only for the Mailpit inbox):

  scripts/demo.sh

It builds a fresh demo database and runs one live collection cycle: polls the 5 RSS feeds, fetches the last 24 hours of GDELT and the Wikipedia check, sends the selected stories to Mailpit (http://127.0.0.1:8025) and prints how to open the admin view. Stories differ each day; the summary also lists review candidates.

Everything in containers (web, collector, dispatcher, Mailpit):

  NEWSALERT_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))') docker compose up

Details: src/README.md (application), scripts/README.md (demo). Reviewer's checklist: REVIEW-ME.md.


# Conclusion

Two separate agents (Claude and Codex), working in parallel, arrived at the three sources that fit this problem best: GDELT to detect how widely a story is covered, RSS to confirm it, Wikipedia to check afterwards.
On that basis we built the system end to end, from collection to the inbox, and made it more robust through independent agent reviews whose findings were verified before fixing.
What makes it reliable from here is method: manual work, looking through the data and labelling it, and cheap AI checks on the uncertain joins and verifications, each measured against those labels.
