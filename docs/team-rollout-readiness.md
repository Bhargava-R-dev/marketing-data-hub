# Team rollout readiness — 17 September 2026

## Incident and scope

The v0.6.0 report is consistent with the source at `5dcc4d8`: a frozen GUI
process used its own executable for sync, the GUI discarded arguments, the
server opened a browser before binding, and each new page could trigger sync.
This review confirms those code defects. It does not independently verify the
colleague's installer hash, machine scan, or absence of malware on that machine.

Pause distribution of v0.6.0. Existing users can close the repeated tabs and
exit the app; as a temporary workaround, start the installed `hub.exe setup`
instead of its GUI shortcut. Do not ask colleagues to disable Defender or Smart
App Control. Retain the incident logs and installer hash for release tracking.

## Changes in this patch

| Gap | Change |
| --- | --- |
| GUI relaunches itself instead of syncing | Shared CLI command builder selects sibling `hub.exe`; missing CLI produces an actionable failure |
| Arguments discarded by GUI | Only an argument-free GUI launch defaults to setup |
| Tabs opened on failed startup | Setup and dashboard open the browser only after successful Uvicorn startup |
| Multiple tabs race to launch work | Wizard serializes launch requests and tracks the process immediately |
| Child dies before progress exists | Status reports its exit or launch error; previous success cannot mask a new job |
| Opening/reloading a page starts sync | Polling is read-only; starting or retrying requires an explicit action |
| Scheduler and Claude point at GUI | Both use the shared console CLI resolver |
| Frozen MCP passes `-m hub.cli` to an EXE | Sync and backfill use packaged CLI commands, both unattended |
| Custom shortcut loses its config | Preserve the supplied config argument |
| Stale Claude command appears connected | Compare command and arguments, not merely the config path |
| Claude repair loses unrelated settings | Merge only `marketing-hub`, keep a backup, replace atomically, refuse malformed JSON |
| Claude Code registration does not replace stale global entry | Repair the user-level `.claude.json` entry directly when Connect is selected |
| Local UI accepts arbitrary Host/Origin | Restrict setup/dashboard hosts and reject foreign setup origins |
| Release check exercises only CLI version | Add packaged GUI startup, occupied-port, sync-child and shutdown smoke tests to CI |
| Untested/unsigned release publication | Require tests and trusted timestamped signatures before publishing; include SHA-256 checksums |

An occupied port now fails without opening a tab. It does not automatically
attach to whatever is on that port: that could be another app or another hub.

## Windows publisher trust — still a release blocker

Google OAuth verification concerns Google account access and consent. It does
not establish a Windows publisher identity or sign this installer.

Obtain a public-trust code-signing identity under the publisher's control.
Microsoft Artifact Signing is one option, subject to eligibility and identity
validation; a supported CA/hardware-backed signing service is another. Choose
the service before adding its authenticated signing steps to release CI. No
signing account, certificate, or paid service has been provisioned by this patch.

1. Sign and timestamp the bundled `hub.exe` and `MarketingDataHub.exe` before
   building the installer; validate the actual files being packaged.
2. Review/sign the bundled native libraries as required by the target Windows
   app-control policy. Configure Inno Setup's signed-uninstaller support too.
3. Build the installer, sign and timestamp it, then create the versioned alias
   from the signed file. Both downloadable installer names must be signed.
4. Run `packaging/verify_signatures.ps1` and generate checksums after signing.
   Keep the verified publisher identity consistent across releases.
5. Have team IT test the exact downloaded artifact against their endpoint
   policy. A valid signature does not guarantee immediate SmartScreen reputation.

The release workflow deliberately fails until signing steps are configured.
It will not silently publish an unsigned fallback or publish the wheel ahead
of the failed Windows release. PR tests do not require signing credentials.

References: [Microsoft SmartScreen guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation),
[Artifact Signing action](https://github.com/Azure/artifact-signing-action),
[Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app).

## Required acceptance before expanding beyond a pilot

- Fresh Windows user with no Python: install, Start Menu launch, Google consent,
  account selection, sync, dashboard, Claude Desktop and Claude Code.
- Upgrade an existing v0.6.0 install: back up the hub folder first; confirm data,
  credentials, paths and other MCP entries survive. Reconnect each Claude target
  and re-register daily sync so existing stale stored commands are replaced.
- Try two launches, several tabs, a port occupied by another process, a missing
  CLI, expired/revoked consent, offline access and a forced child-process exit.
- Confirm no background operation opens a consent browser. Show the user which
  account needs reconnection, and require their explicit login action.
- Exercise the actual scheduled task on battery and after sleep; confirm its
  action invokes `hub.exe sync ... --unattended`, not the GUI.
- Restore a backup and test uninstall/reinstall. Verify that retained tokens
  and data match the documented retention policy.
- Publish a new version only after the final signed installer passes these
  checks; keep a rollback installer and a reproducible build record.

## Remaining scaling work (not certified by this patch)

This remains a per-user local app, not a shared multi-user database service.
Do not place a shared DuckDB file on a network drive for the team.

- Coordinate all writers across wizard, MCP, scheduled tasks and API using one
  cross-process job mechanism. The new wizard guard prevents concurrent launches
  within its process; DuckDB still arbitrates independent writers. Recover stale
  progress after a crash or wizard restart using job ownership/heartbeat data.
- Serialize config edits and Google login creation across simultaneous tabs;
  guard configuration changes while a sync is reading them. Bound log growth
  and add redacted support diagnostics and restore testing.
- Review local OAuth-token storage, Windows ACLs/credential encryption, token
  revocation on offboarding, retention and log redaction. These are not replaced
  by Google verification. The app currently stores tokens as local JSON files.
- Verify Google's approval for the exact requested scopes and desktop OAuth
  client, including any additional Ads/YouTube scopes, with a fresh consenting
  user. This patch does not access or change the Google Cloud submission.
- Pin a tested dependency set, audit dependencies, retain build provenance,
  and test signed artifacts on clean supported Windows versions and managed PCs.
- Validate Claude installations whose project-local MCP entries override the
  user entry; this patch repairs the selected Desktop/user entry, not unrelated
  per-project configuration.

The fixes address the observed incident and adjacent source defects, not every
possible future failure. Passing automated tests is necessary but does not
replace the signed-installer and real-account acceptance checks above.
