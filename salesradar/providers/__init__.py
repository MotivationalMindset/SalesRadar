"""Job sources behind the JobProvider protocol."""

from .base import JobProvider, ProviderError

__all__ = ["JobProvider", "ProviderError"]
