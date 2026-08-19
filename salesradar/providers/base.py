"""The JobProvider protocol every source implements.

A provider's only job is to return normalized `Job` objects. It does no
filtering, no dedupe, and no alerting — the pipeline owns all of that, so
swapping a source in or out never changes behaviour downstream.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import Job


class ProviderError(RuntimeError):
    """A provider could not fetch. The run continues without that source."""


@runtime_checkable
class JobProvider(Protocol):
    """Anything that can hand back postings."""

    #: Short stable identifier, stored on every Job as `source`.
    name: str

    def fetch(self) -> list[Job]:
        """Return postings from this source.

        Should raise `ProviderError` on a failure the pipeline can survive.
        The pipeline logs it and carries on with the remaining providers, so a
        broken Gmail token never costs you the Adzuna results.
        """
        ...
