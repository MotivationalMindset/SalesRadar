"""The geo filter — coordinates when available, location text when not."""

from __future__ import annotations

import pytest

from salesradar.filters import geo
from salesradar.models import Verdict

from .fixtures import postings as p


class TestHaversine:
    def test_zero_distance(self):
        assert geo.haversine_km(43.6532, -79.3832, 43.6532, -79.3832) == pytest.approx(0.0)

    def test_toronto_to_vaughan(self):
        """~22km apart, which is why both anchors are needed for a 25km radius."""
        distance = geo.haversine_km(43.6532, -79.3832, 43.8361, -79.4983)
        assert 20 < distance < 25

    def test_toronto_to_ottawa(self):
        distance = geo.haversine_km(43.6532, -79.3832, 45.4215, -75.6972)
        assert 340 < distance < 360


class TestCoordinates:
    def test_downtown_toronto_accepted(self, geo_rules):
        result = geo.check(p.make_job(), geo_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "Toronto" in result.reason

    def test_vaughan_accepted_via_its_own_anchor(self, geo_rules):
        result = geo.check(p.VAUGHAN_JOB, geo_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "Vaughan" in result.reason

    def test_ottawa_rejected(self, geo_rules):
        result = geo.check(p.OTTAWA_JOB, geo_rules)
        assert result.verdict is Verdict.REJECT
        assert "outside" in result.reason

    def test_chicago_rejected_on_text_before_coordinates(self, geo_rules):
        result = geo.check(p.CHICAGO_JOB, geo_rules)
        assert result.verdict is Verdict.REJECT
        assert "united states" in result.reason.lower()

    def test_barrie_is_outside_the_radius(self, geo_rules):
        """Ontario, but ~80km north — the radius is the point of the filter."""
        assert geo.check(p.BARRIE_EDGE, geo_rules).verdict is Verdict.REJECT

    def test_mississauga_coords_accepted(self, geo_rules):
        job = p.make_job(location="Mississauga, ON", latitude=43.5890, longitude=-79.6441)
        assert geo.check(job, geo_rules).verdict is Verdict.ACCEPT


class TestTextFallback:
    def test_known_gta_town_without_coordinates(self, geo_rules):
        result = geo.check(p.MISSISSAUGA_NO_COORDS, geo_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "mississauga" in result.reason.lower()

    def test_remote_us_rejected(self, geo_rules):
        result = geo.check(p.REMOTE_US, geo_rules)
        assert result.verdict is Verdict.REJECT

    def test_remote_with_ontario_signal_accepted(self, geo_rules):
        result = geo.check(p.REMOTE_ONTARIO, geo_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "remote" in result.reason.lower()

    def test_remote_with_no_signal_rejected(self, geo_rules):
        result = geo.check(p.REMOTE_NOWHERE, geo_rules)
        assert result.verdict is Verdict.REJECT
        assert "out of province" in result.reason

    def test_empty_location_rejected(self, geo_rules):
        job = p.make_job(location="", description="A sales job.", latitude=None, longitude=None)
        assert geo.check(job, geo_rules).verdict is Verdict.REJECT

    def test_unknown_ontario_town_is_uncertain_not_rejected(self, geo_rules):
        """Reads as Ontario but isn't a listed GTA town and has no coordinates.
        Flagged for a human rather than silently binned."""
        job = p.make_job(
            location="Guelph, ON",
            description="Sales role at our facility.",
            latitude=None,
            longitude=None,
        )
        assert geo.check(job, geo_rules).verdict is Verdict.UNCERTAIN

    @pytest.mark.parametrize(
        "location",
        ["Toronto, ON", "North York, ON", "Etobicoke", "Thornhill, ON", "Markham, ON"],
    )
    def test_gta_towns_accepted(self, geo_rules, location):
        job = p.make_job(location=location, latitude=None, longitude=None)
        assert geo.check(job, geo_rules).verdict is Verdict.ACCEPT
