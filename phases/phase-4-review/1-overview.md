# Phase 4 overview: morning review

Reviewing the overnight work with a fresh head: findings, setup checks and small fixes.
@me = what I asked or decided. @agent = what an agent produced. @consideration = my reasoning at that point.


# 1. Walking through the night

@me - Asked how the night went, who did the reviews, and which bugs were found exactly.
@agent - Two reviewers: Codex before the fixes (six code risks, five fixed, one documented) and a fresh Claude sub-agent after them (eight findings, all fixed, no security problems). Details in phases/phase-3-final/3-validation-evidence.md.
@me - Asked what the last phase taught about data collection.
@agent - The same story reappears in every rolling window, so its id must come from shared articles; syndication inflates coverage; RSS matters for presentation as much as for confirmation; Wikipedia lists stories on the day they began; selection is strict and tuned on one day only; RSS barely moves at night.


# 2. Understanding the data flow

@me - Trying to get a clear picture of the data flow: what the raw data is from each source, how the outlets are joined, and with what confidence the same event is recognised across the three sources.
@agent - GDELT gives article URLs only (no text), so a story is built from them; RSS items and Wikipedia entries arrive as finished units. Only URL-based links are reliable (RSS by URL, run to run); word-based links (story grouping, RSS by words, Wikipedia) are plausible but unmeasured.
@consideration - Wikipedia's own news citations are thrown away today; matching them by URL would make the check much stronger.
@me - Came back to the LLM idea from the beginning: where could AI make the join more reliable, verifying that articles from different outlets and sources report the same event, while staying cost efficient?
@agent - Use it only on the uncertain joins at the narrow end of the funnel, never on raw GDELT:
  Is this candidate one event? Given a story's ~10 headlines, the model says whether they describe one event or several (about 35 stories a day).
  Does this RSS article report the same event as this story? A yes/no check for the word-based matches only; URL matches stay as they are (about 50 pairs a day).
  Which Wikipedia entry matches which event? One call per day, replacing word overlap as the judge.
  Helping the admin on review stories, and labelling categories (breaking, market, disaster).
@agent - About 1-2 cents a day with a small model. Keep the rules as the fallback, store each AI decision with its reason, and measure against about 50 hand-labelled pairs before trusting it.


# 3. Admin panel

@me - Opened the admin panel on the demo data.
@me - Noticed that admins and users are the same entity: an admin is a normal user listed in a setting. Not fixing it in the POC, but noted as a limitation.


# 4. How a reviewer gets data

@me - Asked how a reviewer would run the containers and get data in; suggested a seeder with our current database content.
@agent - Found that the demo depended on an RSS snapshot that is not in the repository: on a fresh clone it would select nothing and send no email. A seeder would also republish publisher text.
@me - Preferred fetching, since it shows the data collection itself.
@agent - Changed the demo to one live cycle (RSS now, last 24 hours of GDELT, Wikipedia check), kept the Thursday replay as an option, and verified it: 2 stories selected and delivered to the local inbox.


# 5. Keeping the record clean

@me - Wanted the overnight session to stay untouched as its own commit, with this review as a separate one.
@agent - Had added the morning notes to the phase 3 files; restored them and moved the notes here instead. The overnight commit itself was never changed.


# 6. Final word

@me - Had Codex review the code and the setup for the reviewer as a last check.
@agent - Followed the READMEs in a separate environment, with a fresh database and isolated containers. Startup worked; 50 tests and lint passed.
@agent - The live collector stored 300 events. Approved one review candidate through the admin view and verified that it reached Mailpit once and appeared in user history.
@agent - The browser check caught a bug the tests missed: Wikipedia matches displayed as "True" instead of 16. Also found that Compose does not forward the documented collector settings.
@agent - Recorded the findings, startup logs and screenshots in [the app-check report](artifacts/codex-startup-review/README.md). No application fixes made during the review.
@agent - Claude then fixed both issues (the Wikipedia count in the admin overview, with a test; the collector settings in Compose).
@me - Asked Codex to finish and verify the fixes, and record the result here.
@agent - After Claude fixed both issues, Codex reran the full test suite, including local email delivery, and rechecked the dashboard and collector settings in the running containers. All 55 tests and lint passed; both fixes worked, with no new issues found in those checks.
@me - Conclusion: two separate agents found the three best sources for this problem, and we built the system end to end and made it more robust. Reliability from here needs manual work, looking through the data and labelling it, plus relatively cheap AI-driven checks and verifications, measured against those labels.


# 7. Next steps from the review

- Match Wikipedia citation URLs against GDELT and RSS articles.
- Measure the word-based joins against about 50 hand-labelled pairs; add the LLM checks (one event? same event as this RSS article?) where they beat the rule.
- Separate admins from users.
- Tune the thresholds on more days, now that the RSS poller has started collecting.
