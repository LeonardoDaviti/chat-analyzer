#!/usr/bin/env python3
"""CLI entry point for the interactive HTML dashboard exporter.

Usage:
    python build_dashboard.py [--chat substr,substr] [--exclude substr,substr]
                              [--output-dir Outputs] [--dash-dir Dashboard]

Scans ``Outputs/*`` for the latest analysed run of each chat and writes a
self-contained, offline dashboard to ``Dashboard/`` at the repo root. See
``src/dashboard_export.py`` for the implementation.
"""

import sys

from src.dashboard_export import main

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
