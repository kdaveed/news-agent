# Fresh-environment startup review

Date: 2026-11-06. Verdict: the documented Compose startup works. The README is understandable, with one observed dashboard defect and the configuration/first-notification gaps below. This was a fresh runtime review by Codex, not a separate independent AI reviewer.

## Isolation and method

Copied the current working-tree files, including the latest README/demo edits, to `/tmp/newsalert-review-20261106-v6uazv_c`. Application code is based on commit `b7ca13f`. No original `.env`, virtual environment, local database or downloaded news data was copied.

Followed the root README, application README and reviewer checklist. Used a new Compose project (`newsalert-review`), new volume (`newsalert-review_newsalert-data`), and separate image (`newsalert-review:local`). Port overrides and an image-only Compose override prevented interference with existing services. The original application's code and data were not changed during this review.

The generated review `.env` uses a fresh session secret and allows `reviewer@example.com` as admin. No existing account credentials were reused. Docker build cache and uv package cache were available; this was not a cold-cache download test.

## Startup and verification

| Check | Observed result |
| --- | --- |
| Compose configuration/build | Passed |
| Initialization | Exited 0; created all 10 shared tables |
| Runtime | Web healthy; Mailpit healthy; collector and dispatcher running |
| Isolated dependency installation | Passed; new virtual environment |
| Standard test suite | 49 passed, 1 optional Mailpit test skipped |
| Suite with isolated Mailpit enabled | 50 passed |
| `ruff check src tests` | Passed |
| Registration, login, settings, admin | Passed in API/browser checks |
| Ordinary registered user's admin access | HTTP 403 |
| Browser JavaScript errors | None observed |

Tests emitted an existing Starlette/httpx deprecation warning; it did not fail the suite.

The live collector downloaded 192 GDELT files with none missing, processed 330,055 mentions into 2,541 story candidates, and stored the top 300 events: **2 auto/selected, 30 review/candidate, 268 drop/dropped**. It polled 128 new RSS items, used 113 within the matching window, and recorded 43 Wikipedia entries with 32 events checked and 16 keyword matches. These are observed pipeline outputs, not a validation of factual accuracy or clustering quality.

The reviewer account was created after the initial automatic selections, so those events correctly did not backfill to its new destination. To test the connected flow, the browser opened a real collected review candidate's evidence page and clicked **Select for delivery**. The running dispatcher created one delivery, submitted it to the isolated Mailpit on its first attempt, and recorded `sent`. The notification appeared in user history and Mailpit. Subsequent dispatcher cycles did not send it again.

The reviewer inbox contains one explicit test notification and one manually approved collected news event. The latter is **not** an automatic-selection demonstration. No real Slack channel or external mailbox was contacted. Slack HTTP behavior is covered by mocked tests.

## Findings

1. **Dashboard match count renders a boolean instead of an integer.** The admin screenshot shows “True of 32 checked events matched”; raw SQL returns 16 matches from 32 checks. The SQLAlchemy aggregate in `src/newsalert/web/admin.py:100` yields `(32, True)` because the Boolean column's sum retains Boolean result processing. Cast the summed expression to an integer and add a regression check with multiple matches. Collection/check storage is correct; the presentation is wrong. The existing 50 tests did not catch it.
2. **Compose does not forward documented collector settings.** The application README describes `NEWSALERT_HTTP_USER_AGENT` and threshold environment variables, but the Compose collector has an explicit environment list that omits them, and `.env` is excluded from the image. Setting these only in the host shell or Compose `.env` does not configure the container. The default collector completed successfully here; configurable deployments need these mappings added or a documented override.
3. **Fresh Compose users need a clearer first-notification walkthrough.** The collector starts before anyone registers. New destinations intentionally do not receive previously selected events. Explain that users should wait for a newly selected event or approve a review candidate after configuring a destination. The local demo seeds its destination before collection, so this distinction mainly affects the Compose route.
4. **“One command” has two meanings.** The local demo runs the pipeline and prints a separate web-start command; Compose starts the web and workers together. Both are described, but making that distinction explicit at the top would reduce surprises. This review executed the Compose route, not `scripts/demo.sh` or its unavailable historical replay snapshot.

No application fixes were applied during this review.

## Follow-up: fixes verified

After the review, the user requested fixes. Claude's integer-count and Compose mappings were already present in the shared workspace. Codex extended regression coverage to empty, zero-match and multiple-match keyword counts (excluding other checker methods), plus Compose defaults and `.env` overrides. The collector settings are also listed in `.env.example`.

All **55 tests passed**, including the local Mailpit integration; lint passed. The rebuilt isolated web instance renders **16 of 32 checked events matched**. A one-off collector container received a custom User-Agent and thresholds **125 / 3 / 45** through Compose. The persistent review collector was refreshed with its normal configuration; the review database and accounts were preserved.

The original screenshots retain the observed defect. See [the corrected dashboard](admin-fixed.png) for the verified fix. The remaining first-notification and demo-startup notes above are documentation improvements, not changes included in these two fixes.

## Running review instance

- Login: http://127.0.0.1:8100/login
- Register: http://127.0.0.1:8100/register
- User settings/history: http://127.0.0.1:8100/settings
- Admin overview: http://127.0.0.1:8100/admin
- Admin events: http://127.0.0.1:8100/admin/events
- Admin deliveries: http://127.0.0.1:8100/admin/deliveries
- Isolated Mailpit: http://127.0.0.1:18125

Synthetic review admin: `reviewer@example.com` / `Review-demo-2026!`. These credentials belong only to this temporary, loopback-bound review instance. Registering a new account does not automatically grant admin access.

The stack is left running for inspection. To stop this review instance only:

```sh
cd /tmp/newsalert-review-20261106-v6uazv_c
docker compose -p newsalert-review -f docker-compose.yml -f .review-compose.yml down
```

## Evidence

- [Container status](container-status.txt)
- [Startup and dispatcher logs](startup.log)
- [Browser result](browser-result.json)
- [Login screenshot](login.png)
- [Admin after startup](admin-startup.png)
- [Event before manual approval](event-before-selection.png)
- [User delivery history](user-delivery-history.png)
- [Admin after delivery](admin-after-delivery.png)
- [Mailpit inbox](mailpit-inbox.png)
