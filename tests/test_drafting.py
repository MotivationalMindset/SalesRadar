"""Drafting: caching, batching, JSON extraction, and graceful degradation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from salesradar.drafting import Drafter, _extract_json_array, _parse_response
from salesradar.models import Draft

from .fixtures import postings as p


class FakeClient:
    """Stands in for anthropic.Anthropic, recording what it was asked."""

    def __init__(self, responses: list[str] | None = None, error: Exception | None = None):
        self.responses = responses or []
        self.error = error
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        text = self.responses.pop(0) if self.responses else "[]"
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
        )


def draft_json(ids: list[int]) -> str:
    return json.dumps(
        [
            {
                "id": i,
                "cover_letter_opener": f"Opener for posting {i}.",
                "resume_bullets": [f"bullet {i}a", f"bullet {i}b", f"bullet {i}c"],
                "interview_questions": [f"question {i}a?", f"question {i}b?"],
            }
            for i in ids
        ]
    )


@pytest.fixture
def resume(tmp_path):
    path = tmp_path / "resume.md"
    path.write_text("# Test Candidate\n\nAccount Executive, 5 years B2B SaaS.", "utf-8")
    return path


@pytest.fixture
def draft_config():
    return {
        "enabled": True,
        "model": "claude-sonnet-4-6",
        "max_tokens": 4096,
        "batch_size": 2,
        "cover_letter_words": 120,
        "resume_bullets": 3,
        "interview_questions": 2,
        "cache_ttl_days": 30,
    }


class TestGeneration:
    def test_produces_a_draft_per_job(self, storage, resume, draft_config):
        client = FakeClient([draft_json([0, 1])])
        drafter = Drafter(draft_config, resume, storage, client=client)

        jobs = [p.make_job(source_id="1"), p.make_job(source_id="2", company="Cardinal")]
        drafts = drafter.draft_all(jobs)

        assert len(drafts) == 2
        assert drafts[jobs[0].dedupe_hash].cover_letter_opener == "Opener for posting 0."
        assert len(drafts[jobs[1].dedupe_hash].resume_bullets) == 3

    def test_the_resume_is_sent_as_cached_system_context(
        self, storage, resume, draft_config
    ):
        client = FakeClient([draft_json([0])])
        Drafter(draft_config, resume, storage, client=client).draft_all([p.make_job()])

        system = client.calls[0]["system"]
        assert "Test Candidate" in system[0]["text"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_the_model_is_told_not_to_invent_experience(
        self, storage, resume, draft_config
    ):
        client = FakeClient([draft_json([0])])
        Drafter(draft_config, resume, storage, client=client).draft_all([p.make_job()])

        assert "never invent" in client.calls[0]["system"][0]["text"].lower()


class TestBatching:
    def test_jobs_are_chunked_by_batch_size(self, storage, resume, draft_config):
        draft_config["batch_size"] = 2
        client = FakeClient([draft_json([0, 1]), draft_json([0])])
        drafter = Drafter(draft_config, resume, storage, client=client)

        jobs = [
            p.make_job(source_id=str(i), company=f"Company {i}") for i in range(3)
        ]
        drafter.draft_all(jobs)

        assert len(client.calls) == 2

    def test_a_single_batch_makes_one_call(self, storage, resume, draft_config):
        draft_config["batch_size"] = 10
        client = FakeClient([draft_json([0, 1, 2])])
        drafter = Drafter(draft_config, resume, storage, client=client)

        jobs = [p.make_job(source_id=str(i), company=f"Company {i}") for i in range(3)]
        drafter.draft_all(jobs)

        assert len(client.calls) == 1


class TestCaching:
    def test_a_cached_draft_skips_the_api(self, storage, resume, draft_config):
        job = p.make_job()
        storage.put_draft(job.content_hash, Draft("Cached.", ["b"], ["q?"]))

        client = FakeClient([draft_json([0])])
        drafts = Drafter(draft_config, resume, storage, client=client).draft_all([job])

        assert client.calls == []
        assert drafts[job.dedupe_hash].cover_letter_opener == "Cached."

    def test_generated_drafts_are_written_to_the_cache(
        self, storage, resume, draft_config
    ):
        job = p.make_job()
        client = FakeClient([draft_json([0])])
        Drafter(draft_config, resume, storage, client=client).draft_all([job])

        assert storage.get_draft(job.content_hash) is not None

    def test_only_uncached_jobs_are_sent(self, storage, resume, draft_config):
        cached_job = p.make_job(source_id="1")
        new_job = p.make_job(source_id="2", company="Cardinal Analytics")
        storage.put_draft(cached_job.content_hash, Draft("Cached.", [], []))

        client = FakeClient([draft_json([0])])
        drafts = Drafter(draft_config, resume, storage, client=client).draft_all(
            [cached_job, new_job]
        )

        assert len(client.calls) == 1
        assert "Cardinal" in client.calls[0]["messages"][0]["content"]
        assert len(drafts) == 2


class TestGracefulDegradation:
    def test_an_api_error_returns_no_drafts_rather_than_raising(
        self, storage, resume, draft_config
    ):
        client = FakeClient(error=RuntimeError("503 upstream unavailable"))
        drafter = Drafter(draft_config, resume, storage, client=client)

        assert drafter.draft_all([p.make_job()]) == {}

    def test_a_missing_resume_does_not_raise(self, storage, tmp_path, draft_config):
        client = FakeClient([draft_json([0])])
        drafter = Drafter(draft_config, tmp_path / "nope.md", storage, client=client)

        assert drafter.draft_all([p.make_job()]) == {}

    def test_unparseable_output_yields_no_drafts(self, storage, resume, draft_config):
        client = FakeClient(["I'm sorry, I can't help with that."])
        drafter = Drafter(draft_config, resume, storage, client=client)

        assert drafter.draft_all([p.make_job()]) == {}

    def test_a_partial_response_keeps_what_it_can(self, storage, resume, draft_config):
        """One draft back for two jobs: the second alert simply has no draft."""
        draft_config["batch_size"] = 5
        client = FakeClient([draft_json([0])])
        drafter = Drafter(draft_config, resume, storage, client=client)

        jobs = [p.make_job(source_id="1"), p.make_job(source_id="2", company="Cardinal")]
        drafts = drafter.draft_all(jobs)

        assert len(drafts) == 1

    def test_a_refusal_is_handled(self, storage, resume, draft_config):
        class RefusingClient(FakeClient):
            def _create(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(content=[], stop_reason="refusal")

        drafter = Drafter(draft_config, resume, storage, client=RefusingClient())
        assert drafter.draft_all([p.make_job()]) == {}

    def test_disabled_in_config_makes_it_a_no_op(self, storage, resume, draft_config):
        draft_config["enabled"] = False
        client = FakeClient([draft_json([0])])

        assert Drafter(draft_config, resume, storage, client=client).draft_all(
            [p.make_job()]
        ) == {}
        assert client.calls == []


class TestJsonExtraction:
    def test_bare_array(self):
        assert _extract_json_array('[{"id": 0}]') == '[{"id": 0}]'

    def test_array_wrapped_in_prose(self):
        text = 'Here you go:\n[{"id": 0}]\nHope that helps!'
        assert _extract_json_array(text) == '[{"id": 0}]'

    def test_nested_arrays(self):
        text = '[{"id": 0, "resume_bullets": ["a", "b"]}]'
        assert _extract_json_array(text) == text

    def test_brackets_inside_strings_do_not_confuse_the_scanner(self):
        text = '[{"cover_letter_opener": "I saw your [posting] online"}]'
        assert _extract_json_array(text) == text

    def test_escaped_quotes_are_handled(self):
        text = '[{"cover_letter_opener": "They said \\"hello\\" first"}]'
        assert json.loads(_extract_json_array(text))[0]

    def test_no_array_returns_none(self):
        assert _extract_json_array("no json at all") is None

    def test_parse_maps_by_the_id_field(self):
        parsed = _parse_response(draft_json([0, 1]), expected=2)
        assert set(parsed.keys()) == {0, 1}

    def test_parse_falls_back_to_array_position(self):
        text = json.dumps([{"cover_letter_opener": "A"}, {"cover_letter_opener": "B"}])
        parsed = _parse_response(text, expected=2)
        assert parsed[0]["cover_letter_opener"] == "A"
        assert parsed[1]["cover_letter_opener"] == "B"
