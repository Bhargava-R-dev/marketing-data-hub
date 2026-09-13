# Google OAuth app verification — checklist

Project: `data-hub-501708` (console.cloud.google.com, signed in as the project owner).
Do these in order. Items marked **(needs live site)** wait until the website PR is merged.

## A. Consent screen (Google Auth Platform → Branding)

- [ ] App name: `Marketing Data Hub`
- [ ] User support email: your address
- [ ] App logo: 120×120 PNG (the logo you're preparing)
- [ ] App home page **(needs live site)**: `https://growthbybhargava.com/tools/marketing-data-hub`
- [ ] Privacy policy **(needs live site)**: `https://growthbybhargava.com/privacy`
- [ ] Terms of service **(needs live site)**: `https://growthbybhargava.com/terms`
- [ ] Authorized domains: `growthbybhargava.com`
- [ ] Developer contact email: your address
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

~2 minutes, screen recording with the URL bar visible:
1. Open `https://growthbybhargava.com/tools/marketing-data-hub`, scroll to show the download and privacy link.
2. Run `hub setup`; the setup page opens.
3. Click "Connect Google" → the Google consent screen appears showing **the app name and the three scopes** → approve.
4. Back in the setup page, show the account list, tick one GA4 property and one GSC site, start the sync.
5. Show the sync finishing and the dashboard listing rows — say (in a caption or voice) "all data is stored locally in this folder", and show the folder.
6. Show `myaccount.google.com/permissions` with the app listed, to demonstrate revocation.

## G. Submit

- [ ] Google Auth Platform → Verification Center → "Prepare for verification" → fill in:
  - How will the scopes be used: *"The desktop application reads the user's own Google Analytics 4 and Search Console reports and stores them in a database on the user's device so they can query them locally. userinfo.email labels which Google login was connected. No data is transmitted to the developer."*
  - Demo video: the unlisted link from F.
- [ ] Submit. Expect 2–6 weeks; Google emails follow-up questions to the developer contact address — answer them promptly (they close the ticket after ~7 days of silence).

## After approval

- [ ] Sign in once with a fresh Google account to confirm the "unverified app" warning is gone.
- [ ] Tell Claude Code — the wizard's Welcome copy can then drop the "you may see a warning" note.
