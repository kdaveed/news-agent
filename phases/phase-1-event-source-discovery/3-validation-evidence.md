# Validation evidence (phase 1)

The checks run on AI output, and what they changed. "Where" points to the section in the full transcript (3-transcripts/).


# Checks on claims

Claim: RSS can give 6 months of history.
Check: queried Wayback CDX and fetched a snapshot. Result: patchy snapshots, one with 0 items. RSS rejected as the starting point.
Where: claude-main.md, User 2

Claim: GDELT, USGS, GDACS and Wikipedia have usable history.
Check: live API calls. Result: USGS 4,230 events M4.5+ in 6 months; GDELT file list live; NWS only recent; Guardian demo key rejected.
Where: claude-main.md, User 2

Claim (own estimate): the 3-day download is 150-250 MB.
Check: measured from the GDELT file list. Result: 54 MB. Estimate corrected.
Where: claude-main.md, User 6

Claim (sub-agent B): wire syndication inflates outlet counts.
Check: independent DuckDB query on identical document length and tone. Result: confirmed, up to 145 outlets per copy, 133 groups.
Where: claude-main.md, background agent finished 19:34 UTC

Claim (sub-agent C): shared keywords are non-deterministic, data is English-only, a symlink is not ignored.
Check: ran with 3 hash seeds; counted translated mentions; checked git status. Result: all three confirmed and fixed. Corrected an earlier "many languages" claim.
Where: claude-main.md, background agent finished 19:49 UTC

Claim (own): low recall is because data is missing ("it needs more sources").
Check: searched article URLs for the 18 stories every approach missed. Result: most are in GDELT with 15-40 outlets. It is mostly a ranking problem; claim corrected.
Where: claude-main.md, User 11

Claim (Codex): five RSS feeds work and overlap with GDELT.
Check (by Codex): live fetch and parse; URL match against the GDELT data. Result: 126 items; 11 of 17 in-window items in GDELT. Codex fixed its own parser error (image metadata counted as article content).
Where: codex-2-collection-options-and-rss.md, User 2


# Checks on our own tools

Data load: checked event codes and categories for column shifts, nulls and time range. Clean.
Where: claude-main.md, User 6

Evaluator v1: ran a no-grouping baseline to see whether fragmentation is detected. It was (11 copies of one story in the top 20). An audit then found generic-word false matches ("killed" + "nine"); fixed, recall 0.42 -> 0.16.
Where: claude-main.md, User 6

Evaluator v2: an audit of all matches found more false matches ("become", "voter", "county"). Measuring rarity on news URLs did not help, so a shared proper name is now required. Remaining errors are documented.
Where: claude-main.md, background agent finished 19:49 UTC

Approach A parameter: swept J = 0.1 / 0.2 / 0.35 using internal checks only (cluster sizes, duplicates), not the answer key.
Where: claude-main.md, User 6

Reproducibility: re-ran all approaches from main after merging the agent branches.
Where: claude-main.md, background agent finished 19:49 UTC


# Guarding the comparison

Answer key held back: sub-agents were started fresh (not forked) and told not to read it; evaluator outputs quoting it were removed from git before they started; their code was grepped for references afterwards (none).
Where: claude-main.md, User 6 and background agent finished 19:34 UTC; sub-agent transcripts
