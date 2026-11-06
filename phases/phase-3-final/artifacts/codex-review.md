**1. Gaps against the brief**

This is a credible POC with strong process evidence. The largest remaining gaps are the admin view, continuous collection, and evidence that event selection works beyond one day.

Severity: **High** affects a core requirement or alert correctness; **Medium** limits reliability or demonstrability; **Low** is a minor submission gap.

| Requirement / criterion | Status | Evidence and gap | Severity |
|---|---|---|---|
| Users set up alerts | **Met, within documented scope** | `web/routes.py`, `web/templates/settings.html`, `tests/test_user_flow.py`: accounts, destinations, pause/enable, test sends and history. Everyone receives the same selected events. Omitting personalized rules is an explicit decision in `planning/data-schema-users.md`, defensible under the vague brief. | — |
| Important world events | **Partial** | `collector/grouping.py`, `collector/events.py`: coverage ranking and RSS confirmation exist. Thresholds have limited validation; the documented POC selected two stories from one day. | High |
| Breaking news | **Partial** | `collector/run.py:71` requires a manually supplied date window; `collector/rss.py:114` polls once. No continuous collection or delayed Wikipedia-check scheduler implements the architecture’s promised loop. Alert latency is unmeasured. | High |
| Market movements | **Missing as a demonstrated capability** | No market-data input, price-change detection or market-specific validation in `src/newsalert/` or `tests/`. Market headlines might pass the general pipeline, but that capability is unverified. | High |
| Natural disasters | **Partial** | General news collection could detect disasters, but no dedicated disaster feed or representative collector test verifies coverage. Phase 1 explicitly deferred USGS. | Medium |
| Email | **Met for the local POC** | `delivery/channels.py:128`, `tests/test_delivery.py`, phase 2 overview: real SMTP delivery to Mailpit. External inbox delivery is unverified. | — |
| Slack | **Partial** | `delivery/channels.py:94` implements webhook submission and error handling; tests mock responses. `artifacts/user-ui/README.md` explicitly records no real Slack delivery. | Medium |
| Extensible channels | **Partial** | `Notification`, `Target` and the sender boundary separate delivery from collection. Adding a channel still requires changing sender branches, API literals, database constraints and UI (`channels.py:86`, `web/schemas.py:22`, `db/users.py:19`). | Medium |
| Admin view | **Missing** | `web/routes.py` exposes account/settings/history screens only. No admin authorization, candidate inspection, run results, Wikipedia comparisons or operational dashboard. | High |
| Visible process | **Met** | Phase overviews, planning documents, condensed threads, exact transcripts and meaningful milestone commits are present. Final-phase scope and time allocation remain unwritten. | Low |
| Validation of AI output | **Met, with uneven implementation coverage** | Phase 1’s `3-validation-evidence.md` documents challenged claims, evaluator false positives and corrections. Phase 2 records schema checks, browser verification and Mailpit integration. Collector regression tests and multi-day validation remain absent. | Medium |

A submission reviewer would also expect—but currently not find:

- A reproducible, consolidated collector-to-inbox walkthrough. `src/README.md` still says table-creation commands are absent, although `db/init.py` exists.
- The Dockerfile/Compose setup described in `planning/architecture.md`.
- Representative market/disaster examples, measured detection latency, and manually audited selection results.
- A repeatable collector-to-dispatcher integration test; current delivery tests seed events directly.

Prompt-history artifacts exist; completeness against every original AI session is **unverified**.

**2. Top code risks**

All findings below were verified by reading the code. The indicated probes used memory only; no files were modified. I did not rerun the full pytest suite because its fixtures write temporary databases.

| Risk | Verified failure scenario and evidence | Severity |
|---|---|---|
| Event identity changes across windows | `collector/grouping.py:180` sorts URLs and hashes the lexicographically first URL at line 184—not the earliest article. `collector/events.py:92` uses that hash as the sole event lookup. Adding/removing that URL changes identity; no cross-run story reconciliation exists. An in-memory probe confirmed that a changed key produces two selected events for the same story, defeating delivery deduplication. | **High** |
| Outlet counts can inflate automatic selection | `collector/grouping.py:138` counts each syndicated headline group as another voice without deduplicating overlapping source sets between groups. Running the existing scoring function on 100 groups from the same three domains returned **100 independent outlets**, enough to meet the default automatic threshold with two RSS confirmations. | **High** |
| Different articles can become “exact” RSS confirmations | `collector/text.py:59` discards every query parameter. Consequently, `/article?id=1` and `/article?id=2` collide. `collector/events.py:35` accepts that collision immediately with confidence `1.0`, bypassing term/time checks. An in-memory probe confirmed an unrelated headline matched by URL. | **High** |
| Unverified destinations enable email abuse | `web/routes.py:87` accepts arbitrary recipient addresses; `web/routes.py:148` permits repeated test sends, including paused destinations. No destination verification or application rate limit exists. A registered user can repeatedly trigger application email to someone else. | **Medium** |
| Confirming sources are displaced by syndicated links | `collector/events.py:105` inserts GDELT evidence first; `delivery/dispatcher.py:75` renders evidence in insertion order; `delivery/messages.py:28` keeps only three links. Three valid GDELT links can exclude every confirming RSS article. The ordering was reproduced in memory and matches the documented POC weakness. | **Medium** |
| Database initialization can target the wrong database | `db/init.py:33` reads shell environment variables but does not load `.env`; `settings.py:6` and `collector/config.py:17` do. With a custom database URL only in `.env`, the initializer creates the default database while the application opens the custom, uninitialized database. | **Medium** |

**Top 5 recommendations for the final phase**

1. **Fix alert correctness first:** reconcile event identity across runs, correct outlet counting, preserve identifying query parameters, and prefer confirming RSS links. Add focused regression tests.
2. **Build a small, protected admin view:** show runs, candidates, selection reasons, source evidence, Wikipedia matches and delivery failures. Keep threshold editing optional.
3. **Make collection continuous and reproducible:** schedule RSS polling and overlapping collection windows, then delayed Wikipedia checks. Provide one accurate startup/demo guide and consistent database configuration.
4. **Validate representative cases:** manually audit several days, including market and disaster stories; measure duplicates, false confirmations and latency. Exercise one real Slack webhook and retain redacted evidence.
5. **Finish the submission narrative:** document final scope and omissions, record fixes and rejected AI suggestions, link validation evidence, and explain the remaining tradeoffs within the 24-hour budget.