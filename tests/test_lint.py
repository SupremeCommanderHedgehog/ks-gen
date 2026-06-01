import textwrap
from pathlib import Path

from ks_gen.lint import lint_kickstart
from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle, write_bundle

YAML = textwrap.dedent(
    """\
    system: {hostname: web01.example.com}
    user:
      admin:
        name: opsadmin
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
    """
)


def _generate(tmp_path) -> Path:
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    out = tmp_path / "out"
    write_bundle(bundle, out)
    return out


def test_lint_accepts_known_good(tmp_path):
    out = _generate(tmp_path)
    report = lint_kickstart(out / "ks.cfg")
    assert report.ok, report.failures


def test_lint_detects_missing_authorized_keys(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8").replace(".ssh/authorized_keys", ".ssh/DISARMED")
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok
    assert any("authorized_keys" in f for f in report.failures)


def test_lint_detects_sshd_before_admin(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8")
    # Swap order: cut admin block, paste after sshd block
    admin_marker = "# ===== admin_user_and_keys ====="
    sshd_marker = "# ===== ssh_config_apply ====="
    a = text.index(admin_marker)
    b = text.index(sshd_marker)
    text = text[:a] + text[b : b + 200] + text[a:b] + text[b + 200 :]
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok


def test_lint_detects_missing_pre_tailoring_fetcher(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8")
    # Remove the %pre header line so the block is no longer recognisable
    text = text.replace(
        "%pre --erroronfail --log=/tmp/ks-pre-tailoring.log",
        "%pre --log=/tmp/ks-pre-tailoring.log",
    )
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok
    assert any("missing: %pre tailoring fetcher block" in f for f in report.failures)
