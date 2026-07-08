"""Application settings access."""

DEFAULTS = {"timeout": 30, "retries": 3, "verbose": False}


def get(key, source):
    """Read a setting from source, falling back to the default."""
    try:
        return source.read(key)
    except Exception:
        return DEFAULTS.get(key)
