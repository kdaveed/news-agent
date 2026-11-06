# User flow verification

Implemented login/register/logout, destination settings, test sends and user-scoped delivery history.
No subscriptions or filtering. No migration files or automatic schema creation added by this thread.

- 32 integration checks passed, including the opt-in local Mailpit test; 31 run without Mailpit.
- Disposable SQLite schemas use the shared collector models. Dispatcher checks cover deduplication, retries, paused destinations, secrets and worker locking.
- Actual SMTP verification: fixture event → dispatcher → Mailpit, plus test-send API → Mailpit. Captured text and HTML checked.
- Browser check passed: register → add email → Send test → add Slack → pause Slack → logout → login.
- Desktop (1280px) and mobile (390px) screenshots captured with synthetic account data.
- No browser page errors or mobile page overflow in that check.
- Slack URLs were masked. Email went only to a temporary local Mailpit; Slack HTTP responses were mocked and no real Slack channel was contacted.
- Temporary Mailpit v1.33.0 binary was downloaded from its official release and checked against the release asset SHA256 digest; Docker was not running. Test services were stopped after verification.

Screenshots: [desktop](settings-desktop.png), [mobile](settings-mobile.png).
Application setup, endpoint list and integration boundaries: [src/README.md](../../../../src/README.md).
