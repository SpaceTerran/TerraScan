"""Configuration loader."""

import os
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class Config:
    """Configuration from YAML file."""

    # AI settings
    provider: str = "openai"
    model: str = "gpt-5.2-codex"
    ollama_url: str = "http://localhost:11434"
    max_tokens: int = 16000
    temperature: float = 0.2

    # Gitea settings
    gitea_url: str = ""

    # Review behavior
    fail_on_severity: str = "critical"
    max_comments: int = 50
    ignore_patterns: list = field(default_factory=list)

    # Display
    bot_name: str = "AI Code Review"
    bot_emoji: str = "🤖"
    severity_icons: dict = field(default_factory=dict)

    # Impact analysis settings
    impact_analysis_enabled: bool = True
    impact_token_budget: int = 6000
    impact_max_files: int = 10
    impact_include_references: bool = True


def load_config() -> Config:
    """Load config from YAML files."""
    config_dir = Path("/app/config")

    # Load main config
    main_file = config_dir / "review-config.yml"
    data = {}
    if main_file.exists():
        with open(main_file) as f:
            data = yaml.safe_load(f) or {}

    # Apply custom overrides if mounted
    custom_file = config_dir / "custom.yml"
    if custom_file.exists():
        with open(custom_file) as f:
            overrides = yaml.safe_load(f) or {}
        data.update(overrides)

    # Validate required
    if not data.get("gitea_url"):
        raise ValueError("gitea_url is required in config")

    return Config(**{k: v for k, v in data.items() if hasattr(Config, k)})
