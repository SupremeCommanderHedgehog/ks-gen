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
          - "ssh-rsa BBBB a@b"
        sudo: nopasswd_yes
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


def test_exit_code_tailoring_drift_is_8() -> None:
    from ks_gen.loader import ExitCode

    assert int(ExitCode.TAILORING_DRIFT) == 8


def test_stig_with_fips_mode_false_is_a_rule_conflict(tmp_path):
    """#84: opting out of kernel FIPS under STIG is a conflict, not bad syntax."""
    p = tmp_path / "host.yaml"
    p.write_text(
        "system: {hostname: h.example.com}\n"
        "crypto: {policy: STIG}\n"
        "overrides: {fips_mode: false}\n"
        "user:\n"
        "  admin:\n"
        "    name: ops\n"
        '    authorized_keys: ["ssh-rsa AAAA a@b"]\n'
        "    sudo: nopasswd_yes\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as e:
        load_host_config(p, sets=[])
    assert e.value.exit_code == ExitCode.RULE_CONFLICT


def test_ubuntu_stig_with_fips_mode_true_is_a_rule_conflict(tmp_path):
    """#84: kernel FIPS on Ubuntu needs a Pro entitlement ks-gen doesn't manage."""
    p = tmp_path / "host.yaml"
    p.write_text(
        "system: {hostname: h.example.com}\n"
        "distro: ubuntu2404\n"
        "crypto: {policy: STIG}\n"
        "overrides: {fips_mode: true}\n"
        "user:\n"
        "  admin:\n"
        "    name: ops\n"
        '    authorized_keys: ["ssh-rsa AAAA a@b"]\n'
        "    sudo: nopasswd_yes\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as e:
        load_host_config(p, sets=[])
    assert e.value.exit_code == ExitCode.RULE_CONFLICT


def test_two_malformed_fields_is_not_a_rule_conflict(tmp_path):
    """Two unrelated field errors can jointly contain both substrings; that's not a conflict."""
    p = tmp_path / "host.yaml"
    p.write_text(
        "system: {hostname: h.example.com}\n"
        "crypto: {policy: BOGUS}\n"
        "overrides: {fips_mode: [1, 2, 3]}\n"
        "user:\n"
        "  admin:\n"
        "    name: ops\n"
        '    authorized_keys: ["ssh-rsa AAAA a@b"]\n'
        "    sudo: nopasswd_yes\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as e:
        load_host_config(p, sets=[])
    assert e.value.exit_code == ExitCode.CONFIG_INVALID
