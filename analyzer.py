#!/usr/bin/env python3
"""Compatibility entrypoint for the AlgoScope CLI."""

from __future__ import annotations

from algoscope.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
