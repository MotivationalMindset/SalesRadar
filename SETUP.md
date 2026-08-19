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

You'll need accounts for four services, all free — plus one optional paid one
if you want the application drafting.

| What | Cost | Used for | |
|---|---|---|---|
| GitHub | Free | Runs the bot on a schedule | Required |
| Adzuna | Free | Job listings from employer sites | Required |
| Telegram | Free | Where the alerts arrive | Required |
| Google | Free | A dedicated Gmail for Indeed alerts | Required |
| Anthropic | ~$1–3/month | Writes the application drafts | **Optional** |

Skipping the last one is a supported setup, not a degraded one — you still get
every job alert, just without the pre-written cover letter. Step 3 covers both
paths.

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

## Step 3 — Application drafting (optional)

This is the part that writes your cover-letter openers and resume bullets.
**You can skip it entirely** — everything else works without it, free.

### Option A — Skip it (free, nothing to sign up for)

You still get every job alert: title, company, salary, how fresh the posting
is, the apply link, and the Applied/Skip buttons. You just write your own
cover letter, which is what most people do anyway.

1. In your repository, click on **`config.yaml`**.
2. Click the **pencil icon** (Edit this file).
3. Near the bottom, find the line that says `enabled: true` directly under
   `drafting:` and change it to:

   ```yaml
   drafting:
     enabled: false
   ```

4. Scroll down and click **Commit changes**.

That's it. Skip step 8 too (no resume needed), and leave `ANTHROPIC_API_KEY`
out of your secrets in step 7 — seven secrets instead of eight.

You can switch this on later at any time by flipping the line back.

### Option B — Turn drafting on

> **This is not a Claude subscription, and a ChatGPT subscription won't work
> here.** Chat subscriptions and developer APIs are separate products with
> separate billing — a subscription can't be called by a script. What you're
> creating below is a pay-as-you-go developer account with a small prepaid
> balance on it.

1. Go to **https://console.anthropic.com/**
2. Sign up or sign in.
3. Click **Get API keys** (or go to Settings → API keys).
4. Click **Create Key**, name it `SalesRadar`, and click **Add**.
5. **Copy the key immediately** — it starts with `sk-ant-` and is shown only
   once. Paste it into a notes app for the moment.
6. Go to **Billing** and add $5 of credit.

$5 lasts months at this volume. Drafts are only written for postings that
survive all four filters — a handful a day — every draft is cached so a
reappearing job never costs twice, and jobs are batched so your resume is sent
once per batch rather than once per job. Expect $1–3 a month.

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

First, download your forked repository: on your GitHub repo page, click the
green **Code** button → **Download ZIP**. Double-click the ZIP to unpack it.
Then move `client_secret.json` into that unpacked folder, so it sits next to
`auth_gmail.py`.

Now follow the section for your computer.

---

#### On a Mac

1. **Check whether you have Python.** Open **Terminal** (press `Cmd + Space`,
   type `terminal`, press Enter) and paste:

   ```
   python3 --version
   ```

   If it prints a version number (3.9 or higher), you're set. If it says
   "command not found", or offers to install developer tools, install Python
   from **https://www.python.org/downloads/macos/** and then close and reopen
   Terminal.

2. **Point Terminal at the folder.** Type `cd` followed by a space — then
   **drag the unpacked SalesRadar folder from Finder onto the Terminal
   window** and let go. It fills in the path for you. Press Enter.

   ```
   cd 
   ```

   *(Don't hunt for a right-click option — macOS hides "New Terminal at
   Folder" until you enable it in System Settings, so dragging is faster.)*

3. **Set up an isolated Python environment.** Paste these two lines, pressing
   Enter after each:

   ```
   python3 -m venv .venv
   ```

   ```
   source .venv/bin/activate
   ```

   Your prompt now starts with `(.venv)`. This keeps SalesRadar's packages
   away from the rest of your Mac, and it's also what makes the plain `python`
   and `pip` commands work — on a stock Mac they don't exist otherwise.

4. **Install and run.** Two more lines:

   ```
   pip install -r requirements.txt
   ```

   ```
   python auth_gmail.py
   ```

5. Jump to **"What happens next"** below.

> **If `pip install` fails with "externally-managed-environment"**, you skipped
> step 3. Run those two `venv` lines and try again.

---

#### On Windows

1. Install Python from **https://www.python.org/downloads/** if you don't have
   it. **Tick "Add Python to PATH"** on the first install screen — it's easy
   to miss and nothing works without it.
2. Open the unpacked folder in File Explorer, click the **address bar** at the
   top, type `cmd`, and press Enter.
3. Paste these lines, pressing Enter after each:

   ```
   python -m venv .venv
   ```

   ```
   .venv\Scripts\activate
   ```

   ```
   pip install -r requirements.txt
   ```

   ```
   python auth_gmail.py
   ```

---

#### What happens next

1. A browser window opens by itself. Sign in with the **new Gmail account**
   from step 5a — not your personal one.
2. You'll see **"Google hasn't verified this app"**. That's expected; it's
   your own app, and Google flags anything that hasn't been through its review
   process. Click **Advanced**, then **Go to SalesRadar (unsafe)**.
3. Click **Continue** to grant access.
4. Back in the terminal, three values are printed. **Leave this window open** —
   you'll paste all three into GitHub in the next step.

> **Nothing gets uploaded anywhere.** The authorization happens between your
> browser and Google; the token is printed straight to your own terminal.

> **Why can it modify and not just read?** After reading an alert email the bot
> marks it read, so the next run doesn't process it again. Marking read is
> technically a modification, which read-only permission forbids. If you'd
> rather it never touch the mailbox at all, open `config.yaml`, set
> `mark_read_after_parse: false`, and re-run the authorization with
> `python auth_gmail.py --readonly`. (Reopening Terminal later? Re-run
> `source .venv/bin/activate` on a Mac, or `.venv\Scripts\activate` on
> Windows, before the command works again.)

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
| `ANTHROPIC_API_KEY` | Step 3 **Option B only** — skip this row if you chose Option A |
| `TELEGRAM_BOT_TOKEN` | Step 4a, from BotFather |
| `TELEGRAM_CHAT_ID` | Step 4b, the number |
| `GMAIL_CLIENT_ID` | Step 6b terminal output |
| `GMAIL_CLIENT_SECRET` | Step 6b terminal output |
| `GMAIL_REFRESH_TOKEN` | Step 6b terminal output |

Eight secrets, or seven if you skipped drafting. Names are case-sensitive,
and a stray space at the end of a pasted value will break it.

---

## Step 8 — Add your resume (Option B only)

**Skip this step entirely if you chose Option A in step 3.** The resume is only
used as context for the drafting, so with drafting off it's never read.

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
