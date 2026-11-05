# News alerts: from a vague brief to a working approach

Brief: task-04-feature-design-and-build.md. Users set up alerts for important world events (breaking news, market moves, disasters), delivered by email and Slack, with room for more channels and an admin view.

This repo documents how I directed AI agents (Claude Code, Codex) through the work. The process is the submission; the code is evidence.


# The story so far

The brief leaves the hardest question open: what counts as important, and where does it come from? So I started with the data, not the app.
Claude checked the candidate sources live. Only GDELT measures how widely news is covered, across all topics, with history to test against. Codex, run in parallel from scratch, reached GDELT too.
I asked Claude to try several GDELT algorithms in parallel with sub-agents, compared against Wikipedia. None clearly won, and the approach proved more fragile than it first looked: GDELT alone is not enough.
Codex then found five free RSS feeds that work right away. Merging the two threads gave the source roles: GDELT detects, RSS confirms, Wikipedia checks afterwards. Precision first: fewer alerts, but accurate.


# Where to start

Each phase has three levels:
1 - overview: short and human-readable. Start here.
2 - threads: my prompts (grammar polished) with condensed agent responses, one file per AI thread.
3 - transcripts: the exact sessions, exported from the Claude Code and Codex logs.
    3-validation-evidence.md lists the checks run on AI output and where each one is in the transcripts.
    3-transcripts/my-working-notes.md holds my own unedited notes from the phase.


# Phases

Phase 1 - event source discovery: phases/phase-1-event-source-discovery/
  Which free sources can tell us what is important, and how we check it.
  Outcome: GDELT detects, RSS confirms, Wikipedia checks.


# Other folders

Each phase folder also has:
  artifacts/ - research write-ups and decisions produced during the phase.
  research/ - experiment code, dataset scripts, evaluator and results.
  scripts/ - transcript export tools used for level 3.
src/ - product code.
