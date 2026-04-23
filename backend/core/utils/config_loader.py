"""Load and merge YAML config files with environment variable overrides."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_config(config_dir: str | Path = "config") -> dict:
    """
    Load all YAML files from config_dir and merge into a single dict.
    Environment variables override:
      SOLANA_RPC_HTTP  → config['rpc']['primary']['http']
      SOLANA_RPC_WS    → config['rpc']['primary']['ws']
      BOT_MODE         → config['bot']['mode']
    """
    load_dotenv()
    config_dir = Path(config_dir)
    merged: dict[str, Any] = {}

    for yaml_file in sorted(config_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f) or {}
        _deep_merge(merged, data)

    # Apply environment variable overrides
    _apply_env_overrides(merged)

    return merged


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(config: dict) -> None:
    rpc = config.setdefault("rpc", {}).setdefault("primary", {})

    if val := os.getenv("SOLANA_RPC_HTTP"):
        rpc["http"] = val
    if val := os.getenv("SOLANA_RPC_WS"):
        rpc["ws"] = val
    if val := os.getenv("BOT_MODE"):
        config.setdefault("bot", {})["mode"] = val


def get_rpc_http(config: dict) -> str:
    return config["rpc"]["primary"]["http"]


def get_rpc_ws(config: dict) -> str:
    return config["rpc"]["primary"]["ws"]


def get_mode(config: dict) -> str:
    return config.get("bot", {}).get("mode", "paper")
