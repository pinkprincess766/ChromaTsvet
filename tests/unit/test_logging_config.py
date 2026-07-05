import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from python_analyzer.core import logging_config


class LoggingConfigTest(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("chromatsvet")
        self.original_handlers = list(self.logger.handlers)
        for handler in self.original_handlers:
            self.logger.removeHandler(handler)
        self.original_log_dir = os.environ.get("CHROMATSVET_LOG_DIR")

    def tearDown(self):
        self._remove_managed_handlers()
        for handler in self.original_handlers:
            self.logger.addHandler(handler)
        if self.original_log_dir is None:
            os.environ.pop("CHROMATSVET_LOG_DIR", None)
        else:
            os.environ["CHROMATSVET_LOG_DIR"] = self.original_log_dir

    def _remove_managed_handlers(self):
        for handler in list(self.logger.handlers):
            if getattr(handler, logging_config._HANDLER_MARKER, None):
                self.logger.removeHandler(handler)
                handler.close()

    def test_setup_is_idempotent_and_writes_utf8_log(self):
        with TemporaryDirectory() as temp_dir:
            os.environ["CHROMATSVET_LOG_DIR"] = temp_dir

            first = logging_config.setup_logging(log_filename="test.log")
            original_handler_ids = {id(handler) for handler in first.handlers}
            second = logging_config.setup_logging(log_filename="test.log")
            second.debug("Debug details")
            first.info("Unicode log entry: спектр")
            for handler in first.handlers:
                handler.flush()

            managed_handlers = [
                handler
                for handler in first.handlers
                if getattr(handler, logging_config._HANDLER_MARKER, None)
            ]
            self.assertIs(first, second)
            self.assertEqual(len(managed_handlers), 2)
            self.assertEqual(
                original_handler_ids,
                {id(handler) for handler in second.handlers},
            )
            self.assertTrue(
                any(
                    isinstance(handler, RotatingFileHandler)
                    and handler.level == logging.DEBUG
                    and handler.maxBytes == 5 * 1024 * 1024
                    for handler in managed_handlers
                )
            )
            self.assertIn(
                "Unicode log entry: спектр",
                (Path(temp_dir) / "test.log").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Debug details",
                (Path(temp_dir) / "test.log").read_text(encoding="utf-8"),
            )

    def test_unwritable_candidate_falls_back_without_touching_root_handlers(self):
        with TemporaryDirectory() as temp_dir:
            blocked = Path(temp_dir) / "not-a-directory"
            blocked.write_text("blocked", encoding="utf-8")
            fallback = Path(temp_dir) / "fallback"
            root_handler = logging.NullHandler()
            logging.getLogger().addHandler(root_handler)
            try:
                with patch.object(
                    logging_config,
                    "_log_directory_candidates",
                    return_value=[blocked, fallback],
                ):
                    logger = logging_config.setup_logging(log_filename="fallback.log")
                    logger.info("fallback works")
                    for handler in logger.handlers:
                        handler.flush()

                self.assertIn(root_handler, logging.getLogger().handlers)
                self.assertTrue((fallback / "fallback.log").exists())
            finally:
                logging.getLogger().removeHandler(root_handler)

    def test_file_logging_failure_keeps_stderr_handler(self):
        with TemporaryDirectory() as temp_dir:
            blocked = Path(temp_dir) / "not-a-directory"
            blocked.write_text("blocked", encoding="utf-8")

            with patch.object(
                logging_config,
                "_log_directory_candidates",
                return_value=[blocked],
            ):
                logger = logging_config.setup_logging()

            managed_kinds = {
                getattr(handler, logging_config._HANDLER_MARKER, None)
                for handler in logger.handlers
            }
            self.assertEqual(managed_kinds, {"stderr"})


if __name__ == "__main__":
    unittest.main()
