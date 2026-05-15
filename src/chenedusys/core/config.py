"""Application configuration backed by TOML files and env-var overrides."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


_DEFAULT_CONFIG_DIR = Path.home() / ".chenedusys"
_DEFAULT_CONFIG_FILE = _DEFAULT_CONFIG_DIR / "config.toml"


class AppConfig(BaseSettings):
    """Root configuration model.

    Values are resolved in this order (highest priority first):
      1. Environment variables prefixed with ``CHENEDUSYS_``
      2. Values loaded from the TOML config file
      3. Field defaults below
    """

    model_config = SettingsConfigDict(env_prefix="CHENEDUSYS_")

    # -- General ----------------------------------------------------------
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_dir: str = Field(default=str(_DEFAULT_CONFIG_DIR / "logs"))

    # -- Hub / Signaling --------------------------------------------------
    hub_url: str = Field(default="wss://localhost:8443")
    hub_reconnect_delay: float = Field(default=2.0, ge=0.5)
    hub_reconnect_max_delay: float = Field(default=60.0)

    # -- P2P --------------------------------------------------------------
    p2p_port_range_start: int = Field(default=9100, ge=1024, le=65535)
    p2p_port_range_end: int = Field(default=9200, ge=1024, le=65535)
    p2p_stun_servers: list[str] = Field(
        default=["stun:stun.l.google.com:19302"]
    )

    # -- Audio ------------------------------------------------------------
    audio_sample_rate: int = Field(default=48000)
    audio_frame_ms: int = Field(default=20)
    audio_bitrate: int = Field(default=32000)

    # -- UI ---------------------------------------------------------------
    window_width: int = Field(default=1280, ge=640)
    window_height: int = Field(default=720, ge=480)


class ConfigError(Exception):
    """Raised when the config file cannot be loaded."""


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load configuration from TOML file + env vars.

    If *config_path* is ``None`` the default location
    ``~/.chenedusys/config.toml`` is used. Missing files are not an error
    — defaults are used instead.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_FILE

    toml_values: dict = {}
    if path.exists():
        if tomllib is None:
            raise ConfigError(
                "Cannot read TOML config: no 'tomllib' or 'tomli' available. "
                "Upgrade to Python 3.11+ or install tomli."
            )
        try:
            with open(path, "rb") as f:
                toml_values = tomllib.load(f)
        except Exception as exc:
            raise ConfigError(f"Failed to parse {path}: {exc}") from exc

    # TOML values are passed as kwargs, but we must NOT override env vars.
    # pydantic-settings priority: init kwargs > env vars > defaults.
    # So we strip any TOML field that has a matching CHENEDUSYS_* env var,
    # letting pydantic-settings read the env var instead.
    for field_name in list(toml_values.keys()):
        env_name = f"CHENEDUSYS_{field_name.upper()}"
        if env_name in os.environ:
            del toml_values[field_name]

    try:
        return AppConfig(**toml_values)
    except Exception as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc


def save_config(config: AppConfig, config_path: Path | str | None = None) -> None:
    """Persist non-default values back to a TOML file.

    Only fields whose value differs from the default are written, keeping
    the file minimal and readable.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    defaults = AppConfig()
    changed: dict[str, object] = {}
    for field_name in type(config).model_fields:
        current = getattr(config, field_name)
        default = getattr(defaults, field_name)
        if current != default:
            changed[field_name] = current

    lines: list[str] = []
    for key, value in changed.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, list):
            import json
            lines.append(f"{key} = {json.dumps(value)}")
        else:
            lines.append(f"{key} = {value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
