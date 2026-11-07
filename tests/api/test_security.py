"""Access control rules, framework-free (D78, D83)."""
import hmac
import logging

import pytest

from thanzi_screen.api import security
from thanzi_screen.api.security import ConfigError, build_config

GW, AU = "gateway-key-0123456789", "audit-key-0123456789ab"


def test_no_gateway_key_means_no_start():
    with pytest.raises(ConfigError, match="THANZI_GATEWAY_KEY"):
        build_config(env={})
    with pytest.raises(ConfigError):
        build_config(gateway_key="", env={})


def test_dev_mode_is_explicit_and_loud(caplog):
    with caplog.at_level(logging.WARNING, logger="thanzi.security"):
        cfg = build_config(env={"THANZI_DEV_MODE": "1"})
    assert cfg.dev_mode and cfg.gateway_key is None
    assert "DEV MODE" in caplog.text
    assert security.gateway_ok(cfg, None)
    for off in ("0", "true", "yes", ""):
        with pytest.raises(ConfigError):
            build_config(env={"THANZI_DEV_MODE": off})


def test_keys_from_environment_and_arguments():
    cfg = build_config(env={"THANZI_GATEWAY_KEY": GW, "THANZI_AUDIT_KEY": AU})
    assert (cfg.gateway_key, cfg.audit_key, cfg.dev_mode) == (GW, AU, False)
    cfg = build_config(gateway_key=GW, env={"THANZI_GATEWAY_KEY": "x" * 30})
    assert cfg.gateway_key == GW                      # arguments win


def test_weak_or_duplicate_keys_are_refused():
    with pytest.raises(ConfigError, match="at least"):
        build_config(gateway_key="short", env={})
    with pytest.raises(ConfigError, match="at least"):
        build_config(gateway_key=GW, audit_key="short", env={})
    with pytest.raises(ConfigError, match="differ"):
        build_config(gateway_key=GW, audit_key=GW, env={})


def test_gateway_and_audit_checks():
    cfg = build_config(gateway_key=GW, audit_key=AU, env={})
    assert security.gateway_ok(cfg, GW)
    assert not security.gateway_ok(cfg, None) and not security.gateway_ok(cfg, "") and not security.gateway_ok(cfg, GW + "x")
    assert not security.gateway_ok(cfg, AU)           # the audit key is not a gateway key
    assert security.audit_ok(cfg, AU)
    assert not security.audit_ok(cfg, GW) and not security.audit_ok(cfg, None)
    off = build_config(gateway_key=GW, env={})
    assert not security.audit_ok(off, AU) and not security.audit_ok(off, None)     # no audit key: audit is off


def test_key_comparison_is_constant_time(monkeypatch):
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(security.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert security.key_matches(GW, GW) and not security.key_matches("other", GW) and not security.key_matches(None, GW)
    assert len(calls) == 3


def test_non_ascii_header_values_do_not_crash():
    assert not security.key_matches("clé-ünïcode", GW)


def test_keys_are_not_logged(caplog):
    with caplog.at_level(logging.DEBUG):
        build_config(gateway_key=GW, audit_key=AU, env={})
    assert GW not in caplog.text and AU not in caplog.text
