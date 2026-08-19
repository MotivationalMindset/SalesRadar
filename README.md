# SalesRadar

Finds newly-posted sales jobs in the Greater Toronto Area, throws out the
commission-only junk, drafts the application material, and sends it to
Telegram. Runs itself on GitHub Actions, free.

**It does not apply to anything.** It surfaces postings and pre-drafts what
you'd send. You read the alert and submit manually. There is deliberately no
code here that automates form submission, bypasses CAPTCHAs, or spoofs a
browser fingerprint.

Setting it up for the first time: **[SETUP.md](SETUP.md)** — written for
someone who has never opened a terminal.

---

## What an alert looks like

```
🎯 Account Executive @ Riverstone Technologies
📍 Toronto, ON · 💰 $70,000–$135,000
⏱️ Posted 2 hours ago
Apply here
———
Cover letter opener
Riverstone's move into mid-market logistics is the reason I'm writing...

Resume tweaks
• Closed $1.2M in new ARR against a $950K quota (126%)
• Ran full-cycle deals averaging 47 days and $38K ACV
• Built the outbound motion for the Ontario mid-market segment

Ask them
1. What does ramp look like for a new AE on this team?
2. How is the Ontario territory split today?

[ Applied ✅ ]  [ Skip ❌ ]
```

Tapping a button logs the choice, which feeds the Friday conversion summary.

---

## How it works

```
Adzuna API ─────┐
                ├──▶ merge + dedupe ──▶ filters ──▶ draft ──▶ Telegram
Indeed emails ──┘     (slug hash)         │          │
   (Gmail API)                            │          └─ Anthropic API
                                          │             (cached, batched)
                                   1. freshness   < 24h
                                   2. commission  the money filter
                                   3. geo         25km of Toronto/Vaughan
                                   4. title       SDR/BDR/AE/AM/BD
```

**Two providers, because Adzuna does not carry Indeed.** Adzuna covers employer
sites and applicant tracking systems; Indeed coverage comes from parsing the
job-alert emails Indeed sends to a dedicated Gmail account. Both implement the
same `JobProvider` protocol, so the sources are swappable. A third, JSearch on
RapidAPI, ships disabled.

**Dedupe is on a normalized slug**, not a raw string: `company + title +
location` with corporate suffixes and seniority prefixes stripped, then hashed.
"Riverstone Technologies Inc." from Adzuna and "Riverstone Technologies" from
Indeed collapse to one alert. The hash lands in a SQLite table, so nothing is
ever alerted twice.

**The commission filter is the one that earns its keep.** It weighs red flags
against evidence of a real base salary rather than running a single blocklist:

| | |
|---|---|
| Hard flags + base evidence | **UNCERTAIN** — sent with a ⚠️ |
| Any flag, no base evidence | **REJECT** |
| Base evidence, no hard flags | **ACCEPT** |

Hard flags are things that contradict a base: "commission only", 1099 and
contractor language, known MLM operators (Primerica, WFG, Cydcor, Vector...).
Soft flags — "uncapped commission", "unlimited earning potential" — only count
when nothing establishes a base, because a good AE posting says "$70k base plus
uncapped commission" and rejecting that would throw away the best jobs.

Ambiguity is surfaced, never dropped. A false reject is silent and permanent;
a false accept costs ten seconds of reading.

---

## Every rule lives in `config.yaml`

Retuning the bot never requires touching Python. The commission blocklist, the
accepted titles, the geo radius and anchors, the Indeed CSS selectors, the
drafting batch size — all of it is in that one file.

```yaml
filters:
  commission:
    min_base_salary_cad: 40000
    mlm_companies:
      - "primerica"
      - "cydcor"
```

After editing, run a dry run to see what changed.

---

## Running it locally

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m salesradar --dry-run
```

The venv is worth the extra line on macOS: a stock Mac has `python3` but no
`python`, and a Homebrew Python refuses `pip install` outright with
`externally-managed-environment`. Activating a venv resolves both.

`--dry-run` fetches and filters, then prints every posting with the exact rule
that accepted or rejected it. It sends nothing and records nothing.

```
WOULD ALERT (3)
  [PASS]      Account Executive @ Northbound Software Inc.
               Toronto, ON · $70,000–$120,000 · adzuna
               + freshness: posted 3.0h ago
               + commission: base pay evidence: salary_min $70,000 >= $40,000
               + geo: 0.0km from Toronto
               + title: title matched "account executive"

WOULD FILTER OUT (4)
  [REJECT]    Sales Representative @ Apex Marketing Group
               - commission: commission-only indicators: "commission only",
                 "100% commission", "1099", "independent contractor" (+2 more)
```

Other flags: `--weekly-summary`, `--config PATH`, `--log-format text`.

---

## Tests

```bash
python -m pytest tests/ -v
```

183 tests. Every filter rule is covered with real-world-shaped fixtures — the
MLM samples are worded the way Primerica and Cydcor ads actually read, so a
regression in the commission filter shows up as a failing test rather than as
junk in your Telegram.

The tests load the **real** `config.yaml`, so the shipped rules are what gets
tested. Change a rule and break a test, and that is the suite doing its job.

---

## Layout

```
salesradar/
  cli.py             argument parsing, entry point
  runner.py          fetch → dedupe → screen → draft → deliver
  config.py          loads config.yaml
  models.py          Job, Draft, FilterResult, dedupe slug
  storage.py         SQLite: seen jobs, draft cache, decisions
  drafting.py        Anthropic API, cached and batched
  telegram_out.py    alerts out, button presses in
  gmail_auth.py      refresh-token credentials
  providers/
    base.py          the JobProvider protocol
    adzuna.py        employer sites and ATS
    indeed_email.py  Indeed coverage via Gmail
    jsearch.py       optional, disabled by default
  filters/
    pipeline.py      ordering, dry-run report
    freshness.py     < 24h
    commission.py    the money filter
    geo.py           haversine + text fallback
    title.py         role relevance
```

---

## Things worth knowing

**Button presses land on the next run.** SalesRadar is a cron job, not a
long-lived process — nothing is listening between runs. Presses queue on
Telegram's side and are drained at the start of the next run via `getUpdates`,
so a decision is recorded within two hours rather than instantly. Fine for a
weekly summary; worth knowing before you file a bug.

**State is committed back to the repo.** The SQLite file is pushed by the
workflow after each run. That's how the seen-jobs table survives a fresh runner
every two hours. The workflow rebases and retries on a push race.

**The Gmail scope is `gmail.modify`, not `gmail.readonly`.** Marking an alert
email read is a modification, and read-only forbids it. Set
`mark_read_after_parse: false` in `config.yaml` and re-run
`python auth_gmail.py --readonly` if you'd rather the bot never touch the
mailbox; the seen-jobs table absorbs the resulting re-reads.

**Drafting fails soft.** If the Anthropic call fails for any reason, the alert
still goes out with a "No draft generated" note. A missing cover letter is an
inconvenience; a missed job posting is the actual failure.

**Indeed's email HTML drifts.** When the selectors stop matching, the parser
raises and logs the raw HTML rather than quietly reporting zero jobs — a silent
zero is indistinguishable from a quiet job market. Selectors are an ordered
list in `config.yaml`: add the new one at the top, leave the old ones below as
fallbacks.
