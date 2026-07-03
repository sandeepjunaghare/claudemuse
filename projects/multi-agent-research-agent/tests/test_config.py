"""Unit: config constants (model tiers) + env path resolution. No SDK, no credentials."""

import config


def test_model_tiers():
    """Coordinator is Opus-tier; workers are Sonnet-tier (TR: model tiering)."""
    assert config.COORDINATOR_MODEL == "claude-opus-4-8"
    assert config.WORKER_MODEL == "claude-sonnet-4-6"
    assert config.COORDINATOR_MODEL != config.WORKER_MODEL


def test_orchestration_constants():
    assert config.MCP_SERVER_NAME == "research"
    assert config.MAX_TURNS_BACKSTOP > 0
    assert config.MAX_REFINEMENT_ITERATIONS >= 1  # defined now, used in Phase 3


def test_workspace_env_path_resolves():
    """`parents[3]` from src/config.py must land on the monorepo-root `.env`."""
    assert config._WORKSPACE_ENV.name == ".env"
    assert config._WORKSPACE_ENV.exists()
