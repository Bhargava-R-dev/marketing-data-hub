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
Google's reviewer needs to clearly SEE the actual Google permission screen —
not just click past it. The single most common reason this gets rejected is
recording at normal speed and clicking "Allow" before the screen is even
fully rendered, so the reviewer can't read it back. Fix: maximize the browser
window first, and **pause for a full 3–5 seconds** on the permission screen
itself before clicking anything.

~2 minutes, screen recording with the browser **maximized** and the URL bar
always visible:
1. Open `https://growthbybhargava.com/tools/marketing-data-hub`, scroll to show the download and privacy link.
2. Run `hub setup`; the setup page opens.
3. Click "Connect Google". A new tab opens at `accounts.google.com` and shows
   an account picker — pick the account. **This is not the consent screen
   yet — keep recording.**
4. The *next* screen is the real one: still on `accounts.google.com`, titled
   something like "Marketing Data Hub wants to access your Google Account",
   listing the app name/logo and the three permissions (Google Analytics,
   Search Console, email address) with **Cancel** / **Continue** buttons.
   **Stop and hold on this exact screen for 3–5 seconds** — this is the part
   the reviewer checks for. Only then click **Continue**/**Allow**.
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

## After approval

- [ ] Sign in once with a fresh Google account to confirm the "unverified app" warning is gone.
- [ ] Tell Claude Code — the wizard's Welcome copy can then drop the "you may see a warning" note.

## H. PyPI trusted publishing (one time, needed for automated releases)

- [ ] pypi.org → log in → your project `marketing-data-hub` → **Publishing** → *Add a new publisher* (GitHub):
  - Owner: `Bhargava-R-dev`
  - Repository: `marketing-data-hub`
  - Workflow name: `release.yml`
  - Environment: leave blank
- [ ] Save. From then on, pushing a `v*` tag publishes the wheel with no token to manage. Until this exists the release workflow's `wheel` job fails (the Windows installer job is independent and still succeeds).
