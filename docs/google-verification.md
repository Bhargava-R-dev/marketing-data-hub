# Google OAuth app verification — checklist

Project: `data-hub-501708` (console.cloud.google.com, signed in as the project owner).
Do these in order. Items marked **(needs live site)** wait until the website PR is merged.

## A. Consent screen (Google Auth Platform → Branding)

- [ ] App name: `Marketing Data Hub` (currently shows a typo, "Marketind Data Hub" — fix it)
- [ ] User support email: `rallabandibhargava@gmail.com` (Cloud Console's dropdown only accepts the signed-in Google Account or a Group you own — a custom-domain address like `bhargava@growthbybhargava.com` can't be typed in. This does **not** need to match the website's public support email; it's fine, even common, for the two to differ. What actually ties the app to the domain is the Search Console ownership check in step E below.)
- [ ] App logo: 120×120 PNG (the logo you're preparing)
- [ ] App home page **(needs live site)**: `https://growthbybhargava.com/tools/marketing-data-hub`
- [ ] Privacy policy **(needs live site)**: `https://growthbybhargava.com/privacy`
- [ ] Terms of service **(needs live site)**: `https://growthbybhargava.com/terms`
- [ ] Authorized domains: `growthbybhargava.com`
- [ ] Developer contact email: `rallabandibhargava@gmail.com` (Google sends review questions here — check this inbox during the 2–6 week review)
- [ ] Save

## B. Audience

- [ ] User type: External
- [ ] Publishing status: **In production** (click "Publish app" if it still says Testing)

## C. Data access (scopes)

Remove everything and add exactly these three (use "Manually add scopes" if search doesn't find them):

- [ ] `https://www.googleapis.com/auth/analytics.readonly`
- [ ] `https://www.googleapis.com/auth/webmasters.readonly`
- [ ] `https://www.googleapis.com/auth/userinfo.email`

Do **not** add `yt-analytics.readonly` or `adwords` now — they add review time and no current user needs them. (Add later and re-verify when the Ads connector goes live.)

## D. Enabled APIs (APIs & Services → Enabled APIs)

- [ ] Google Analytics Data API
- [ ] Google Analytics Admin API
- [ ] Google Search Console API

## E. Domain ownership

- [ ] Search Console → verify `growthbybhargava.com` is owned by the same Google account that owns the Cloud project (if the site is already verified under another account, add this account as an owner in Search Console → Settings → Users and permissions).

## F. Screencast (record before submitting; unlisted YouTube link)

**Rejection so far: "Your demo video does not show the OAuth consent flow."**
Diagnosed directly from the rejected video (extracted frames with ffmpeg):
the recording account had **already granted this app access** from earlier
testing, so Google skipped the real screen and only ever showed the
shortcut "You're signing back in to Marketing Data Hub" / "Marketing Data
Hub already has some access — see the 4 services" screen — the itemized
scope list stays collapsed and never appears on screen. That's what's
actually missing, not a pacing problem.

**Fix — do this before recording:**
- [ ] Go to [myaccount.google.com/permissions](https://myaccount.google.com/permissions),
  find **Marketing Data Hub**, and remove its access for whichever account
  you'll demo with. This forces Google to show the full first-time consent
  screen again on the next sign-in.
- [ ] Maximize the browser window before recording so the screen is legible.

~2 minutes, screen recording with the browser **maximized** and the URL bar
always visible:
1. Open `https://growthbybhargava.com/tools/marketing-data-hub`, scroll to show the download and privacy link.
2. Run `hub setup`; the setup page opens.
3. Click "Connect Google". A new tab opens at `accounts.google.com` and shows
   an account picker — pick the account you just revoked access for. **This
   account picker is not the consent screen yet — keep recording.**
4. The *next* screen is the real one, still on `accounts.google.com`:
   "Marketing Data Hub wants to access your Google Account", listing the
   app name/logo and each permission individually — Google Analytics,
   Search Console, and your email address — with **Cancel** / **Continue**
   buttons. If you instead see "already has some access" or "signing back
   in", the account wasn't fully revoked — stop and redo step 0 above before
   continuing.
   **Hold on this exact itemized screen for 3–5 seconds** before clicking
   **Continue**/**Allow** — this is the part the reviewer checks for.
5. Back in the setup page, show the account list, tick one GA4 property and one GSC site, start the sync.
6. Show the sync finishing and the dashboard listing rows — say (in a caption or voice) "all data is stored locally in this folder", and show the folder.
7. Show `myaccount.google.com/permissions` with the app listed, to demonstrate revocation.

Before uploading, scrub through the recording yourself and confirm step 4's
screen is on screen long enough to read every word — if you can't read the
scope list back from the video, neither can the reviewer.

## G. Submit

- [ ] Google Auth Platform → Verification Center → "Prepare for verification" → fill in:
  - How will the scopes be used: *"The desktop application reads the user's own Google Analytics 4 and Search Console reports and stores them in a database on the user's device so they can query them locally. userinfo.email labels which Google login was connected. No data is transmitted to the developer."*
  - Demo video: the unlisted link from F.
- [ ] Submit. Expect 2–6 weeks; Google emails follow-up questions to the developer contact address — answer them promptly (they close the ticket after ~7 days of silence).

## G2. Responding to a Trust & Safety rejection email

Google's first response (2026-09-17) asked for four things at once. Two are
already done (privacy policy §4/§5, new demo video). Two are new and need a
**test Google account** — a real login the reviewer can use themselves, not
just watch in a video.

**One-time: create a disposable test account**
- [ ] Create a fresh Google account used for nothing else (or reuse a spare
  one with no sensitive data) — do **not** use `rallabandibhargava@gmail.com`
  or any client account for this.
- [ ] On that account: Google Account → Security → 2-Step Verification →
  **Off**. Also check there's no phone-number-verification prompt configured
  — the reviewer must be able to sign in with just email + password, no OTP.
- [ ] Give it access to at least one real (or dummy) GA4 property and Search
  Console site, so the reviewer sees actual data after connecting, not an
  empty list.
- [ ] Confirmed 2026-09-17: the app is already in **Production**, so this
  account does **not** need to be added as an Audience → Test user — that
  list only applies to apps still in Testing status. It just signs in
  through the normal flow (same "Google hasn't verified this app" screen
  real users see). Do **not** revert the app to Testing status for this —
  that would bring back the 7-day token-expiry bug for every real user.
- [ ] Keep the email + password somewhere you control (a password manager) —
  you'll paste them into the email reply yourself; don't hand them to anyone
  else, and delete/rotate the account once verification is approved.

**Two separate actions — both are required, don't skip either:**

1. **Reply to the SAME email thread** from Google's Trust and Safety team
   (do not start a new email) with:

   > Hi, thanks for the detailed feedback. We've addressed the items below:
   >
   > - Demo video showing the OAuth consent flow (scopes fully expanded):
   >   **[paste the new unlisted YouTube link]**
   > - Privacy policy updated with data sharing/disclosure and data protection
   >   sections: https://growthbybhargava.com/privacy (see "4. Sharing and
   >   disclosure of your data" and "5. Security of your data")
   > - Test credentials for reviewing the OAuth flow directly (2FA disabled):
   >   - Email: **[test account email]**
   >   - Password: **[test account password]**
   >
   > Navigation instructions to reach the OAuth consent screen:
   > 1. Download the Windows installer from
   >    https://growthbybhargava.com/tools/marketing-data-hub and run it (or,
   >    on any OS with Python 3.11+: `pip install marketing-data-hub && hub setup`).
   > 2. The Setup page opens automatically in your browser at
   >    http://127.0.0.1:8770. Click **"Get started"** on the Welcome step.
   > 3. On the **Connect Google** step, click **"Sign in with Google"**.
   > 4. Sign in with the test account above. Google's OAuth consent screen
   >    appears listing the requested permissions (Google Analytics read-only,
   >    Search Console read-only, email address). If any are collapsed under a
   >    "Show all services" or "See all" link, click it to expand the full
   >    list before continuing.
   > 5. Click **Continue**/**Allow**. You're returned to the Setup page with
   >    the account connected.
   >
   > Please let us know if anything else is needed.

2. **Separately, click "resubmit your app"** (the link in the same email) in
   Cloud Console, and fill in:
   - [ ] Link to the login page + the same step-by-step navigation
     instructions as above (with "2FA disabled" noted explicitly).
   - [ ] Link to the privacy policy for data-sharing disclosures:
     `https://growthbybhargava.com/privacy` (section 4).
   - [ ] Link to the privacy policy for data-protection disclosures:
     `https://growthbybhargava.com/privacy` (section 5) — same URL is fine
     for both fields, they're both on that page.

- [ ] After sending the email reply AND resubmitting in Cloud Console, wait
  for the next review pass. Check the test account's 2FA is still off if
  this drags on (Google sometimes re-enables it automatically after a
  security event).

## After approval

- [ ] Sign in once with a fresh Google account to confirm the "unverified app" warning is gone.
- [ ] Tell Claude Code — the wizard's Welcome copy can then drop the "you may see a warning" note.
- [ ] Delete or rotate the disposable test account's password now that it's no longer needed.

## H. PyPI trusted publishing (one time, needed for automated releases)

- [ ] pypi.org → log in → your project `marketing-data-hub` → **Publishing** → *Add a new publisher* (GitHub):
  - Owner: `Bhargava-R-dev`
  - Repository: `marketing-data-hub`
  - Workflow name: `release.yml`
  - Environment: leave blank
- [ ] Save. From then on, pushing a `v*` tag publishes the wheel with no token to manage. Until this exists the release workflow's `wheel` job fails (the Windows installer job is independent and still succeeds).
