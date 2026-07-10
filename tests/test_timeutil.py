"""Tests for src.timeutil — timezone resolution with a graceful fallback.

The fallback matters because Windows ships no IANA tz database: without the
bundled ``tzdata`` package ``zoneinfo.ZoneInfo`` raises, and before the fix that
zeroed out an entire run. These tests use only synthetic timestamps.
"""

import warnings
import zoneinfo
from datetime import datetime

import pytest

from src import timeutil
from src.timeutil import to_datetime, _resolve_tz, DEFAULT_TIMEZONE


@pytest.fixture(autouse=True)
def _clear_tz_cache():
    timeutil._TZ_CACHE.clear()
    yield
    timeutil._TZ_CACHE.clear()


def test_to_datetime_default_zone_regression():
    """When tzdata IS available, default-zone behaviour is unchanged.

    0 ms epoch = 1970-01-01 00:00 UTC = 04:00 in Asia/Tbilisi (UTC+4).
    """
    dt = to_datetime(0)
    assert dt.utcoffset().total_seconds() == 4 * 3600
    assert (dt.hour, dt.minute) == (4, 0)


def test_resolve_tz_returns_zoneinfo_when_available():
    tz = _resolve_tz(DEFAULT_TIMEZONE)
    assert isinstance(tz, zoneinfo.ZoneInfo)


def test_resolve_tz_falls_back_and_warns_once(monkeypatch):
    """ZoneInfo raising -> fallback tzinfo, cached, warns exactly once."""
    def boom(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)

    monkeypatch.setattr(zoneinfo, "ZoneInfo", boom)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tz = _resolve_tz("Asia/Tbilisi")
        tz2 = _resolve_tz("Asia/Tbilisi")  # cached — must not warn again

    assert tz is not None
    assert tz is tz2
    runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert len(runtime_warnings) == 1


def test_to_datetime_still_buckets_under_fallback(monkeypatch):
    """A missing tz database must never blow up to_datetime; buckets computable."""
    def boom(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)

    monkeypatch.setattr(zoneinfo, "ZoneInfo", boom)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dt = to_datetime(1_600_000_000_000)

    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None          # still timezone-aware
    assert 0 <= dt.hour <= 23             # hour-of-day bucket still works
