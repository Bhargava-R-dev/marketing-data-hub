# Website Pages + Google Verification Implementation Plan (Sub-project 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `/tools/marketing-data-hub`, `/privacy`, and `/terms` on growthbybhargava.com, trim the OAuth scopes to the minimum, and hand the user a ready-to-follow Google verification checklist.

**Architecture:** Three static Next.js routes in the existing `Bhargava-Website/bhargava-next` app, reusing its design tokens (`.shell`, `.page-opener`, `.note-article` prose, `.btn`). One small change in the hub repo narrows `GOOGLE_SCOPES` to the three scopes Google will review; YouTube/Google Ads request their extra scope only when configured. A markdown checklist tells the user exactly what to click in Google Cloud.

**Tech Stack:** Next.js 16 (App Router, server components), plain CSS with existing tokens, Python 3.12 + pytest for the hub repo.

**Two repos:**
- HUB = `C:\Users\Laptop-577\Documents\data collection` (branch `master`)
- SITE = `C:\Users\Laptop-577\Documents\Bhargava-Website` (branch `master`, Next app lives in `bhargava-next/`, Vercel deploys on push to master)

**Spec:** `docs/superpowers/specs/2026-09-14-distribution-and-wizard-v3-design.md`

---

## File structure

HUB repo:
- Modify `src/hub/connectors/google_auth.py` — `GOOGLE_SCOPES` → 3 base scopes; add `YOUTUBE_SCOPE`, `GOOGLE_ADS_SCOPE`.
- Modify `src/hub/connectors/youtube.py` — request `YOUTUBE_SCOPE` in addition to base.
- Modify `src/hub/connectors/google_ads.py` — verify the cached token carries `GOOGLE_ADS_SCOPE`, otherwise trigger re-consent with it.
- Modify `tests/test_google_auth.py`, `tests/test_youtube.py` — scope assertions.
- Create `docs/google-verification.md` — the user's console checklist.

SITE repo (all under `bhargava-next/`):
- Create `lib/hubRelease.ts` — single source for repo/download/pip constants.
- Create `app/tools/marketing-data-hub/layout.tsx` (metadata) and `page.tsx`.
- Create `app/privacy/layout.tsx`, `app/privacy/page.tsx`.
- Create `app/terms/layout.tsx`, `app/terms/page.tsx`.
- Create `app/tools.css`; modify `app/globals.css` to import it.
- Modify `app/sitemap.ts` — add the three routes.

---

### Task 1: Narrow the OAuth scopes (HUB)

**Files:**
- Modify: `src/hub/connectors/google_auth.py:16-22`
- Modify: `src/hub/connectors/youtube.py:34-37`
- Modify: `src/hub/connectors/google_ads.py:63-71`
- Test: `tests/test_google_auth.py`, `tests/test_youtube.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_google_auth.py`:

```python
def test_base_scopes_exclude_optional_connectors():
    from hub.connectors.google_auth import GOOGLE_ADS_SCOPE, GOOGLE_SCOPES, YOUTUBE_SCOPE

    assert GOOGLE_SCOPES == [
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/webmasters.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
    assert YOUTUBE_SCOPE == "https://www.googleapis.com/auth/yt-analytics.readonly"
    assert GOOGLE_ADS_SCOPE == "https://www.googleapis.com/auth/adwords"
```

Append to `tests/test_youtube.py`:

```python
def test_youtube_requests_its_own_scope(monkeypatch, tmp_path):
    from hub.connectors import youtube as yt_mod
    from hub.connectors.google_auth import GOOGLE_SCOPES, YOUTUBE_SCOPE
    from hub.core.config import ConnectorSettings

    captured = {}

    def fake_get_credentials(secrets_dir, scopes=None, identity=None):
        captured["scopes"] = scopes
        return object()

    monkeypatch.setattr(yt_mod, "get_credentials", fake_get_credentials)
    conn = yt_mod.YouTubeConnector(
        ConnectorSettings(enabled=True, options={}), secrets_dir=tmp_path)
    conn.authenticate()
    assert captured["scopes"] == [*GOOGLE_SCOPES, YOUTUBE_SCOPE]
```

(Check `tests/test_youtube.py` for how `YouTubeConnector` is constructed elsewhere in that file and copy that constructor call if it differs from `ConnectorSettings(enabled=True, options={})`, `secrets_dir=tmp_path`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_google_auth.py::test_base_scopes_exclude_optional_connectors tests/test_youtube.py::test_youtube_requests_its_own_scope -v`
Expected: FAIL — `ImportError: cannot import name 'YOUTUBE_SCOPE'`

- [ ] **Step 3: Implement**

In `src/hub/connectors/google_auth.py` replace lines 16-22 with:

```python
# Only these three go through Google's verification review. Connectors that
# need more (YouTube, Google Ads) add their own scope when configured, so the
# consent screen stays minimal for the 95% who only use GA4 + Search Console.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
```

In `src/hub/connectors/youtube.py`, change the import line to also import `GOOGLE_SCOPES, YOUTUBE_SCOPE` from `hub.connectors.google_auth`, and replace `authenticate` with:

```python
    def authenticate(self) -> None:
        # options.identity picks which Google login owns this channel
        self._creds = get_credentials(
            self.secrets_dir, scopes=[*GOOGLE_SCOPES, YOUTUBE_SCOPE],
            identity=self.settings.options.get("identity"))
```

In `src/hub/connectors/google_ads.py`, before the line `token = json.loads(token_path.read_text(encoding="utf-8"))` (line 71) insert:

```python
        # the shared token may have been minted with only the base scopes;
        # force one re-consent that adds adwords before reading it
        from hub.connectors.google_auth import GOOGLE_ADS_SCOPE, GOOGLE_SCOPES, get_credentials

        get_credentials(self.secrets_dir, scopes=[*GOOGLE_SCOPES, GOOGLE_ADS_SCOPE],
                        identity=opts.get("identity"))
```

(`get_credentials` returns immediately when the cached token already has every requested scope; it only opens a browser when `adwords` is missing.)

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass. If `tests/test_google_ads.py` fails because `get_credentials` now runs in `authenticate`, monkeypatch it in that test the same way as the YouTube test (`monkeypatch.setattr("hub.connectors.google_auth.get_credentials", lambda *a, **k: None)` is not enough because of the local import — patch `hub.connectors.google_auth.get_credentials` before `authenticate()` is called; the local import resolves at call time so that works).

- [ ] **Step 5: Commit**

```bash
git add src/hub/connectors/google_auth.py src/hub/connectors/youtube.py src/hub/connectors/google_ads.py tests/test_google_auth.py tests/test_youtube.py tests/test_google_ads.py
git commit -m "feat: base OAuth scopes limited to GA4/GSC/email; YouTube and Ads add theirs on demand"
```

---

### Task 2: Release constants + tools page (SITE)

**Files:**
- Create: `bhargava-next/lib/hubRelease.ts`
- Create: `bhargava-next/app/tools/marketing-data-hub/layout.tsx`
- Create: `bhargava-next/app/tools/marketing-data-hub/page.tsx`
- Create: `bhargava-next/app/tools.css`
- Modify: `bhargava-next/app/globals.css`

- [ ] **Step 1: Create a branch**

```bash
cd "C:/Users/Laptop-577/Documents/Bhargava-Website"
git status --short
git checkout -b tools/marketing-data-hub
```

(If `git status` shows the five untracked preview PNG / design-system files, leave them alone — they are the user's.)

- [ ] **Step 2: Create `lib/hubRelease.ts`**

```ts
export const HUB_REPO_URL = 'https://github.com/rallabandibhargava-dev/marketing-data-hub';
// Sub-project 3 flips this to
// `${HUB_REPO_URL}/releases/latest/download/MarketingDataHub-Setup.exe`
// once the first tagged release exists. Until then the releases list is the
// only URL that cannot 404.
export const HUB_WINDOWS_DOWNLOAD_URL = `${HUB_REPO_URL}/releases`;
export const HUB_PIP_COMMAND = 'pip install marketing-data-hub && hub setup';
export const HUB_GUIDE_URL = `${HUB_REPO_URL}/blob/master/GUIDE.md`;
export const HUB_PYPI_URL = 'https://pypi.org/project/marketing-data-hub/';
export const HUB_SUPPORT_EMAIL = 'hi@bhargava.work';
```

- [ ] **Step 3: Create `app/tools/marketing-data-hub/layout.tsx`**

```tsx
export const metadata = {
  title: 'Marketing Data Hub — free GA4 & Search Console data on your machine',
  description:
    'An open-source Windsor.ai alternative. Pulls Google Analytics 4 and Search Console into a local database you can query with Claude, an API, or CSV. No hosting, no subscription, your data never leaves your computer.',
  alternates: { canonical: '/tools/marketing-data-hub' },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
```

- [ ] **Step 4: Create `app/tools/marketing-data-hub/page.tsx`**

```tsx
import Link from 'next/link';
import SiteNav from '../../../components/SiteNav';
import LivingFooter from '../../../components/LivingFooter';
import {
  HUB_GUIDE_URL, HUB_PIP_COMMAND, HUB_PYPI_URL, HUB_REPO_URL,
  HUB_SUPPORT_EMAIL, HUB_WINDOWS_DOWNLOAD_URL,
} from '../../../lib/hubRelease';

const steps = [
  ['Install', 'Run the Windows installer, or one pip command. Nothing else to set up.'],
  ['Connect Google', 'Sign in once. The tool only asks for read-only access to Analytics and Search Console.'],
  ['Pick accounts', 'Tick the GA4 properties and Search Console sites you want. Any number, across several Google logins.'],
  ['Ask questions', 'Connect Claude with one click and ask "How did organic traffic do in June vs May?"'],
];

const faqs = [
  ['Where does my data go?', 'Into a database file on your own computer. Nothing is uploaded to me or anyone else — there is no server on my side at all.'],
  ['What does it access?', 'Read-only Google Analytics 4 and Search Console data for accounts you already have access to, plus your email address to label the login. It cannot change anything in your Google account.'],
  ['How do I revoke access?', 'Go to myaccount.google.com/permissions and remove "Marketing Data Hub". Delete the tool\'s folder to remove local data.'],
  ['Is it really free?', 'Yes. MIT-licensed, open source, no plans to charge. Google\'s APIs are free at this volume.'],
  ['Do I need to know how to code?', 'No. The installer opens a step-by-step setup page in your browser. If you can log into Google Analytics, you can use this.'],
];

export default function MarketingDataHubPage() {
  return (
    <>
      <SiteNav />
      <main>
        <section className="page-opener">
          <div className="shell">
            <div className="eyebrow eyebrow--ochre" style={{ marginBottom: 24 }}>Free tool · Open source</div>
            <h1 className="shout-title page-opener__title">
              YOUR MARKETING DATA,<br />ON <span className="ochre">YOUR</span> MACHINE.
            </h1>
            <p className="page-opener__lead">
              Marketing Data Hub pulls Google Analytics 4 and Search Console into one local
              database — then lets you ask Claude questions about it in plain English. No hosted
              service, no subscription, and your tokens never leave your computer.
            </p>
            <div className="tool-cta">
              <a href={HUB_WINDOWS_DOWNLOAD_URL} className="btn btn--ochre">Download for Windows →</a>
              <a href={HUB_GUIDE_URL} className="btn" target="_blank" rel="noreferrer">Read the guide ↗</a>
            </div>
            <p className="tool-cta__note">Windows 10/11 · Mac via pip (below) · v0.4</p>
          </div>
        </section>

        <section className="section-pad-sm tool-steps">
          <div className="shell">
            <div className="eyebrow" style={{ marginBottom: 32 }}>How it works</div>
            <ol className="tool-steps__list">
              {steps.map(([title, body], i) => (
                <li key={title}>
                  <span className="tool-steps__num">0{i + 1}</span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="section-pad-sm tool-install">
          <div className="shell">
            <div className="tool-install__grid">
              <div className="tool-card">
                <div className="eyebrow eyebrow--ochre">Non-technical</div>
                <h3>Windows installer</h3>
                <p>Download, run, and the setup page opens in your browser. Python is included.</p>
                <a href={HUB_WINDOWS_DOWNLOAD_URL} className="btn btn--ochre">Download for Windows →</a>
              </div>
              <div className="tool-card">
                <div className="eyebrow">Comfortable with a terminal</div>
                <h3>pip (Windows &amp; Mac)</h3>
                <p>Python 3.11+ required. Same setup page, same everything.</p>
                <pre className="tool-code"><code>{HUB_PIP_COMMAND}</code></pre>
                <a href={HUB_PYPI_URL} className="link-draw" target="_blank" rel="noreferrer">View on PyPI ↗</a>
              </div>
            </div>
          </div>
        </section>

        <section className="section-pad-sm">
          <div className="shell shell--narrow">
            <div className="eyebrow" style={{ marginBottom: 24 }}>Questions</div>
            <div className="tool-faq">
              {faqs.map(([q, a]) => (
                <details key={q} className="tool-faq__item">
                  <summary>{q}</summary>
                  <p>{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="section-pad-sm">
          <div className="shell shell--narrow">
            <details className="tool-advanced">
              <summary>Advanced: use your own Google Cloud project</summary>
              <div className="bio-prose note-article">
                <p>
                  By default the tool signs you in through my Google app, so there is nothing to
                  configure. If your organisation requires its own OAuth app (or you just prefer
                  it), create one and drop the file in — the tool picks it up automatically.
                </p>
                <ol>
                  <li>Go to <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">console.cloud.google.com</a> and create a project.</li>
                  <li><strong>APIs &amp; Services → Enable APIs</strong>: enable <em>Google Analytics Data API</em>, <em>Google Analytics Admin API</em>, and <em>Google Search Console API</em>.</li>
                  <li><strong>OAuth consent screen</strong>: user type <em>External</em>, fill in the name and email, add yourself under <em>Test users</em>, then <strong>Publish app</strong> (otherwise your login expires every 7 days).</li>
                  <li><strong>Credentials → Create credentials → OAuth client ID</strong>, application type <em>Desktop app</em>, download the JSON.</li>
                  <li>Save it as <code>google_client.json</code> inside the tool&apos;s <code>secrets</code> folder (the setup page shows the exact path) and restart the setup.</li>
                </ol>
              </div>
            </details>
          </div>
        </section>

        <section className="section-pad-sm">
          <div className="shell shell--narrow tool-foot">
            <p>
              Source code on <a href={HUB_REPO_URL} className="link-draw" target="_blank" rel="noreferrer">GitHub ↗</a> ·{' '}
              <Link href="/privacy" className="link-draw">Privacy policy</Link> ·{' '}
              <Link href="/terms" className="link-draw">Terms</Link> ·{' '}
              Questions: <a href={`mailto:${HUB_SUPPORT_EMAIL}`} className="link-draw">{HUB_SUPPORT_EMAIL}</a>
            </p>
          </div>
        </section>
      </main>
      <LivingFooter />
    </>
  );
}
```

- [ ] **Step 5: Create `app/tools.css`**

```css
/* Tools pages (marketing-data-hub, privacy, terms) */
.tool-cta { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 40px; }
.tool-cta__note {
  font-family: var(--font-mono);
  font-size: var(--step-micro);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-50);
  margin-top: 16px;
}

.tool-steps { border-bottom: 0.5px solid var(--rule-light); }
.tool-steps__list {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 40px;
}
.tool-steps__list li { display: flex; flex-direction: column; gap: 10px; }
.tool-steps__num {
  font-family: var(--font-mono);
  font-size: var(--step-meta);
  color: var(--ochre);
}
.tool-steps__list h3 {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 22px;
  letter-spacing: -0.02em;
}
.tool-steps__list p { color: var(--ink-70); font-size: var(--step-small); line-height: 1.55; }
@media (max-width: 900px) { .tool-steps__list { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .tool-steps__list { grid-template-columns: 1fr; } }

.tool-install { border-bottom: 0.5px solid var(--rule-light); }
.tool-install__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 800px) { .tool-install__grid { grid-template-columns: 1fr; } }
.tool-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: flex-start;
  padding: 32px;
  border: 0.5px solid var(--rule-med);
  border-radius: var(--r-lg);
  background: var(--paper);
}
.tool-card h3 {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 26px;
  letter-spacing: -0.02em;
}
.tool-card p { color: var(--ink-70); }
.tool-code {
  width: 100%;
  padding: 14px 18px;
  border-radius: var(--r-md);
  background: var(--ink);
  color: var(--paper);
  font-family: var(--font-mono);
  font-size: 14px;
  overflow-x: auto;
}

.tool-faq { display: flex; flex-direction: column; border-top: 0.5px solid var(--rule-med); }
.tool-faq__item { border-bottom: 0.5px solid var(--rule-med); padding: 18px 0; }
.tool-faq__item summary {
  cursor: pointer;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 19px;
  list-style: none;
}
.tool-faq__item summary::-webkit-details-marker { display: none; }
.tool-faq__item summary::after { content: '+'; float: right; color: var(--ochre); }
.tool-faq__item[open] summary::after { content: '–'; }
.tool-faq__item p { margin-top: 12px; color: var(--ink-70); max-width: var(--measure-text); }

.tool-advanced summary {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: var(--step-meta);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-50);
}
.tool-advanced[open] summary { margin-bottom: 24px; }

.tool-foot p { color: var(--ink-50); font-size: var(--step-small); }

/* Legal pages */
.legal-meta {
  font-family: var(--font-mono);
  font-size: var(--step-meta);
  color: var(--ink-50);
  margin-bottom: 40px;
}
```

- [ ] **Step 6: Import it in `app/globals.css`**

After the line `@import './case.css';` add:

```css
@import './tools.css';
```

- [ ] **Step 7: Build and check**

```bash
cd "C:/Users/Laptop-577/Documents/Bhargava-Website/bhargava-next"
npm run lint
npm run build
```

Expected: lint clean, build lists `/tools/marketing-data-hub` as a static route (○).

- [ ] **Step 8: Commit**

```bash
cd "C:/Users/Laptop-577/Documents/Bhargava-Website"
git add bhargava-next/lib/hubRelease.ts bhargava-next/app/tools bhargava-next/app/tools.css bhargava-next/app/globals.css
git commit -m "feat: Marketing Data Hub tool page"
```

---

### Task 3: Privacy policy page (SITE)

**Files:**
- Create: `bhargava-next/app/privacy/layout.tsx`
- Create: `bhargava-next/app/privacy/page.tsx`

- [ ] **Step 1: Create `app/privacy/layout.tsx`**

```tsx
export const metadata = {
  title: 'Privacy Policy',
  description: 'How Marketing Data Hub and growthbybhargava.com handle your data.',
  alternates: { canonical: '/privacy' },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
```

- [ ] **Step 2: Create `app/privacy/page.tsx`**

```tsx
import Link from 'next/link';
import SiteNav from '../../components/SiteNav';
import LivingFooter from '../../components/LivingFooter';
import { HUB_SUPPORT_EMAIL } from '../../lib/hubRelease';

export default function PrivacyPage() {
  return (
    <>
      <SiteNav />
      <main>
        <section className="page-opener" style={{ paddingBottom: 48 }}>
          <div className="shell shell--narrow">
            <div className="eyebrow eyebrow--ochre" style={{ marginBottom: 20 }}>Legal</div>
            <h1 className="shout-title page-opener__title" style={{ fontSize: 'clamp(40px, 6vw, 88px)' }}>
              Privacy Policy
            </h1>
            <p className="page-opener__lead" style={{ marginTop: 24 }}>
              The short version: Marketing Data Hub runs on your computer, stores your data on your
              computer, and sends nothing to me.
            </p>
          </div>
        </section>

        <section className="section-pad-sm">
          <div className="shell shell--narrow">
            <div className="legal-meta">Effective 14 September 2026 · Applies to the Marketing Data Hub software and growthbybhargava.com</div>
            <div className="bio-prose note-article">
              <h2>1. Who this covers</h2>
              <p>
                This policy is published by Bhargava (&quot;I&quot;, &quot;me&quot;), an independent marketing
                strategist based in Mumbai, India, and covers two things: the open-source
                <strong> Marketing Data Hub</strong> desktop software (&quot;the Software&quot;), and this
                website.
              </p>

              <h2>2. What the Software accesses</h2>
              <p>
                When you connect a Google account, the Software requests these Google OAuth scopes:
              </p>
              <ul>
                <li><code>analytics.readonly</code> — read Google Analytics 4 report data and list the properties you can access.</li>
                <li><code>webmasters.readonly</code> — read Google Search Console performance data and list your sites.</li>
                <li><code>userinfo.email</code> — read the email address of the connected account, used only to label that login inside the Software.</li>
              </ul>
              <p>
                If you enable the optional YouTube or Google Ads connectors, the Software additionally
                requests <code>yt-analytics.readonly</code> or <code>adwords</code> (read-only usage) at
                that time. All access is read-only; the Software cannot modify anything in your Google
                account.
              </p>

              <h2>3. Where your data goes</h2>
              <p>
                <strong>Nowhere but your device.</strong> The Software has no server component. Google
                data it retrieves is written to a database file in a folder on your computer. Your
                OAuth tokens are stored in a file in that same folder. Data flows directly between your
                computer and Google&apos;s APIs; it is never transmitted to me, to this website, or to
                any third party by the Software.
              </p>
              <p>
                If you choose to connect the Software to an AI assistant (for example Claude Desktop via
                MCP), the assistant runs on your machine and reads from your local database. Anything you
                then send to that assistant&apos;s provider is governed by that provider&apos;s privacy
                policy, not this one.
              </p>

              <h2>4. Google API Services User Data Policy</h2>
              <p>
                The Software&apos;s use and transfer of information received from Google APIs adheres to
                the <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">Google API Services User Data Policy</a>,
                including the Limited Use requirements. Specifically: Google user data is used only to
                provide the Software&apos;s features to you on your own device; it is not sold, not used
                for advertising, not transferred to others, and not used to train AI or machine-learning
                models by me.
              </p>

              <h2>5. Retention and deletion</h2>
              <p>
                Because everything lives on your computer, you control retention. To delete all data
                and tokens, delete the Software&apos;s data folder (the setup page shows its location).
                To revoke the Software&apos;s access to your Google account, visit{' '}
                <a href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer">myaccount.google.com/permissions</a> and
                remove &quot;Marketing Data Hub&quot;.
              </p>

              <h2>6. What I do receive</h2>
              <p>
                The Software makes one outbound request to GitHub to check whether a newer version is
                available; this sends no personal data. I receive no telemetry, no usage analytics, and
                no crash reports from the Software. If you email me for support, I will see whatever you
                choose to include.
              </p>

              <h2>7. This website</h2>
              <p>
                growthbybhargava.com uses Google Tag Manager, Google Analytics, and Mixpanel to
                understand how the site is used (pages visited, approximate location, device type). You
                can block these with a standard content blocker or browser privacy setting. The contact
                form sends what you type to my email and nowhere else.
              </p>

              <h2>8. Changes</h2>
              <p>
                If this policy changes, the effective date above is updated. Material changes to what the
                Software accesses will also appear in the Software&apos;s release notes on GitHub.
              </p>

              <h2>9. Contact</h2>
              <p>
                Questions about privacy: <a href={`mailto:${HUB_SUPPORT_EMAIL}`}>{HUB_SUPPORT_EMAIL}</a>.
              </p>
            </div>
            <div className="case-placeholder__actions" style={{ marginTop: 64 }}>
              <Link href="/tools/marketing-data-hub" className="btn">← Marketing Data Hub</Link>
              <Link href="/terms" className="btn">Terms →</Link>
            </div>
          </div>
        </section>
      </main>
      <LivingFooter />
    </>
  );
}
```

- [ ] **Step 3: Build**

Run: `cd "C:/Users/Laptop-577/Documents/Bhargava-Website/bhargava-next" && npm run build`
Expected: `/privacy` appears as a static route.

- [ ] **Step 4: Commit**

```bash
cd "C:/Users/Laptop-577/Documents/Bhargava-Website"
git add bhargava-next/app/privacy
git commit -m "feat: privacy policy page"
```

---

### Task 4: Terms page (SITE)

**Files:**
- Create: `bhargava-next/app/terms/layout.tsx`
- Create: `bhargava-next/app/terms/page.tsx`

- [ ] **Step 1: Create `app/terms/layout.tsx`**

```tsx
export const metadata = {
  title: 'Terms of Use',
  description: 'Terms for using the Marketing Data Hub software.',
  alternates: { canonical: '/terms' },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
```

- [ ] **Step 2: Create `app/terms/page.tsx`**

```tsx
import Link from 'next/link';
import SiteNav from '../../components/SiteNav';
import LivingFooter from '../../components/LivingFooter';
import { HUB_REPO_URL, HUB_SUPPORT_EMAIL } from '../../lib/hubRelease';

export default function TermsPage() {
  return (
    <>
      <SiteNav />
      <main>
        <section className="page-opener" style={{ paddingBottom: 48 }}>
          <div className="shell shell--narrow">
            <div className="eyebrow eyebrow--ochre" style={{ marginBottom: 20 }}>Legal</div>
            <h1 className="shout-title page-opener__title" style={{ fontSize: 'clamp(40px, 6vw, 88px)' }}>
              Terms of Use
            </h1>
            <p className="page-opener__lead" style={{ marginTop: 24 }}>
              Marketing Data Hub is free, open-source software provided as-is.
            </p>
          </div>
        </section>

        <section className="section-pad-sm">
          <div className="shell shell--narrow">
            <div className="legal-meta">Effective 14 September 2026</div>
            <div className="bio-prose note-article">
              <h2>1. The software</h2>
              <p>
                Marketing Data Hub (&quot;the Software&quot;) is published by Bhargava under the MIT
                License. The full licence text is in the{' '}
                <a href={`${HUB_REPO_URL}/blob/master/LICENSE`} target="_blank" rel="noreferrer">LICENSE file</a> of
                the source repository and governs your use, copying, and modification of the code.
              </p>

              <h2>2. Your Google account</h2>
              <p>
                The Software accesses Google services on your behalf using credentials you authorise.
                You are responsible for having the right to access the Google Analytics properties and
                Search Console sites you connect, and for complying with Google&apos;s terms for those
                services. You can revoke the Software&apos;s access at any time from your Google account
                permissions.
              </p>

              <h2>3. No hosted service</h2>
              <p>
                I do not operate any server for the Software and do not store, process, or have access
                to your data. See the <Link href="/privacy">Privacy Policy</Link>.
              </p>

              <h2>4. No warranty</h2>
              <p>
                The Software is provided &quot;as is&quot;, without warranty of any kind, express or
                implied, including but not limited to the warranties of merchantability, fitness for a
                particular purpose, and non-infringement. Data pulled from Google may be incomplete,
                delayed, or sampled by Google; verify important figures against the source before
                relying on them.
              </p>

              <h2>5. Limitation of liability</h2>
              <p>
                To the maximum extent permitted by law, I am not liable for any claim, damages, or other
                liability arising from or in connection with the Software or your use of it.
              </p>

              <h2>6. Support</h2>
              <p>
                Support is best-effort via GitHub issues at{' '}
                <a href={`${HUB_REPO_URL}/issues`} target="_blank" rel="noreferrer">the repository</a> or
                by email at <a href={`mailto:${HUB_SUPPORT_EMAIL}`}>{HUB_SUPPORT_EMAIL}</a>. There is no
                service-level commitment.
              </p>

              <h2>7. Changes</h2>
              <p>
                These terms may be updated; the effective date above will change when they are.
                Continued use of the Software after a change constitutes acceptance.
              </p>

              <h2>8. Governing law</h2>
              <p>These terms are governed by the laws of India.</p>
            </div>
            <div className="case-placeholder__actions" style={{ marginTop: 64 }}>
              <Link href="/privacy" className="btn">← Privacy</Link>
              <Link href="/tools/marketing-data-hub" className="btn btn--ochre">Get the tool →</Link>
            </div>
          </div>
        </section>
      </main>
      <LivingFooter />
    </>
  );
}
```

- [ ] **Step 3: Build**

Run: `cd "C:/Users/Laptop-577/Documents/Bhargava-Website/bhargava-next" && npm run build`
Expected: `/terms` appears as a static route.

- [ ] **Step 4: Commit**

```bash
cd "C:/Users/Laptop-577/Documents/Bhargava-Website"
git add bhargava-next/app/terms
git commit -m "feat: terms of use page"
```

---

### Task 5: Sitemap, visual check, PR (SITE)

**Files:**
- Modify: `bhargava-next/app/sitemap.ts:10-17`

- [ ] **Step 1: Add the routes to the sitemap**

Replace the `staticRoutes` array literal with:

```ts
  const staticRoutes = [
    '',
    '/about',
    '/services',
    '/work',
    '/notes',
    '/contact',
    '/tools/marketing-data-hub',
    '/privacy',
    '/terms',
  ].map((route) => ({
    url: `${siteUrl}${route}`,
    lastModified: now,
    changeFrequency: route === '' ? 'weekly' : 'monthly',
    priority: route === '' ? 1 : route.startsWith('/tools') ? 0.8 : route === '/privacy' || route === '/terms' ? 0.3 : 0.8,
  })) satisfies MetadataRoute.Sitemap;
```

- [ ] **Step 2: Run the dev server and look at all three pages**

Add to `.claude/launch.json` in the SITE repo root if absent:

```json
{
  "version": "0.0.1",
  "configurations": [
    { "name": "site", "runtimeExecutable": "npm", "runtimeArgs": ["run", "dev"], "port": 3000, "cwd": "bhargava-next" }
  ]
}
```

Then use the Browser pane (`preview_start` name `site`) and open `/tools/marketing-data-hub`, `/privacy`, `/terms` at desktop and `mobile` preset. Check: nav renders, hero title wraps sanely on mobile, FAQ `<details>` toggles, the "Advanced" section opens and shows the ordered list, no horizontal scroll on mobile. Fix any CSS in `app/tools.css`.

- [ ] **Step 3: Lint + build once more, commit**

```bash
cd "C:/Users/Laptop-577/Documents/Bhargava-Website/bhargava-next" && npm run lint && npm run build
cd .. && git add bhargava-next/app/sitemap.ts bhargava-next/app/tools.css .claude/launch.json
git commit -m "feat: add tool + legal routes to sitemap"
```

- [ ] **Step 4: Push and open a PR — ASK THE USER FIRST**

Pushing publishes to a shared repo and merging deploys the live site. Confirm with the user, then:

```bash
git push -u origin tools/marketing-data-hub
gh pr create --title "Marketing Data Hub tool page + privacy/terms" --body "$(cat <<'EOF'
## Summary
- New `/tools/marketing-data-hub` landing page (download / pip / FAQ / bring-your-own Google project)
- New `/privacy` and `/terms` pages written to satisfy Google OAuth app verification
- Sitemap updated

## Test plan
- [ ] Vercel preview: all three routes render, mobile layout OK
- [ ] Links: GitHub repo, PyPI, guide, mailto
- [ ] After merge: `curl -I https://growthbybhargava.com/privacy` returns 200

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Vercel builds a preview for the PR; the user merges to `master` to go live.

---

### Task 6: Google verification checklist (HUB)

**Files:**
- Create: `docs/google-verification.md`

- [ ] **Step 1: Write the checklist**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
cd "C:/Users/Laptop-577/Documents/data collection"
git add docs/google-verification.md
git commit -m "docs: Google OAuth verification checklist"
```

- [ ] **Step 3: Hand off**

Tell the user: the website PR is up (link), and `docs/google-verification.md` lists what to click. Sections A (URLs) wait for the merge; everything else can start now.

---

## Self-review

- **Spec coverage:** tools page ✓ (Task 2, includes advanced/own-project section moved from SETUP.md), privacy ✓ (Task 3, includes Limited Use statement + revoke path), terms ✓ (Task 4), sitemap ✓ (Task 5), scopes trimmed with YouTube/Ads opt-in ✓ (Task 1), checklist + screencast ✓ (Task 6). Logo upload is the user's (checklist A).
- **Placeholders:** none; the download button intentionally points at the releases list until sub-project 3 (documented in `hubRelease.ts`).
- **Consistency:** `HUB_*` constant names match across `hubRelease.ts` and the three pages; `YOUTUBE_SCOPE` / `GOOGLE_ADS_SCOPE` names match between Task 1 code and tests.
