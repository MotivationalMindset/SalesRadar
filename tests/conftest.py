"""Shared fixtures. Tests load the real config.yaml so they test shipped rules.

If a rule in config.yaml changes and a test breaks, that is the test doing its
job — the config is the behaviour, not just a settings file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from salesradar.config import load_config  # noqa: E402
from salesradar.storage import Storage  # noqa: E402


@pytest.fixture(scope="session")
def config():
    """The real shipped config.yaml."""
    return load_config(ROOT / "config.yaml")


@pytest.fixture
def commission_rules(config):
    return config.filter_section("commission")


@pytest.fixture
def geo_rules(config):
    return config.filter_section("geo")


@pytest.fixture
def title_rules(config):
    return config.filter_section("title")


@pytest.fixture
def freshness_rules(config):
    return config.filter_section("freshness")


@pytest.fixture
def storage(tmp_path):
    """A throwaway database per test."""
    with Storage(tmp_path / "test.db") as store:
        yield store


@pytest.fixture
def alert_html():
    return (Path(__file__).parent / "fixtures" / "indeed_alert.html").read_text(
        encoding="utf-8"
    )
