"""Shared timestamp helper.

Instagram exports store timestamps as UTC epoch milliseconds. Interpreting them
with the analyst machine's local timezone (the default behaviour of
``datetime.fromtimestamp``) shifts every hour-of-day / day-of-week / daily bucket
by the local UTC offset. This module provides ONE place that converts an epoch-ms
value into a timezone-aware datetime, so every metric agrees on what day/hour a
message belongs to regardless of where the pipeline runs.

All ``datetime.fromtimestamp`` calls in the codebase must go through
``to_datetime`` (see BUG_REPORT A4).

Timezone resolution is resilient: on platforms without an IANA tz database
(notably Windows without the ``tzdata`` package), ``ZoneInfo`` raises. Rather
than let every ``to_datetime`` call blow up — which zeroed out an entire Windows
run in the field — we fall back to the machine's local timezone and warn once.
"""

from datetime import datetime, timezone
import warnings

# Default timezone for interpreting timestamps. Instagram stores UTC epoch ms;
# this project's data is a Tbilisi conversation, so bucket by Tbilisi wall-clock.
DEFAULT_TIMEZONE = "Asia/Tbilisi"

# Cache resolved tzinfo objects. Besides avoiding a repeated (and possibly
# failing) ZoneInfo construction per message, this ensures the fallback warning
# fires at most once per timezone name.
_TZ_CACHE = {}


def _resolve_tz(name):
    """Resolve an IANA timezone name to a tzinfo, with a safe fallback.

    Returns the requested :class:`zoneinfo.ZoneInfo` when the tz database is
    available. If it is not (e.g. Windows without ``tzdata``), returns the
    system local timezone (or UTC as a last resort) and warns once.
    """
    if name in _TZ_CACHE:
        return _TZ_CACHE[name]
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(name)
    except Exception:                      # ZoneInfoNotFoundError, ImportError, ...
        tz = datetime.now().astimezone().tzinfo or timezone.utc
        warnings.warn(
            f"IANA timezone '{name}' unavailable (no tz database?); "
            f"falling back to the system timezone {tz}. Hour-of-day "
            f"buckets will use this machine's clock.", RuntimeWarning)
    _TZ_CACHE[name] = tz
    return tz


def to_datetime(timestamp_ms, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """Convert an epoch-milliseconds value to a timezone-aware datetime.

    Args:
        timestamp_ms: Unix timestamp in milliseconds (UTC epoch).
        timezone: IANA timezone name used to render wall-clock fields.

    Returns:
        A timezone-aware ``datetime`` in the requested timezone (or the system
        local timezone if the tz database is unavailable).
    """
    return datetime.fromtimestamp((timestamp_ms or 0) / 1000,
                                  tz=_resolve_tz(timezone))
