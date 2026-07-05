"""Central configuration constants for the analysis pipeline.

Keeping a single source of truth for the session-gap threshold prevents the
"two conflicting session definitions" problem (BUG_REPORT B3): the pipeline
chunker and every V3 metric now derive sessions with the SAME gap.
"""

# Gap (in hours) above which two consecutive messages belong to different
# conversation sessions. Used by both the session chunker and the V3 metrics.
SESSION_GAP_HOURS = 2.0
SESSION_GAP_MS = int(SESSION_GAP_HOURS * 60 * 60 * 1000)

# Minimum messages for a valid (non-micro) session.
MIN_SESSION_MESSAGES = 3

# Minimum duration (seconds) for a valid session.
MIN_SESSION_DURATION_S = 30

# Tiny sessions are only merged into an adjacent session if the gap between them
# is within this many minutes; otherwise they are kept as micro-interactions.
MERGE_THRESHOLD_MINUTES = 60

# Default timezone re-exported for convenience.
from src.timeutil import DEFAULT_TIMEZONE  # noqa: E402,F401
