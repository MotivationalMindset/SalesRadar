# SalesRadar

A job-alert bot that surfaces freshly-posted sales jobs in the Greater Toronto
Area and pushes them to Telegram with pre-drafted application material.

## Purpose

Single user (Musawwir). Runs unattended on GitHub Actions free tier every two
hours, 7am–7pm ET, weekdays. Zero maintenance once the secrets are set.

**It does not apply to anything.** It finds postings, filters out the junk,
drafts the opener and resume tweaks, and sends them to Telegram. A human reads
the alert and applies manually. There is deliberately no code that submits
forms, bypasses CAPTCHAs, or spoofs a browser.

## Audience

One person, on a phone, reading Telegram. Alerts must be scannable in a few
seconds and carry a direct apply link.

## Pipeline

1. **Fetch** from two providers behind a shared `JobProvider` protocol:
   - **Adzuna API** — employer sites and ATS postings, Canadian coverage.
   - **Indeed email alerts** — Gmail API (read-only), parses Indeed's alert
     emails. This is the Indeed coverage; Adzuna does not carry Indeed.
   - A third provider, **JSearch** (RapidAPI), exists but is off by default.
2. **Merge and dedupe** on a slug hash of `company + title + location`, checked
   against a SQLite `seen_jobs` table, so a job found by both providers alerts
   once and never alerts twice.
3. **Filter**, in order — freshness (24h), commission-only rejection, geo
   (25km of Toronto or Vaughan, Ontario only), title relevance.
4. **Draft** with the Anthropic API: a 120-word cover-letter opener, three
   resume bullet tweaks, two interview questions. Cached in SQLite, batched
   across jobs. If it fails, the alert still sends without the draft.
5. **Deliver** to Telegram with `Applied ✅` / `Skip ❌` inline buttons, logged
   back to SQLite for a weekly conversion summary.

## Key decisions

- **Every filter rule lives in `config.yaml`.** Editing the commission
  blocklist, the accepted titles, or the geo radius never requires touching
  Python.
- **`--dry-run` prints what would be filtered and why** and sends nothing.
- **UNCERTAIN, not dropped.** A posting that is genuinely ambiguous on
  commission-vs-base is surfaced with a ⚠️ rather than silently binned — a
  missed real job costs more than one bad alert.
- **State is committed back to the repo** by the workflow so the seen-jobs
  table survives between runs.
- **Gmail OAuth is bootstrapped locally**, once, with `auth_gmail.py`; the
  refresh token goes into a repo secret. GitHub Actions is headless and cannot
  run a consent flow.

## Out of scope for v1

- Applying to anything, in any form.
- More than one user.
- A web UI. Telegram is the whole interface.
- LinkedIn (no compliant API for this).

## Status

Built 2026-08-19. `resume.md` is a placeholder — replace it with the real
resume before the drafts are worth reading.
