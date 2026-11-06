# Claude thread (level 2)

My prompts, polished for grammar only, with each Claude response condensed to a few lines.
Full, unedited version: 3-transcripts/claude-main.md.


# 1. Walking through the night

@me (1): How is it going? Walk me through how you got there. Who did the review again, and what bugs were found exactly?
@agent: All work was in one commit; the RSS poller was still running. Two reviewers: Codex before the fixes (six risks, five fixed), a fresh sub-agent after them (eight findings, all fixed, no security problems). Listed each finding.

@me (2): Go into the data collection part. What findings did you come to during the last phase?
@agent: The same story reappears in every rolling window, so ids must come from shared articles; syndication inflates coverage; RSS matters for presentation; Wikipedia lists stories on the day they began; selection is strict and tuned on one day; RSS barely moves at night.


# 2. Data flow and AI

@me (3): How exactly does the unification work, and with what confidence are events from the three sources the same? Does Wikipedia contain one news link per event, or several? Walk me through the raw data concisely.
@agent: GDELT gives article URLs only, RSS gives finished articles, Wikipedia gives one sentence per event with 1-2 news citations. Only URL-based joins are reliable; word-based joins are unmeasured. Wikipedia's citations are thrown away today.

@me (4): At the beginning we talked about LLM-based matching. Where could AI make the system more reliable while staying cost efficient?
@agent: Only on the uncertain joins at the narrow end: is this candidate one event, does this RSS article report the same event, which Wikipedia entry matches, help for the admin. About 1-2 cents a day; measure against hand labels first.


# 3. Admin panel and reviewer setup

@me (5): Can you show me the admin panel? Give me a link.
@agent: Started the web app on the demo database and gave the login and admin links.

@me (6): Admins and users should be different entities; right now they are mixed. Don't fix it in the POC, but note it.
@agent: Noted as a known limitation, without code changes.

@me (7): Are there instructions for running the code and the containers? How does a reviewer get data in? A seeder with our current database content would be good.
@agent: Found that the demo depended on an RSS snapshot that is not in the repository, so a fresh clone would send no email. A seeder would also republish publisher text.

@me (8): Then fetching is more elegant, since it shows the data collection too.
@agent: Changed the demo to one live cycle, kept the Thursday replay as an option, and verified it: 2 stories delivered to the local inbox.


# 4. Keeping the record clean (summary)

@me: Wanted the overnight commit untouched and this review as a separate commit, with an overview of the session, a final word, and a two-sentence-per-phase summary in the README.
@agent: Moved the morning notes out of the phase 3 files into this phase, wrote the overview, the README story and the conclusion. After Codex's app check, fixed its two findings.
