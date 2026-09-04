import pytest

from app.config import Settings


def test_upload_limit_defaults_to_25_mib(monkeypatch):
    monkeypatch.delenv("MAX_UPLOAD_MIB", raising=False)
    assert Settings().max_upload == 25 * 1024 * 1024


def test_upload_limit_can_be_configured_but_is_bounded(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MIB", "30")
    assert Settings().max_upload == 30 * 1024 * 1024
    monkeypatch.setenv("MAX_UPLOAD_MIB", "0")
    with pytest.raises(ValueError, match="MAX_UPLOAD_MIB"):
        Settings()
