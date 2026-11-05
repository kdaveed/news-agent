# Phase 1 overview: event source discovery

Based on my working notes (3-transcripts/my-working-notes.md), the Claude thread and the Codex threads.
@me = what I asked or decided. @agent = what an agent produced. @consideration = my reasoning at that point.


# 1. Claude attempt

@me - Gave Claude the brief. Asked it to start with where the news comes from and how to judge it.
@agent - Checked sources live:
  RSS: only the latest items, no history.
  GDELT: worldwide news coverage, every 15 minutes, history back to 2015. It counts how many outlets mention each event.
  USGS / GDACS: earthquakes and disasters, already graded by magnitude or alert level, but narrow.
  Wikipedia Current Events: a daily, human-curated list of important events, full history.
@agent - Proposed the key idea: importance is roughly how widely something is covered. Wikipedia could serve as the answer key to test it.
@me - Chose GDELT because it is the only free source that measures coverage across all topics. Left USGS for later.
@me - Asked Claude to run sub-agents in parallel on different directions, with comparable outputs.
@agent - Built three algorithms (one itself, two by sub-agents) and compared them against Wikipedia. None clearly won; each failed differently.
@consideration - The approach turned out more complicated and fragile than first suggested.
@consideration - GDELT alone is not enough, so we need another source on top. Wikipedia can help, but not as ground truth: it comes out late, so it works best as a checker.


# 2. Codex thread

@me - First asked Codex about GDELT processing, but it built on Claude's work in the repo, so I told it to forget the implementation and step back to principles. Then started a fresh thread from the brief.
@me - Ran Codex in parallel while Claude was working on the GDELT algorithms. Gave it the brief from scratch to see what it finds on its own.
@agent - Codex also ranked GDELT first. It recommended RSS too, but without any concrete feeds.
@consideration - Same conclusion as Claude, and the RSS advice was too vague, so I didn't take it seriously at first.
@consideration - When the Claude thread finished, GDELT turned out weaker than expected, even with the Wikipedia check. That made RSS worth a second look.
@me - Asked Codex for concrete RSS feeds, to test them, and to write the results into a doc, knowing the Claude thread would put everything together.
@agent - Probed five free feeds live (BBC, Guardian, DW, France 24, Al Jazeera): they work right away, but have no history, and 11 of the 17 items in our window are already in GDELT.


# 3. Merge

@me - Both threads had delivered. I asked Claude to read the Codex doc, pull out the RSS findings, and give feedback on my idea of combining GDELT, RSS and Wikipedia into the most probable important news.
@consideration - Each source has its own uncertainty and noise, so combining them should reduce it.
@agent - Agreed with the direction, with one caveat: combining only reduces uncertainty if the sources' errors are independent. RSS isn't independent of GDELT (11 of 17 items were already in it). What it adds is different: an editor chose the story, and it has a real headline.
@agent - Proposed roles: GDELT detects and scores coverage, RSS confirms, Wikipedia checks afterwards. Alert only when both GDELT and RSS agree.
@me - Challenged the hierarchy: is Wikipedia the checker only because it's late?
@agent - Two reasons. It's late, so it can't trigger alerts. More importantly, if it were an input, every alert would be on Wikipedia by design and the check would measure nothing. The checker has to be independent.
@me - Decided: GDELT + RSS together as the system, Wikipedia as the checker. Precision first: fewer alerts, but accurate.


# 4. Takeaways

- It is good to have multiple threads on the same question. They reached GDELT independently and caught different things.
- When one agent reaches a long comparison step, start the other agent instead of waiting.
- Before a comparison, tell the agent to return an easy-to-read table with specific comparisons.
- When asking for options, ask for concrete things (named feeds with relevant info), not categories like "RSS".
- Plausible output often hid flaws that only showed up when I asked how it knew.
