# Codex thread (level 2)

My prompts, polished for grammar only, with each Codex response condensed to a few lines.
Full, unedited version: 3-transcripts/codex-app-check.md (continues the earlier Codex session, from its 26th prompt).


@me (1): One last task, Codex: take the reviewer's role. Set up the infrastructure in a separate environment based on the READMEs, and first tell me whether the instructions are clear.
@agent: The README is understandable and startup works in a fresh, isolated environment: build, database setup, web, collector, dispatcher and Mailpit all running. The first live collection stored 300 events (2 automatic, 30 review). Approved one review candidate in the admin view; its email arrived once. 50 tests and lint passed.
  Two issues: the admin overview showed Wikipedia matches as "True of 32" instead of "16 of 32", and Compose did not forward the documented collector settings. No fixes made; report, logs and screenshots in artifacts/codex-startup-review/.

@me (2): Write the notes of your app check into the phase 4 overview.
@agent: Added them to section 6 of the overview.
