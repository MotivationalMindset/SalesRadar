"""Filter 3 — geography. Within 25km of Toronto or Vaughan, Ontario only.

Coordinates are the reliable signal and are used whenever a provider supplies
them. Indeed alert emails carry only a location string, so there is a text
fallback: an explicit US/remote-US phrase rejects, a recognized Ontario town
accepts, and a bare "Remote" with no Ontario signal anywhere is rejected as
likely out of province.
"""

from __future__ import annotations

import math
from typing import Any

from ..models import FilterResult, Job, Verdict

RULE = "geo"

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def check(job: Job, config: dict[str, Any]) -> FilterResult:
    location = job.location.lower()
    haystack = f"{location} {job.title.lower()}"

    # Hard rejects first — a US posting is out regardless of anything else.
    for phrase in config.get("reject_location_phrases", []):
        if phrase.lower() in haystack:
            return FilterResult(
                Verdict.REJECT, RULE, f'location matched "{phrase}" (outside Ontario)'
            )

    radius = float(config.get("radius_km", 25))
    anchors = config.get("anchors", [])

    if job.latitude is not None and job.longitude is not None:
        return _check_coords(job, anchors, radius)

    return _check_text(job, location, config, radius)


def _check_coords(
    job: Job, anchors: list[dict[str, Any]], radius: float
) -> FilterResult:
    assert job.latitude is not None and job.longitude is not None

    nearest_name = ""
    nearest_km = float("inf")

    for anchor in anchors:
        distance = haversine_km(
            job.latitude, job.longitude, float(anchor["lat"]), float(anchor["lon"])
        )
        if distance < nearest_km:
            nearest_km = distance
            nearest_name = str(anchor.get("name", "anchor"))

    if nearest_km <= radius:
        return FilterResult(
            Verdict.ACCEPT, RULE, f"{nearest_km:.1f}km from {nearest_name}"
        )

    return FilterResult(
        Verdict.REJECT,
        RULE,
        f"{nearest_km:.1f}km from nearest anchor ({nearest_name}), "
        f"outside the {radius:.0f}km radius",
    )


def _check_text(
    job: Job, location: str, config: dict[str, Any], radius: float
) -> FilterResult:
    """No coordinates — fall back to matching the location string."""
    ontario_tokens = [t.lower() for t in config.get("ontario_tokens", [])]
    remote_tokens = [t.lower() for t in config.get("remote_tokens", [])]

    is_remote = any(t in location for t in remote_tokens)

    # The location field is authoritative, so it is searched on its own first.
    # Only if it says nothing recognizable do we fall back to the description —
    # otherwise a posting in Mississauga whose blurb mentions "Ontario" would
    # report the province instead of the city, which is useless when debugging
    # a --dry-run.
    matched_town = next((t for t in ontario_tokens if t in location), None)
    if matched_town is None:
        full = f"{location} {job.description.lower()}"
        matched_town = next((t for t in ontario_tokens if t in full), None)

    if matched_town:
        note = "remote but " if is_remote else ""
        return FilterResult(
            Verdict.ACCEPT,
            RULE,
            f'{note}location text matched "{matched_town}" (no coordinates given)',
        )

    if is_remote:
        return FilterResult(
            Verdict.REJECT,
            RULE,
            "remote posting with no Ontario or GTA signal — likely out of province",
        )

    if not location.strip():
        # An empty location with nothing to go on is not worth alerting about.
        return FilterResult(Verdict.REJECT, RULE, "no location given and no coordinates")

    if config.get("require_province", True):
        province_tokens = [t.lower() for t in config.get("province_tokens", [])]
        if any(t in location for t in province_tokens):
            return FilterResult(
                Verdict.UNCERTAIN,
                RULE,
                f'"{job.location}" reads as Ontario but is not a recognized GTA town '
                f"and has no coordinates to check against the {radius:.0f}km radius",
            )

    return FilterResult(
        Verdict.REJECT,
        RULE,
        f'"{job.location}" is not a recognized Ontario/GTA location',
    )
