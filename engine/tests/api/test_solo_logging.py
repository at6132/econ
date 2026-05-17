"""Solo socket file logging."""

from __future__ import annotations

import logging

import pytest

from realm.api import solo_logging as sl
from realm.api.solo_logging import configure_solo_logging, default_log_path


def test_default_log_path_override(tmp_path, monkeypatch) -> None:
    custom = tmp_path / "custom.log"
    monkeypatch.setenv("REALM_LOG_FILE", str(custom))
    assert default_log_path() == custom


def test_configure_solo_logging_writes_file(tmp_path, monkeypatch) -> None:
    if sl._CONFIGURED:
        pytest.skip("solo logging already configured in this process")
    log_file = tmp_path / "realm_test.log"
    monkeypatch.setenv("REALM_LOG_FILE", str(log_file))
    monkeypatch.setenv("REALM_LOG_LEVEL", "INFO")
    path = configure_solo_logging()
    assert path == log_file
    logging.getLogger("realm.test").warning("hello from test")
    for h in logging.getLogger().handlers:
        if hasattr(h, "flush"):
            h.flush()
    assert log_file.exists()
    assert "hello from test" in log_file.read_text(encoding="utf-8")
