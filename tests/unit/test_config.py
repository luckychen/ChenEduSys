"""Unit tests for config system."""

from __future__ import annotations

from pathlib import Path

import pytest

from chenedusys.core.config import AppConfig, ConfigError, load_config, save_config


class TestLoadConfig:

    def test_load_from_toml_file(self, tmp_path: Path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('log_level = "DEBUG"\nhub_url = "wss://hub.example.com"\n')
        config = load_config(cfg_file)
        assert config.log_level == "DEBUG"
        assert config.hub_url == "wss://hub.example.com"

    def test_env_var_overrides_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('log_level = "DEBUG"\n')
        monkeypatch.setenv("CHENEDUSYS_LOG_LEVEL", "WARNING")
        config = load_config(cfg_file)
        assert config.log_level == "WARNING"

    def test_missing_file_uses_defaults(self, tmp_path: Path):
        config = load_config(tmp_path / "nonexistent.toml")
        assert config.log_level == "INFO"
        assert config.p2p_port_range_start == 9100

    def test_invalid_toml_syntax(self, tmp_path: Path):
        cfg_file = tmp_path / "bad.toml"
        cfg_file.write_text("this is not valid toml {{{{")
        with pytest.raises(ConfigError, match="Failed to parse"):
            load_config(cfg_file)

    def test_invalid_field_value(self, tmp_path: Path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('log_level = "NOTALEVEL"\n')
        with pytest.raises(ConfigError, match="Invalid configuration"):
            load_config(cfg_file)

    def test_unknown_field_rejected(self, tmp_path: Path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('totally_unknown_field = true\n')
        with pytest.raises(ConfigError):
            load_config(cfg_file)

    def test_all_defaults_are_valid(self):
        config = AppConfig()
        assert config.log_level == "INFO"
        assert config.audio_sample_rate == 48000
        assert config.window_width == 1280


class TestSaveConfig:

    def test_save_writes_changed_fields_only(self, tmp_path: Path):
        cfg_file = tmp_path / "config.toml"
        config = AppConfig(log_level="DEBUG")
        save_config(config, cfg_file)
        content = cfg_file.read_text()
        assert 'log_level = "DEBUG"' in content
        # default fields should NOT appear
        assert "window_width" not in content

    def test_round_trip(self, tmp_path: Path):
        cfg_file = tmp_path / "config.toml"
        original = AppConfig(log_level="DEBUG", hub_url="wss://myhub.com")
        save_config(original, cfg_file)
        loaded = load_config(cfg_file)
        assert loaded.log_level == original.log_level
        assert loaded.hub_url == original.hub_url

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        nested = tmp_path / "a" / "b" / "config.toml"
        save_config(AppConfig(), nested)
        assert nested.exists()
