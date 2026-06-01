import textwrap

import pytest

from ks_gen.config import CryptoPolicy
from ks_gen.loader import ConfigError, ExitCode, load_host_config

MIN_YAML = textwrap.dedent(
    """\
    system:
      hostname: web01.example.com
    user:
      admin:
        name: opsadmin
        authorized_keys:
          - "ssh-ed25519 AAAA a@b"
    """
)


def test_load_minimal_yaml(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    cfg = load_host_config(f, sets=[])
    assert cfg.system.hostname == "web01.example.com"
    assert cfg.crypto.policy == CryptoPolicy.MODERN


def test_set_overrides_string(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    cfg = load_host_config(f, sets=["ssh.port=2222"])
    assert cfg.ssh.port == 2222


def test_set_overrides_bool_and_nested(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    cfg = load_host_config(f, sets=["overrides.fips_mode=true", "crypto.policy=STIG"])
    assert cfg.crypto.policy == CryptoPolicy.STIG
    assert cfg.overrides.fips_mode is True


def test_set_invalid_syntax_raises(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_host_config(f, sets=["ssh.port"])
    assert exc.value.exit_code == ExitCode.USAGE


def test_crypto_fips_conflict_returns_exit_3(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_host_config(f, sets=["overrides.fips_mode=true"])
    assert exc.value.exit_code == ExitCode.RULE_CONFLICT
