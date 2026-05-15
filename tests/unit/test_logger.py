"""Unit tests for logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from chenedusys.core.logger import get_logger, setup_logging


class TestSetupLogging:

    def test_log_to_file(self, tmp_path: Path):
        setup_logging(level="DEBUG", log_dir=str(tmp_path))
        logger = get_logger("test")
        logger.info("hello from test")
        # flush handlers
        for h in logger.handlers:
            h.flush()

        log_file = tmp_path / "chenedusys.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "hello from test" in content

    def test_log_level_respected(self, tmp_path: Path):
        # Reset module state so we can re-initialize
        import chenedusys.core.logger as mod
        mod._initialized = False
        # Clear any existing handlers on the root chenedusys logger
        logging.getLogger("chenedusys").handlers.clear()

        setup_logging(level="WARNING", log_dir=str(tmp_path))
        logger = get_logger("test_level")
        logger.debug("should not appear")
        logger.warning("should appear")

        for h in logger.handlers:
            h.flush()

        content = (tmp_path / "chenedusys.log").read_text()
        assert "should not appear" not in content
        assert "should appear" in content

    def test_get_logger_prefix(self):
        logger = get_logger("mymodule")
        assert logger.name == "chenedusys.mymodule"

    def test_get_logger_full_name(self):
        logger = get_logger("chenedusys.foo.bar")
        assert logger.name == "chenedusys.foo.bar"
