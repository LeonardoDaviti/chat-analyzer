"""Shared timestamp helper.

Instagram exports store timestamps as UTC epoch milliseconds. Interpreting them
with the analyst machine's local timezone (the default behaviour of
``datetime.fromtimestamp``) shifts every hour-of-day / day-of-week / daily bucket
by the local UTC offset. This module provides ONE place that converts an epoch-ms
value into a timezone-aware datetime, so every metric agrees on what day/hour a
message belongs to regardless of where the pipeline runs.

All ``datetime.fromtimestamp`` calls in the codebase must go through
``to_datetime`` (see BUG_REPORT A4).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# Default timezone for interpreting timestamps. Instagram stores UTC epoch ms;
# this project's data is a Tbilisi conversation, so bucket by Tbilisi wall-clock.
DEFAULT_TIMEZONE = "Asia/Tbilisi"


def to_datetime(timestamp_ms, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """Convert an epoch-milliseconds value to a timezone-aware datetime.

    Args:
        timestamp_ms: Unix timestamp in milliseconds (UTC epoch).
        timezone: IANA timezone name used to render wall-clock fields.

    Returns:
        A timezone-aware ``datetime`` in the requested timezone.
    """
    return datetime.fromtimestamp((timestamp_ms or 0) / 1000, tz=ZoneInfo(timezone))
