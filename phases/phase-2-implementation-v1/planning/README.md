# Phase 2 planning

Each thread writes its own plan here, so both can see the other's work before building.

architecture.md - shared. Stack, containers, folder structure and ownership.
data-schema-collector.md - Claude. Data collection: source items, events, Wikipedia checks, collector runs.
data-schema-users.md - Codex. Users, destinations, deliveries.

Shared point: the events table. The collector writes it; delivery reads events with status "selected" and creates deliveries that point to events.id. Any change to events must be visible in both files.
