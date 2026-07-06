"""Test setup: put `src/` and the project root on the path; load `.env` once.

`src/` gives flat absolute imports (`import config`, `from extract import ...`); the
project root gives `import data.corpus`. The deterministic suite (`-m "not integration"`)
never touches the network — the SDK is only imported inside the live integration tests.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import config  # noqa: E402

config.load_env()


def anthropic_available() -> bool:
    """Whether live Anthropic API calls are possible (raw SDK needs a real key)."""
    return config.anthropic_key_present()
