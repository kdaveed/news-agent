# Approach B: structured keys

Run: `uv run python approaches/b_structured_keys/run.py` (about 14 s). Passing `key=json` arguments
overrides PARAMS for experiments and skips writing `stories.json`.

## Idea
Stories are built only from GDELT's **structured event fields**: ActionGeo, CAMEO actor codes,
QuadClass and time. No article text and no shared URLs are used for grouping. The `mentions`
table is used for scoring (who covered it, when), for deciding which cells are "solid", and for
choosing which URLs feed the shared `story_keywords` labeller.

### 1. Cells
event → `(location, unordered actor pair, family)`
- location precision follows `ActionGeo_Type`: city/landmark (3,4) → 0.25° grid cell; state (2,5) → ADM1; country (1) → country. Ungeocoded events (type 0, 2.6%) are dropped.
- actor = CAMEO code (`USAGOV`, `IRNMIL`, ...). Role-only codes with no country (`GOV`, `COP`, `CVL`) get the location's country as a namespace (`NGA/COP` ≠ `USA/COP`).
- ActionGeo uses FIPS country codes and actors use ISO3. I map between them from the data: each ISO actor's home is the FIPS country where it is most often located, and each FIPS country takes its most frequent home actor. A plain per-FIPS argmax was a bug: it mapped India to USA, because the US is the top actor almost everywhere. 177 of 234 FIPS codes get mapped. The rest keep their FIPS code, so in those mostly small countries domestic actors count as informative.
- family = coop (Quad 1–2) / conflict (Quad 3–4).
- `EventDay < 20261026` is dropped. That removes the ~3.3k retrospective and "one year ago" (2025) events.

### 2. Linking (union-find, solid cells only = ≥3 independent voices)
An actor is **informative** at a location if it is foreign to the location's country. Plain
domestic codes don't count, and neither do their sub-roles (`USAGOV` at Washington) or role-only codes. A cell with no informative
actor is **generic**.
- `G_loc`: generic cells at the same non-capital point → one "what happened in Palm Beach" story.
- `G_nat`: generic cells at ADM1/country precision, or at the country's busiest point grid (≈ capital, where national news gets geocoded) → one "national domestic" story per country.
- `E_dyad`: international cells with the same set of involved countries (location country ∪ informative actors' countries), anywhere. For example US–Iran cells at Tehran and at Washington.
- `E_actor`: same non-capital point plus the same informative actor, only for cells that name exactly one foreign actor.

### 3. Co-burst pass
After linking, bursty components (≥10 voices, ≥50% of them within 12h of onset) are merged when their
onsets are within 2h and their source-weighted centroids are within 500 km. The pass is non-transitive: each
component joins the largest compatible earlier anchor. It is meant for one breaking event that
GDELT geocodes to several nearby places (airport / county / neighbouring country).

### 4. Scoring
- **Independent voices**: an outlet counts if it has at least one *own* text in the story. Syndicated copies are texts with identical `MentionDocLen` and `MentionDocTone` in more than one outlet. For outlets that only republished wire copy, the story gets one voice per distinct syndicated text, capped at the number of such outlets. `iheart.com` is excluded.
- `score = voices × (0.5 + 0.5 × fast_share)`. `fast_share` = share of voices whose first mention falls within 12h of onset. Onset = time of the 3rd voice.
- Labels: `story_keywords` gets the story's **core URLs**: articles where at least 50% of their events belong to the story (falling back to all URLs if fewer than 5). `sample_urls` are the top core URLs.

## Data findings that shaped the design
- **Syndication is huge**. Of about 100k distinct (DocLen, Tone) texts, 150 are carried by more than 50 outlets each, up to 145 (Newsquest's ~144 UK local sites republishing PA copy; Hearst TV stations republishing one campaign piece). Raw distinct-source counts therefore reward wire stories (Ryanair bomb threats, Karl Bushby) with about 150 "outlets" from 4–6 events. Collapsing syndication changes 43% of the top 100.
- Articles that mention 200+ events are mostly one big story syndicated (the Russian strike on a Ukrainian aid site). So they were *not* dropped. They hurt labelling, not grouping, which is why the core-URL labelling exists. Before that change, keywords of unrelated clusters were dominated by midterm/Iran round-ups ("iran trump midterm war" on the Tehran, Israel and Japan clusters).
- One crash (a Bahamas-registered Learjet, Florida) is coded at 28 distinct locations, including "Texas", with actors BHS/USA/roles. That shows how inconsistent GDELT's structured fields are for a single event.
- Many components have onset at 00:00 on Nov 2, because the story started before the window. Velocity is censored for them.
- The mentions table has 45k mentions of events that are not in `events` (added before the window). Approach B can't use them, since they have no structured fields.

## Sanity checks (numbers from the final config)
- 120,218 cells, 20,437 solid; unions: G_loc 4,475, G_nat 8,325, E_actor 1,513, E_dyad 3,120, co-burst 163. 2,832 stories with ≥3 voices.
- Story size (voices): <10: 1,949 · 10–29: 481 · 30–99: 298 · 100–299: 82 · 300–999: 20 · ≥1000: 2.
- Largest story = US national domestic blob: 4,330 voices, 48k events, 7% of all story voices. It is essentially the midterms ("election senate trump midterm democrats race house").
- Keyword-Jaccard ≥0.4 duplicates in the top 100: 3 (all the Florida Learjet crash; Iran/Qeshm strikes). This **understates** fragmentation. Reading the top 40 by hand, the Iran war is spread over about 5 entries (#3 Iran domestic, #4 US–Iran, #15 Israel–Iran, #23 Qeshm, #36 Iran–Qatar), Israel over 3–4, Russia/Ukraine over 4–6, and the crash over 3.
- URL purity (share of sample URLs containing one of the story's top-3 keywords), top 50: 0.45.
- Runtime ≈ 14 s.

### Ablations (top-100 overlap with the default, by label)
| variant | stories | top-100 overlap | kw-dups | purity | note |
|---|---|---|---|---|---|
| no co-burst | 2995 | 92 | 3 | 0.44 | small effect; merges look plausible (Basij→Iran, Austin airport→Texas) but some are dubious (West Point NY→Washington) |
| family_split (never cross coop/conflict) | 3758 | 36 | 6 | 0.38 | splits one story into coop and conflict halves; rejected |
| no syndication collapse | 3131 | 57 | 9 | 0.46 | wire stories inflated |
| velocity w=0 / w=0.8 | 2832 | 92 / 92 | 4 / 4 | 0.44 / 0.45 | ranking fairly robust to w |
| no G_nat (generic per location only) | 10513 | 38 | 9 | 0.39 | midterms split into 10+ state blobs in the top list |
| no E_dyad | 5628 | 62 | 5 | 0.50 | international stories more fragmented |
| E_actor at any cell/capital | 2336 | 70 | 1 | 0.43 | a 28k-event mega cluster (Iran+Ukraine+Israel+US) at #2; rejected |
| domestic sub-roles informative | 2909 | 69 | 4 | 0.42 | `USAGOV` at Washington becomes a hub |
| grid 0.5° | 2749 | 77 | 3 | 0.44 | |
| min_cell_sources 5 | 11126 | 56 | 3 | 0.47 | more singleton fragments |

## Tried and rejected
- **(loc, actor pair, family) with merging on shared location + any actor** (the starting idea). Every city collapsed around its domestic actor (`USA` at Washington, `IRN` at Tehran). The top 40 held about 10 state-level midterm fragments plus role-only "?" blobs from ungeocoded events.
- **Rare-actor rule** (an informative actor seen at ≤6 locations links all its cells). It bridged hubs: one rare actor present at both Tehran and Washington merged them. Dropped.
- **E_pair** (same two foreign actors within one country). Subsumed by E_dyad.
- **Co-burst by "same primary country"**. Merged unrelated US stories that started together (and every pre-window story with onset at 00:00). Only geographic proximity is used now.
- **Co-burst by shared informative actor**. Merged Western Sahara with Bihar via the `USA` hub actor.
- Per-FIPS argmax country mapping (bug, see above).

## Known weaknesses
- **Fragmentation of mega-stories** is inherent to structured keys. GDELT codes one geopolitical story as many (location, actor) combinations, and every rule that merges them also creates hubs. I chose to accept duplicates over giant mixed clusters, so the top list holds several Iran, Israel and Ukraine entries.
- **National and city "blobs"** (UK, China, France, Canada, Houston, Dallas, ...) are mixtures of a country's or city's domestic news. They rank from volume alone. Velocity only partly demotes them. Their core-URL labels show they are incoherent (e.g. GBR–USA dyad → "species ant rarest nest").
- No time splitting: a dyad or a location that hosts two different stories in 72h stays one story.
- Syndication detection by (DocLen, Tone) misses lightly edited wire copy. It could also merge two genuinely different texts with the same length and tone (unlikely).
- Velocity is censored for stories that began before the window, and blobs trivially "start" at 00:00.
- The capital heuristic (busiest point grid of a country) is crude. For Israel it picks Gaza.
- Roughly 57 FIPS countries without a learned ISO mapping treat domestic actors as foreign.
