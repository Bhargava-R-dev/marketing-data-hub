# Setup Wizard v2 + Data Dashboard — Design

## Goal

Two changes driven by user feedback after using the wizard for real onboarding:

1. **Setup wizard**: connected Google logins currently show meaningless internal
   names (`default`, `personal`). The "choose what to sync" account picker is a
   single flat list with a free-text "browse login" box — unusable once
   several Google accounts and 150+ properties are involved.
2. **Dashboard**: no way to see, at a glance, what data actually lives in the
   hub (which brands, how much history, how many rows) before/while asking
   Claude questions.

## Decisions (from user conversation)

- **Identity naming**: auto-detect and label with the real Google account
  email — no manual naming step. (Rejected: letting the user pick a custom
  friendly label — can revisit later if requested.)
- **Account picker structure**: two-level tabs. **Left sidebar = source**
  (GA4 / Search Console). **Sub-tabs within = connected Google login**
  (labeled by real email). Selecting a combination loads that specific
  source+login's properties.
- **Long lists**: search/filter box **and** grouped collapsible sections
  (GA4 properties grouped by parent account; GSC sites left as a flat
  searchable list — GSC's API has no meaningful parent grouping).
- **Page structure**: stays a single scrolling page (existing sections
  1-5), restyled — not a multi-step wizard.
- **Sync flow**: unchanged from already-shipped behavior (Option C from
  earlier design) — submit adds accounts and kicks off sync in the
  background; user isn't forced to wait.
- **Dashboard**: standalone (`hub dashboard` command, usable anytime) +
  a recap view inside the wizard after sync starts. Read-only, localhost
  only, no auth token needed (no state-changing actions).
- **Dashboard content**: summary only for now (brand, login, date range,
  row count), grouped by source, with **one last-synced status per source**
  (not per brand — syncing runs per-source, so per-brand timestamps aren't
  available). Drill-down into report types is an explicit non-goal for v1.

## Identity email auto-detection — technical approach

- Add `https://www.googleapis.com/auth/userinfo.email` to `GOOGLE_SCOPES`.
  Existing tokens lack this scope, so `get_credentials`'s existing
  under-scoped-token check will force re-consent automatically — no new
  code needed there.
- New `secrets/identity_labels.json`: maps internal identity slug → email,
  written after any successful `login()`.
- Internal identity slugs are otherwise **unchanged** — `default`/`personal`
  keep working exactly as configured in the live `config.yaml` today (no
  migration). The wizard hides the raw slug and shows the fetched email
  instead; the "Login name" text box is removed from the UI (auto-assigned
  internally, never surfaced).
- Existing identities connected before this change won't have a label yet.
  The wizard shows those as "click to authorize" — one manual re-consent
  click backfills the label using the same slug (properties already mapped
  to that slug keep working unchanged).

## Non-goals for this pass

- Per-brand sync timestamps (would require reworking sync_runs to log
  per-account, not per-source — bigger change, not requested).
- Dashboard drill-down into report types (explicitly deferred).
- Renaming/custom labels for identities (explicitly deferred).
- Multi-step (wizard-style) page navigation (explicitly rejected in favor
  of the single-page layout).
