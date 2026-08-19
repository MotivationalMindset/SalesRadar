"""Loads config.yaml and exposes it as attribute-friendly typed sections.

Every filter rule lives in the YAML file, not in code. This module's only job
is to read it, validate the handful of things whose absence would fail later in
a confusing way, and hand back plain dicts the filters can read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(RuntimeError):
    """Raised when config.yaml is missing or structurally wrong."""


@dataclass(frozen=True)
class Config:
    """Parsed config.yaml plus the project root paths derived from it."""

    raw: dict[str, Any]
    root: Path

    # --- sections -----------------------------------------------------------

    @property
    def search(self) -> dict[str, Any]:
        return self.raw.get("search", {})

    @property
    def providers(self) -> dict[str, Any]:
        return self.raw.get("providers", {})

    @property
    def filters(self) -> dict[str, Any]:
        return self.raw.get("filters", {})

    @property
    def drafting(self) -> dict[str, Any]:
        return self.raw.get("drafting", {})

    @property
    def telegram(self) -> dict[str, Any]:
        return self.raw.get("telegram", {})

    @property
    def storage(self) -> dict[str, Any]:
        return self.raw.get("storage", {})

    @property
    def logging(self) -> dict[str, Any]:
        return self.raw.get("logging", {})

    # --- derived paths ------------------------------------------------------

    @property
    def db_path(self) -> Path:
        configured = self.storage.get("db_path", "data/salesradar.db")
        path = Path(configured)
        return path if path.is_absolute() else self.root / path

    @property
    def resume_path(self) -> Path:
        configured = self.drafting.get("resume_path", "resume.md")
        path = Path(configured)
        return path if path.is_absolute() else self.root / path

    # --- helpers ------------------------------------------------------------

    def filter_section(self, name: str) -> dict[str, Any]:
        """Return one filter's rules, or an empty dict if it isn't configured."""
        return self.filters.get(name, {}) or {}

    def provider_section(self, name: str) -> dict[str, Any]:
        return self.providers.get(name, {}) or {}

    def provider_enabled(self, name: str) -> bool:
        return bool(self.provider_section(name).get("enabled", False))


_REQUIRED_SECTIONS = ("search", "providers", "filters", "drafting", "telegram")
_REQUIRED_FILTERS = ("freshness", "commission", "geo", "title")


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Read config.yaml. `path` defaults to config.yaml beside the package."""
    root = Path(__file__).resolve().parent.parent
    config_path = Path(path) if path else root / "config.yaml"

    if not config_path.exists():
        raise ConfigError(
            f"config.yaml not found at {config_path}. "
            "Copy the one from the repo root or pass --config."
        )

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} did not parse to a mapping.")

    missing = [s for s in _REQUIRED_SECTIONS if s not in data]
    if missing:
        raise ConfigError(f"config.yaml is missing section(s): {', '.join(missing)}")

    missing_filters = [f for f in _REQUIRED_FILTERS if f not in data.get("filters", {})]
    if missing_filters:
        raise ConfigError(
            "config.yaml filters section is missing: " + ", ".join(missing_filters)
        )

    # config.yaml lives at the repo root; everything relative resolves from there.
    return Config(raw=data, root=config_path.resolve().parent)
