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

### Step 3 — Make a folder for your hub

Copy-paste these two lines into the command window, pressing **Enter** after
each. This makes a folder called `marketing-hub` and moves into it.

**Windows:**
```
mkdir %USERPROFILE%\marketing-hub
cd %USERPROFILE%\marketing-hub
```

**Mac:**
```
mkdir ~/marketing-hub
cd ~/marketing-hub
```

> Tip: everything the tool creates — your settings and your data — will live
> inside this `marketing-hub` folder. If you ever want to start fresh, you can
> just delete the folder.

### Step 4 — Install the tool

Copy-paste this one line and press **Enter**:

```
pip install marketing-data-hub
```

You'll see a lot of text scroll by for a minute or two while it downloads. When
the cursor comes back and stops scrolling, it's done. (If you see a note about
"a new release of pip is available," ignore it — that's harmless.)

### Step 5 — Add the sign-in file from your admin

Your admin sent you a file called **`google_client.json`**. Now you'll put it in
the right place.

1. Inside your `marketing-hub` folder, make a folder named **`secrets`** (all
   lowercase). In the command window:
   - **Windows:** `mkdir secrets`
   - **Mac:** `mkdir secrets`
2. Move the `google_client.json` file your admin sent you **into that `secrets`
   folder**, using your normal File Explorer / Finder (drag and drop is fine).

The file should end up here:
`marketing-hub` → `secrets` → `google_client.json`

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

You'll see five numbered sections on the page. Go through them top to bottom.

### Step 7 — Section 1: Connect Google

1. Leave the "Login name" box as **`default`**.
2. Click **"Connect Google account."**
3. A **Google sign-in tab** opens. Sign in with the Google account that can see
   your analytics.
4. Google may show a screen saying the app **"isn't verified."** This is normal
   for an internal tool — click **"Advanced"** and then **"Go to … (unsafe)"**
   to continue. (It's your admin's app; it's safe.)
5. Tick the boxes to **allow** access when Google asks, and finish.
6. Back on the wizard page, you'll see **"connected ✓"**.

> **Have analytics under a second Google account too?** You can connect it as
> well: type a different login name (like `personal`) and click Connect again.
> The tool keeps them side by side.

### Step 8 — Section 2: Choose what to sync

1. Click **"Load accounts."** After ~10 seconds, a checklist appears with every
   Google Analytics property and Search Console site your login can see.
2. **Tick the ones you want** to track. (Accounts already added show a ✓ and are
   greyed out.)
3. Click **"Add selected."** You'll see a confirmation, and the "Currently
   syncing" line at the bottom updates.

That's the core of it — GA4 and Search Console are now set up.

### Step 9 — Section 3: Ad platforms (optional — skip if you don't run ads)

Click the **"Ad platforms"** heading to expand it. Only fill in the platform(s)
you use.

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

### Step 10 — Section 4: Load your data

1. Click **"Run first sync."**
2. You'll see each source update live: *⏳ syncing…* then *✓ ga4: 12,495 rows*.
3. This can take a few minutes (longer if you have lots of accounts). Let it
   finish — you'll see **"done ✓"** at the top.

Your data is now on your computer.

### Step 11 — Section 5: Connect Claude

This is what lets you *ask questions*.

1. On the wizard page, click **"Copy"** under the code box. (This copies a small
   piece of text — your personal connection snippet.)
2. Open **Claude Desktop**.
3. Go to **Settings → Developer → Edit Config.** A settings file opens.
4. Paste the snippet inside it, following the on-page instructions (it goes
   inside the `mcpServers` section). Save the file.
   - If the file was empty or you're unsure, ask your admin to help with this
     one paste — it takes 30 seconds.
5. **Fully quit Claude Desktop and reopen it** (quit completely, not just close
   the window).

6. Back on the wizard page, click **"Finish & close wizard."** You can close the
   browser tab and the command window now.

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
