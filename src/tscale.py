"""Timeout scaling for slow/remote environments (e.g. GitHub runners)."""
import os

SCALE = float(os.environ.get("TIMEOUT_SCALE", "1"))


def T(ms: int) -> int:
    return int(ms * SCALE)
