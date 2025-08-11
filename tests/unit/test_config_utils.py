import os

from app.utils import EnvConfig


def test_env_config_parsers(monkeypatch):
    monkeypatch.setenv("X_STR", "hello")
    monkeypatch.setenv("X_BOOL_T", "true")
    monkeypatch.setenv("X_BOOL_F", "0")
    monkeypatch.setenv("X_INT", "42")
    monkeypatch.setenv("X_FLOAT", "3.14")

    cfg = EnvConfig()

    assert cfg.get_str("X_STR") == "hello"

    assert cfg.get_bool("X_BOOL_T") is True
    assert cfg.get_bool("X_BOOL_F") is False
    assert cfg.get_bool("X_BOOL_UNKNOWN", default=True) is True

    assert cfg.get_int("X_INT") == 42
    assert cfg.get_int("X_INT_BAD", default=7) == 7

    assert cfg.get_float("X_FLOAT") == 3.14
    assert cfg.get_float("X_FLOAT_BAD", default=2.71) == 2.71


def test_get_str_required(monkeypatch):
    cfg = EnvConfig()
    import pytest
    with pytest.raises(RuntimeError):
        cfg.get_str_required("MISSING_ENV_VAR_FOR_TEST")

    monkeypatch.setenv("NEEDED", "ok")
    assert cfg.get_str_required("NEEDED") == "ok"
