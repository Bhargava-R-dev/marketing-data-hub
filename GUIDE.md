# Marketing Data Hub — Complete User Guide

A step-by-step guide to installing and using Marketing Data Hub, written for
everyone — no technical background needed. If you can install an app and copy
and paste, you can do this.

**What this tool does for you:** it pulls your marketing numbers (Google
Analytics, Search Console, and optionally Google Ads / Meta Ads) onto your own
computer, so you can ask questions about them in plain English through Claude —
things like *"How did organic traffic do last month?"* or *"Which pages got the
most visits?"* — and get instant answers with real numbers, instead of clicking
through dashboards and copying figures by hand.

**How long it takes:** about 20–30 minutes, once. After that, it just works.

---

> ### 📋 For the admin sharing this guide
>
> Before a colleague starts, make sure you've given them:
> 1. **`google_client.json`** — the Google sign-in file (from your Google Cloud
>    project → APIs & Services → Credentials). Same file for everyone on your
>    team; send it directly (chat/email/USB), never post it publicly.
> 2. **Meta Ads** (only if they run Meta ads): add them as a **Developer** on
>    your Meta app (developers.facebook.com → your app → App Roles), then send
>    them an **access token** with `ads_read`, or have them generate their own.
> 3. **Google Ads** (only if they run Google ads): send them the **developer
>    token** and their **customer id(s)**.
> 4. Be available for **Step 11** (the one-time Claude config paste) if they're
>    not comfortable editing a settings file.
>
> Everything else the colleague does themselves. The rest of this document is
> written for them.

---

## Before you begin — a 2-minute overview

You'll do three things, in order:

1. **Install** the tool on your computer (one-time).
2. **Connect** your Google account and pick which websites/accounts you want.
3. **Ask questions** through Claude.

You will need:

- A **computer** (Windows or Mac).
- A **Google account that can already see your analytics.** This is important:
  the tool only shows data you already have access to. If you can open the
  reports in Google Analytics or Search Console in your web browser, you're
  set.
- **One small file from your admin** (the person who shared this guide with
  you) called `google_client.json`. It's the "key" that lets the tool sign you
  into Google. Ask them for it — it's tiny and safe to receive by email or
  chat.
- **Claude Desktop** installed (the app you'll ask questions in).

> **A word on privacy:** everything runs on *your* computer. Your data and your
> Google login never get uploaded anywhere. There's no website, no account to
> create, no subscription.

---

## PART 1 — Install the tool (one-time)

### Step 1 — Install Python

Python is the free software the tool runs on. You install it once and never
think about it again.

1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python"** button.
3. Open the file you just downloaded to start the installer.
4. **VERY IMPORTANT:** on the first screen, tick the box at the bottom that says
   **"Add Python to PATH"** before clicking Install. (If you miss this, the
   tool won't be found later.)
5. Click **Install Now** and wait for it to finish. Close the installer.

*(Mac users: the installer is a `.pkg` file — double-click it and click through
Continue/Install. There's no "Add to PATH" box on Mac; it's handled for you.)*

### Step 2 — Open the command window

This is the black (or white) text window where you'll type a few commands. Don't
worry — you'll only type a handful of lines, and you can copy-paste them.

- **Windows:** press the **Windows key**, type **`cmd`**, and press **Enter**.
- **Mac:** press **Cmd+Space**, type **`Terminal`**, and press **Enter**.

A window opens with a blinking cursor. That's it — leave it open.

### Step 3 — Nothing to do here

The tool picks its own folder for your settings and data
(`MarketingDataHub` inside your user's AppData\Local on Windows,
`.marketing-data-hub` in your home folder on Mac). The setup page shows the
exact path. If you ever want to start fresh, delete that folder.

> **Windows shortcut:** if you'd rather not use a command window at all,
> download the installer from
> <https://growthbybhargava.com/tools/marketing-data-hub>, run it, and skip
> straight to Step 7 — the setup page opens by itself.

### Step 4 — Install the tool

Copy-paste this one line and press **Enter**:

```
pip install marketing-data-hub
```

You'll see a lot of text scroll by for a minute or two while it downloads. When
the cursor comes back and stops scrolling, it's done. (If you see a note about
"a new release of pip is available," ignore it — that's harmless.)

### Step 5 — Sign-in file: built in

Nothing to add — the tool ships with its own Google sign-in. (Only if your
company insists on its own Google Cloud project will an admin give you a
`google_client.json`; then drop it in the `secrets` folder inside the tool's
folder from Step 3, and the setup page will say "Using your own Google client".)

That's the whole installation. Now the fun part.

---

## PART 2 — Set up your data (the wizard)

### Step 6 — Open the setup wizard

In the command window, type:

```
hub setup
```

and press **Enter**. After a second, **a page opens in your web browser** titled
"Marketing Data Hub — Setup." This friendly page is where you'll do everything
next — no more typing commands. Keep the command window open in the
background (don't close it while you're using the wizard).

The page walks you through six steps, shown across the top. Click **"Get
started"** on the Welcome step.

### Step 7 — Connect Google

1. Click **"Sign in with Google."** (No name to type — the tool figures out
   which account it is automatically.)
2. A **Google sign-in tab** opens. Sign in with the Google account that can see
   your analytics.
3. Google may show a screen saying the app **"isn't verified."** If so, click
   **"Advanced"** and then **"Go to Marketing Data Hub"** to continue.
4. Tick the boxes to **allow** access when Google asks, and finish.
5. The setup page notices by itself and moves on, showing **your email
   address** as connected.

> **Have analytics under a second Google account too?** Click **"+ Add another
> Google account"** and sign in with the other one (choose **"Use another
> account"** if Google offers to reuse the one you're already signed into).
> Both show up by their real email, and the next step lets you switch between
> them.

### Step 8 — Choose accounts

1. Pick **GA4** or **Search Console** — whichever you want to add.
2. Pick **which connected account** (by email) it belongs to. A checklist loads
   after ~10 seconds with every property/site that account can see, grouped and
   searchable if you have a lot. Each group has a **"select all"** link.
3. **Tick the ones you want.** The button shows how many you've selected.
4. Click **"Add N selected."** They appear instantly under "Currently syncing";
   the ✕ on any of them removes it again.
5. Click **"Continue to sync"** when you're done.

That's the core of it — GA4 and Search Console are now set up.

### Step 9 — Ad platforms (optional — skip if you don't run ads)

On the Choose accounts step, open **"Advanced: Google Ads & Meta Ads tokens"**.
Only fill in the platform(s) you use.

**Meta Ads (Facebook / Instagram):**
- Paste your **access token** (your admin generates this from the shared Meta
  app and sends it to you).
- Enter your **ad account id(s)** — they look like `act_1234567890`. You can
  find them in Meta Ads Manager. Separate several with commas.
- Click **"Save Meta Ads."**

**Google Ads:**
- Paste the **developer token** (your admin provides this).
- Enter your **customer id(s)** — they look like `123-456-7890`.
- If your ads are managed through an agency/manager account, enter its
  **Manager (MCC) id** too. Otherwise leave it blank.
- Click **"Save Google Ads."**

> Not sure about tokens? That's fine — ask your admin. They set these up once
> and share the values. See the "Words explained" section at the end.

### Step 10 — Sync

The sync starts by itself. You'll see one line per account with a spinner,
then *✓ 12,495 rows* as each finishes, and a progress bar at the top. This can
take a few minutes (longer with many accounts). You can close the tab and come
back — the sync carries on, and reopening the setup shows where it got to.
Click **"Continue"** when the bar is full.

Your data is now on your computer.

### Step 11 — Connect Claude

This is what lets you *ask questions*.

1. The page shows **"Claude Desktop"** if it's installed. Click **"Connect."**
   That's it — the settings file is written for you (a backup of the old one is
   kept next to it).
2. **Fully quit Claude Desktop and reopen it** (right-click its icon in the
   system tray → Quit — not just close the window).
3. Click **"Continue."**

> Claude Desktop not found? Install it from claude.ai/download, then click
> **"Check again."** The manual snippet is under "Manual setup" if you ever
> need it.

### Step 12 — Done

The last step is your **home page**: it schedules the **daily 6am refresh**
and puts a **"Marketing Data Hub"** icon on your Desktop and Start Menu. From
now on, double-click that icon to come back here — add or remove accounts,
**Sync now**, or **Open dashboard** — with no command window at all. You can
close the browser tab and the command window now.

**You're done.** 🎉

---

## PART 3 — Using it every day

### Asking questions

Open Claude Desktop and just ask, in plain English. Some examples:

- *"How did organic traffic do last month compared to the month before?"*
- *"What were my top 10 landing pages in June?"*
- *"Show me branded vs non-branded search clicks this month."*
- *"Which search queries brought the most clicks last week?"*
- *"How many form submissions did we get in the last 30 days?"*
- *"Compare this year's traffic to last year, by month."*
- *"Break down sessions by device — mobile vs desktop."*

Claude pulls the real numbers from your hub and answers. You can ask follow-ups
just like a conversation ("now just for the India site", "make that a table").

### What kinds of data you can ask about

| You can ask about… | Examples |
|---|---|
| **Traffic & visitors** | sessions, users, new vs returning |
| **Traffic sources** | organic, paid, direct, social, referral |
| **Pages** | top pages, landing pages, engagement time |
| **Search (Google)** | clicks, impressions, position, queries, branded/non-branded |
| **Segments** | by device, by country |
| **Conversions/events** | form submits, calls, sign-ups (whatever your site tracks) |
| **Ads** (if set up) | spend, clicks, impressions, conversions by campaign |

Tip: ask Claude *"what data do you have for me?"* and it'll list your connected
accounts and date ranges.

### Keeping data fresh

The tool automatically refreshes recent data if daily updates were set up for
you (ask your admin). To refresh manually any time, open your command window and
run:

```
cd %USERPROFILE%\marketing-hub        (Mac: cd ~/marketing-hub)
hub sync all
```

> **One rule:** don't ask Claude questions *while* a sync is running — Claude
> will say "database is busy." Just wait a minute for the sync to finish, then
> ask.

### Adding more accounts later

Run `hub setup` again any time to add more properties, sites, or ad accounts —
it remembers what you already have.

### Checking what data you have

Run:

```
hub dashboard
```

This opens a page showing every brand currently synced — grouped by GA4 /
Search Console, with how much history each has and when it last synced. Handy
for a quick "what can I actually ask about?" check, or for confirming a sync
finished. Works anytime, independent of the setup wizard.

---

## Troubleshooting

| What you see | What to do |
|---|---|
| **`hub` is not recognized / command not found** | Python wasn't added to PATH. Reinstall Python (Step 1) and tick "Add Python to PATH". Or use `python -m hub.cli` in place of `hub`. |
| **"No Google credentials found"** | The `google_client.json` file isn't in the `secrets` folder. Recheck Step 5. |
| **Google says "app isn't verified"** | Normal for an internal tool — click Advanced → continue. |
| **The account checklist is empty** | The Google account you signed in with doesn't have access to any analytics. Sign in with the right account (re-run the Connect step). |
| **Claude doesn't show any data / tools** | Make sure you fully quit and reopened Claude Desktop after pasting the snippet. |
| **"database is busy"** | A sync is running. Wait a minute and ask again. |
| **Install fails with a long path error (Windows)** | Put the `marketing-hub` folder somewhere with a short path, like `C:\marketing-hub`, and try again. |
| **Anything else** | Contact your admin and paste them the exact message you see. |

---

## Words explained (plain English)

- **Python** — free software the tool runs on. Install once, forget about it.
- **Command window / Terminal** — the text window where you type a few setup
  commands. You barely use it after setup.
- **`google_client.json`** — the "key" file from your admin that lets the tool
  sign you into Google. Goes in the `secrets` folder.
- **Token** — a long password-like code that grants access to Google Ads or
  Meta Ads data. Your admin generates these and shares them; you just paste
  them in.
- **GA4** — Google Analytics 4, your website traffic data.
- **Search Console (GSC)** — Google's data about how you show up in search
  results (clicks, impressions, search terms).
- **Sync** — the tool fetching the latest numbers from Google onto your
  computer.
- **Branded vs non-branded** — searches that include your brand name (branded)
  vs. generic searches (non-branded).
- **Claude / MCP** — Claude is the AI assistant you ask questions in. "MCP" is
  just the plumbing that connects Claude to your hub; the snippet you pasted in
  Step 11 sets it up.

---

*Questions this guide didn't answer? Ask your admin — they set this up and can
help with anything specific to your accounts.*
