# 4. Three story-detection approaches on 3 days of GDELT: comparison

Window: 2026-11-02 to 2026-11-05 UTC (347,809 events, 953,494 mentions, 150,119 articles; English GDELT stream only).
Answer key: Wikipedia Current Events, 38 entries in the window. Details in `research/` (contract, code, NOTES per approach).

## Setup (why it is fair)
- Shared data, shared keyword labelling (`story_keywords`) and a shared output format. Only grouping and scoring differ.
- B and C were built by separate agents in git worktrees, starting from fresh context. They were not allowed to see the answer key or run the evaluator. A (main agent) had already seen the key, so its single parameter was chosen from internal checks only. All approaches were evaluated once, together.
- Every approach was re-run from `main` after merging, to check reproducibility (runtimes: A 18 s, B 15 s, C 45 s).

| | Grouping idea | Score |
|---|---|---|
| baseline | none (one GDELT event = one story) | distinct sources |
| **A** mention graph | events linked if they share articles (Jaccard ≥ 0.2), connected components | peak distinct sources per day |
| **B** structured keys | (location, actor pair, coop/conflict) cells, merged by rules | independent outlets × speed |
| **C** article text | articles clustered by URL slug words (TF-IDF, online, 24 h), repair passes | independent voices + 12 h burst |

## Results (strict matching)
| approach | P@10 | P@20 | P@50 | R@50 | dup@20 | threads@20 |
|---|---|---|---|---|---|---|
| baseline | 1.00 | 0.80 | 0.70 | 0.16 | 14 | 2 |
| A | 0.80 | 0.75 | 0.68 | 0.21 | 12 | 3 |
| B | 0.60 | 0.65 | 0.58 | 0.29 | 6 | 7 |
| C | 0.80 | 0.60 | 0.62 | 0.26 | 6 | 6 |

How to read it: precision is easy to score well on (big stories are always on Wikipedia). Recall at 50, and the number of distinct story threads in the top 20, are what separate the approaches. B's numbers are inflated by residual false matches from its multi-topic "national" groups (e.g. #17 "ant nest…" matched the Binance hack via mixed keywords). With that taken into account, **B and C are roughly tied, and both beat A and the baseline on variety**.

## What we learned
1. **Grouping is necessary.** Without it, the top 20 is mostly one story: 11 copies of the Florida jet crash and 3 distinct threads.
2. **Wire syndication is the biggest data quirk.** Found by B and C, then verified independently: identical PA articles appear on up to 145 Newsquest sites, in 133 groups of more than 50 outlets. Raw "distinct sources" counts are badly inflated, so scoring must count **independent voices**. A doesn't do this yet.
3. **Each approach fails in a different way:**
   - A chains stories together through bridging events, or splits them, depending on J.
   - B fragments geopolitics (Iran appears ~5×) and lumps unrelated national news into one story.
   - C produces the most coherent stories (median URL purity 0.97) but can't tell "same event" from "same topic" (half its top 100 are midterm sub-stories).
4. **Recall is limited by the data, not by the clustering.** 19 of 38 entries were missed by *all* approaches: Haiti, Sudan, Colombia, Nigeria, Peru, Somalia, Bangladesh and similar. These get little English-language coverage. Coverage-based importance plus the English-only stream structurally under-ranks them.
5. **Product question surfaced:** the US midterms are one topic with dozens of real sub-stories. Should that be one alert, a digest, or one per race? That's for the PM, not for the algorithm.

## Recommendation for the next iteration
A **hybrid**:
- C's article-text clustering for coherent stories.
- A's shared-article links as a second pass, to merge sub-stories into threads.
- Independent-voice scoring with syndication collapse (B/C).
- Add the GDELT **translation** stream to address finding 4.

Evaluate the hybrid against the same harness.

## Corrections and self-checks along the way
- **Download size** was estimated at 150–250 MB; measured 54 MB.
- **Evaluator v1** let generic words ("killed" + "nine") create matches. After adding a rare-word rule and best-match-only scoring, baseline recall went from 0.42 to 0.16.
- **Evaluator v2** measured rarity on only 61 entries, so "voter", "become" and "county" counted as rare. Measuring rarity over news URLs didn't help either ("learjet" is as frequent as "become"). The final rule requires a shared **capitalised name** from the Wikipedia sentence. Residual false matches remain and are noted above. The original threshold sweep (T) turned out to have no effect and was replaced by strict vs lenient matching.
- **Shared-code bugs found by agent C and verified:** `story_keywords` was non-deterministic (tie order depended on the hash seed; fixed), and `.gitignore` missed the `data` symlink (fixed). It also pointed out that the data is English-only (true: translated articles come in a separate stream we didn't download). This corrects an earlier claim of mine that GDELT covers "many languages" in our data.
- **Contract gap found by agent B:** the loader dropped `ActionGeo_FeatureID`.
- **Answer-key leak risk:** the first commit included evaluator outputs quoting the answer key. They were untracked before the agents started and are committed only now.
- **Worktree base:** the agent worktrees were created from the commit *before* `research/` existed. B fast-forwarded; C copied the shared files by hand (left uncommitted). Both final commits were cherry-picked onto `main` and re-run there.
