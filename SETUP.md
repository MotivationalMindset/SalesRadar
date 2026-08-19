# Setting up SalesRadar

This guide assumes you have never used a terminal and don't want to start now.
Almost everything happens in a web browser. There is exactly one step (step 6)
that needs you to run a command on your own computer, and it is copy-and-paste.

Set aside about 45 minutes. You can stop after any step and come back.

**What you're building:** a bot that checks for new sales jobs in Toronto and
Vaughan every two hours during the workday, throws away the commission-only
junk, writes you a first draft of the application, and sends it to Telegram on
your phone. It never applies to anything — you read the alert and decide.

---

## Before you start

You'll need accounts for five services. All free.

| What | Cost | Used for |
|---|---|---|
| GitHub | Free | Runs the bot on a schedule |
| Adzuna | Free | Job listings from employer sites |
| Telegram | Free | Where the alerts arrive |
| Google | Free | A dedicated Gmail for Indeed alerts |
| Anthropic | Pay as you go, a few dollars a month | Writes the application drafts |

---

## Step 1 — Copy the project to your own GitHub account

1. Make a GitHub account at **https://github.com/signup** if you don't have one.
2. Go to the SalesRadar repository page.
3. Click the **Fork** button, near the top right.
4. On the next page, click **Create fork**.

You now have your own copy. Everything else in this guide happens inside it.

> **Keep it private if you like.** Click **Settings → General → Change
> visibility** to make it private. Everything still works. Private repos get
> 2,000 free Actions minutes a month; SalesRadar uses roughly 200.

---

## Step 2 — Get your Adzuna keys

Adzuna supplies the job listings that come from company websites and applicant
tracking systems.

1. Go to **https://developer.adzuna.com/signup**
2. Fill in the form. For "What are you building?" write something like
   *"A personal job alert tool for my own job search."*
3. Check your email and click the confirmation link.
4. Sign in at **https://developer.adzuna.com/admin/access_details**
5. You'll see **Application ID** and **Application Key**.

**Leave this tab open.** You'll paste both values in step 7.

---

## Step 3 — Get your Anthropic API key

This is what writes your cover-letter openers and resume tweaks.

1. Go to **https://console.anthropic.com/**
2. Sign up or sign in.
3. Click **Get API keys** (or go to Settings → API keys).
4. Click **Create Key**, name it `SalesRadar`, and click **Add**.
5. **Copy the key immediately** — it starts with `sk-ant-` and is shown only
   once. Paste it into a notes app for the moment.
6. Go to **Billing** and add $5 of credit. At the volume SalesRadar runs, $5
   lasts a long time — it drafts only for jobs that survive the filters, and
   caches every draft it writes.

---

## Step 4 — Create your Telegram bot

Telegram is where the alerts land. Two parts: creating the bot, then finding
your own chat ID so it knows where to send.

### 4a. Create the bot

1. Install Telegram on your phone if you haven't: **https://telegram.org/**
2. In Telegram, search for **@BotFather** — the one with the blue checkmark.
3. Tap **Start**.
4. Send: `/newbot`
5. It asks for a name. Send: `SalesRadar`
6. It asks for a username, which must end in `bot`. Try:
   `musawwir_salesradar_bot` (if taken, add numbers).
7. BotFather replies with a message containing a **token** that looks like
   `7284759301:AAHqK9x-vBnM3pQrStUvWxYz...`

**Copy that token.** That's `TELEGRAM_BOT_TOKEN`.

### 4b. Find your chat ID

The bot needs to know which chat to send to — yours.

1. In Telegram, search for the bot you just made (the username from step 6).
2. Tap **Start** and send it any message, like `hello`. **This matters** — a
   bot cannot message you first.
3. Now open this URL in your browser, replacing `<TOKEN>` with your token:

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

   So it looks like `https://api.telegram.org/bot7284759301:AAHqK9x.../getUpdates`

4. You'll see a wall of text. Look for `"chat":{"id":123456789`

**That number is your `TELEGRAM_CHAT_ID`.** It's usually 9-10 digits. If you
see `{"ok":true,"result":[]}` with nothing in it, you skipped sending the bot
a message — go back to 4b step 2.

---

## Step 5 — Set up the Indeed job alerts

Adzuna doesn't carry Indeed listings, so SalesRadar gets them a different way:
Indeed emails you job alerts, and the bot reads that mailbox.

### 5a. Make a dedicated Gmail account

**Use a brand new account, not your personal one.** You'll be giving the bot
permission to read this mailbox, and it should only ever contain job alerts.

1. Go to **https://accounts.google.com/signup**
2. Create something like `musawwir.jobalerts@gmail.com`
3. Write the password down somewhere safe.

### 5b. Create the Indeed alerts

Do this twice — once for Toronto, once for Vaughan.

1. Go to **https://ca.indeed.com/** and sign in (or sign up) using the **new
   Gmail address**.
2. In the search box, type **sales**. In the location box, type
   **Toronto, ON**. Press **Find jobs**.
3. On the results page, find the **Date posted** filter and choose
   **Last 24 hours**.
4. Scroll to the bottom and find **Get new jobs for this search by email** (it
   may say "Activate" or show an envelope icon).
5. Confirm the email address is your new one, and click **Activate**.
6. Check the new Gmail inbox and click Indeed's confirmation link.

**Now repeat all six steps with "Vaughan, ON"** as the location.

> **Getting the settings right matters.** The alert must be Sales / the right
> city / Last 24 hours. If you set it to weekly, SalesRadar will only see
> Indeed jobs once a week.

---

## Step 6 — Authorize the bot to read that Gmail

This is the one step that needs your own computer. Google won't let a server
grant itself mailbox access — a human has to click "Allow" in a browser once.
After this, the bot runs unattended forever.

### 6a. Create Google credentials

1. Go to **https://console.cloud.google.com/**, signed in as the **new Gmail
   account**.
2. At the top, click the project dropdown, then **New Project**. Name it
   `SalesRadar` and click **Create**.
3. In the search bar at the top, type **Gmail API** and click the result.
   Click **Enable**.
4. In the left menu, go to **APIs & Services → OAuth consent screen**.
   - User type: **External** → **Create**
   - App name: `SalesRadar`
   - User support email: your new Gmail
   - Developer contact: your new Gmail
   - Click **Save and Continue** through the remaining pages.
   - On the **Test users** page, click **+ Add users**, enter your new Gmail
     address, and save. *(Without this, Google blocks the sign-in.)*
5. Go to **APIs & Services → Credentials**.
6. Click **+ Create Credentials → OAuth client ID**.
   - Application type: **Desktop app**
   - Name: `SalesRadar`
   - Click **Create**, then **Download JSON**.
7. Rename the downloaded file to exactly **`client_secret.json`**.

### 6b. Run the authorization once

1. Install Python from **https://www.python.org/downloads/** if you don't have
   it. **On Windows, tick "Add Python to PATH"** on the first install screen.
2. Download your forked repository: on your GitHub repo page, click the green
   **Code** button → **Download ZIP**, then unzip it.
3. Move `client_secret.json` into that unzipped folder, next to `auth_gmail.py`.
4. Open the folder, then open a terminal *in that folder*:
   - **Windows:** click the address bar at the top of the File Explorer
     window, type `cmd`, press Enter.
   - **Mac:** right-click the folder → Services → New Terminal at Folder.
5. Paste these two lines, pressing Enter after each:

   ```
   pip install -r requirements.txt
   python auth_gmail.py
   ```

6. A browser window opens. Sign in with the **new Gmail account**.
7. You'll see **"Google hasn't verified this app"** — this is expected, it's
   your own app. Click **Advanced** → **Go to SalesRadar (unsafe)**.
8. Click **Continue** to grant access.
9. The terminal prints three values. **Keep this window open** — you need all
   three in the next step.

> **Why can it modify and not just read?** After reading an alert email the bot
> marks it read, so the next run doesn't process it again. Marking read is
> technically a modification, which read-only permission forbids. If you'd
> rather it never touch the mailbox at all, open `config.yaml`, set
> `mark_read_after_parse: false`, and re-run `python auth_gmail.py --readonly`.

---

## Step 7 — Paste everything into GitHub

This is where all those values go. GitHub stores them encrypted; they are never
visible in the code or the logs.

1. Go to your forked repository on GitHub.
2. Click **Settings** (the tab along the top of the repo, not your profile).
3. In the left sidebar: **Secrets and variables** → **Actions**.
4. Click **New repository secret**.
5. For each row below: type the **Name** exactly as shown, paste the value,
   click **Add secret**, then click **New repository secret** again.

| Name (type exactly) | Where it came from |
|---|---|
| `ADZUNA_APP_ID` | Step 2, Application ID |
| `ADZUNA_APP_KEY` | Step 2, Application Key |
| `ANTHROPIC_API_KEY` | Step 3, starts with `sk-ant-` |
| `TELEGRAM_BOT_TOKEN` | Step 4a, from BotFather |
| `TELEGRAM_CHAT_ID` | Step 4b, the number |
| `GMAIL_CLIENT_ID` | Step 6b terminal output |
| `GMAIL_CLIENT_SECRET` | Step 6b terminal output |
| `GMAIL_REFRESH_TOKEN` | Step 6b terminal output |

Eight secrets. Names are case-sensitive, and a stray space at the end of a
pasted value will break it.

---

## Step 8 — Add your resume

The drafts are only as good as what the bot knows about you. It is explicitly
instructed never to invent an employer, a number, or a credential — so with the
placeholder resume in place, you'll get vague, useless drafts.

1. In your repository, click on **`resume.md`**.
2. Click the **pencil icon** (Edit this file).
3. Delete everything and paste in your real resume. Plain text is fine —
   formatting doesn't matter, specifics do. Real numbers matter most: quota
   attainment, deal sizes, cycle length.
4. Scroll down, click **Commit changes**.

---

## Step 9 — Test it

1. Click the **Actions** tab in your repository.
2. If you see "Workflows aren't being run on this forked repository", click
   **I understand my workflows, go ahead and enable them**.
3. In the left sidebar, click **SalesRadar**.
4. Click **Run workflow** on the right. **Tick the "Dry run" box** for the
   first test — it filters everything and prints the reasoning without sending
   anything or writing anything down.
5. Click the green **Run workflow** button.
6. Wait about a minute, refresh, and click into the run. Click the **run** job,
   then expand **Run SalesRadar**.

You'll see every posting it found and the exact rule that accepted or rejected
each one. If that looks sensible, run it again with the dry-run box **unticked**
and check your Telegram.

From here it runs by itself, every two hours from 7am to 7pm Eastern on
weekdays. On Friday evening it also posts a summary of how many jobs you were
alerted to and how many you applied for.

---

## Using it day to day

Each alert has two buttons, **Applied ✅** and **Skip ❌**. Tapping one logs
your choice so the Friday summary means something. Nothing else happens — the
bot never applies for you.

The button press is recorded on the *next* run, up to two hours later, so the
message won't update instantly. That's normal.

---

## When something goes wrong

**No alerts at all.** Check the Actions tab for a red ✗. Click into the failed
run and read the error — they name the missing secret directly.

**"Missing Telegram secret(s)".** A secret name is misspelled. They are
case-sensitive.

**"Adzuna rejected the credentials (401)".** The ID and key were swapped, or a
space got pasted along with the value. Re-copy both.

**Nothing from Indeed.** Check the dedicated Gmail — are the alert emails
actually arriving? If not, the Indeed alert wasn't confirmed (step 5b, item 6).
If they are arriving but nothing comes through, look in the Actions log for
"selectors have probably drifted" — that means Indeed changed its email layout.
See "Fixing the Indeed parser" below.

**Alerts arrive but with no drafts.** The alert always sends even when drafting
fails, which is deliberate. Check that `ANTHROPIC_API_KEY` is set and that your
Anthropic account has credit.

**Too many junk postings getting through.** Open `config.yaml` and add the
company name to `mlm_companies`, or the phrase to `commission_only_phrases`.
Commit, then run with dry-run ticked to confirm it's now caught. No code
changes needed — every rule lives in that file.

**Good jobs being rejected.** Same file. Run a dry run first: it prints the
rule that rejected each posting, so you know exactly which list to edit.

### Fixing the Indeed parser

Indeed rewrites its alert emails every so often. When it does, SalesRadar fails
loudly rather than silently reporting zero jobs, and writes the raw HTML into
the Actions log.

Open `config.yaml` and find `providers.indeed_email.selectors`. Each entry is a
list tried in order. Add the new selector at the top of the list and leave the
old ones underneath as fallbacks. If reading HTML isn't your thing, paste the
logged HTML into Claude and ask which CSS selectors now match the job title,
company, and location.

---

## What it costs

| | |
|---|---|
| GitHub Actions | Free (~200 of 2,000 monthly minutes) |
| Adzuna | Free tier, well under the limit |
| Telegram | Free |
| Gmail / Google Cloud | Free |
| Anthropic | Roughly $1–3/month at typical volume |
