"""Cross-provider dedupe and the seen-jobs table."""

from __future__ import annotations

from salesradar.models import Draft

from .fixtures import postings as p


class TestSlug:
    def test_same_posting_from_two_providers_collapses(self):
        adzuna = p.make_job(
            source="adzuna", source_id="a1", company="Riverstone Technologies Inc."
        )
        indeed = p.make_job(
            source="indeed_email", source_id="i1", company="Riverstone Technologies"
        )
        assert adzuna.dedupe_hash == indeed.dedupe_hash

    def test_seniority_prefix_does_not_split_a_match(self):
        a = p.make_job(title="Senior Account Executive")
        b = p.make_job(title="Account Executive")
        assert a.dedupe_hash == b.dedupe_hash

    def test_location_tail_does_not_split_a_match(self):
        a = p.make_job(location="Toronto, ON")
        b = p.make_job(location="Toronto, ON, Canada")
        assert a.dedupe_hash == b.dedupe_hash

    def test_different_companies_stay_distinct(self):
        a = p.make_job(company="Riverstone Technologies")
        b = p.make_job(company="Cardinal Analytics")
        assert a.dedupe_hash != b.dedupe_hash

    def test_different_roles_at_one_company_stay_distinct(self):
        a = p.make_job(title="Account Executive")
        b = p.make_job(title="Account Manager")
        assert a.dedupe_hash != b.dedupe_hash

    def test_different_cities_stay_distinct(self):
        a = p.make_job(location="Toronto, ON")
        b = p.make_job(location="Vaughan, ON")
        assert a.dedupe_hash != b.dedupe_hash

    def test_case_and_punctuation_are_ignored(self):
        a = p.make_job(company="ACME CORP.", title="Account Executive")
        b = p.make_job(company="acme corp", title="account executive")
        assert a.dedupe_hash == b.dedupe_hash


class TestSeenJobs:
    def test_new_job_is_not_seen(self, storage):
        assert not storage.has_seen(p.make_job().dedupe_hash)

    def test_recorded_job_is_seen(self, storage):
        job = p.make_job()
        storage.record_seen(job, alerted=True)
        assert storage.has_seen(job.dedupe_hash)

    def test_recording_twice_is_harmless(self, storage):
        job = p.make_job()
        storage.record_seen(job, alerted=True)
        storage.record_seen(job, alerted=False)
        assert storage.has_seen(job.dedupe_hash)

    def test_filter_unseen_drops_known_jobs(self, storage):
        known = p.make_job(source_id="known")
        storage.record_seen(known, alerted=True)
        fresh = p.make_job(source_id="fresh", company="Cardinal Analytics")

        result = storage.filter_unseen([known, fresh])

        assert len(result) == 1
        assert result[0].company == "Cardinal Analytics"

    def test_filter_unseen_dedupes_within_one_batch(self, storage):
        """Both providers surfacing the same job in one run must alert once."""
        from_adzuna = p.make_job(source="adzuna", source_id="a1")
        from_indeed = p.make_job(source="indeed_email", source_id="i1")

        result = storage.filter_unseen([from_adzuna, from_indeed])

        assert len(result) == 1

    def test_filter_unseen_on_empty_input(self, storage):
        assert storage.filter_unseen([]) == []

    def test_rejected_jobs_are_recorded_so_they_are_not_rescreened(self, storage):
        storage.record_seen(p.COMMISSION_ONLY, alerted=False)
        assert storage.has_seen(p.COMMISSION_ONLY.dedupe_hash)

    def test_hash_prefix_lookup_resolves_a_telegram_callback(self, storage):
        job = p.make_job()
        storage.record_seen(job, alerted=True)

        row = storage.find_by_hash_prefix(job.dedupe_hash[:32])

        assert row is not None
        assert row["dedupe_hash"] == job.dedupe_hash

    def test_hash_prefix_lookup_refuses_a_dangerously_short_prefix(self, storage):
        storage.record_seen(p.make_job(), alerted=True)
        assert storage.find_by_hash_prefix("ab") is None


class TestDraftCache:
    def test_miss_then_hit(self, storage):
        job = p.make_job()
        assert storage.get_draft(job.content_hash) is None

        draft = Draft("Opener text.", ["bullet one"], ["question one?"])
        storage.put_draft(job.content_hash, draft)

        cached = storage.get_draft(job.content_hash)
        assert cached is not None
        assert cached.cover_letter_opener == "Opener text."
        assert cached.resume_bullets == ["bullet one"]

    def test_expired_entries_are_ignored(self, storage):
        job = p.make_job()
        storage.put_draft(job.content_hash, Draft("Old.", [], []))
        assert storage.get_draft(job.content_hash, ttl_days=0) is None

    def test_content_hash_changes_when_the_posting_changes(self):
        a = p.make_job(description="Original description.")
        b = p.make_job(description="Rewritten description.")
        assert a.content_hash != b.content_hash


class TestDecisions:
    def test_recording_and_summarizing(self, storage):
        job = p.make_job()
        storage.record_seen(job, alerted=True)
        storage.record_decision(job.dedupe_hash, "applied")

        summary = storage.weekly_summary()

        assert summary["alerted"] == 1
        assert summary["applied"] == 1
        assert summary["skipped"] == 0

    def test_a_later_press_overwrites_an_earlier_one(self, storage):
        job = p.make_job()
        storage.record_seen(job, alerted=True)
        storage.record_decision(job.dedupe_hash, "skipped")
        storage.record_decision(job.dedupe_hash, "applied")

        summary = storage.weekly_summary()

        assert summary["applied"] == 1
        assert summary["skipped"] == 0

    def test_undecided_alerts_are_counted(self, storage):
        storage.record_seen(p.make_job(source_id="1"), alerted=True)
        storage.record_seen(
            p.make_job(source_id="2", company="Cardinal Analytics"), alerted=True
        )

        summary = storage.weekly_summary()

        assert summary["alerted"] == 2
        assert summary["no_response"] == 2
