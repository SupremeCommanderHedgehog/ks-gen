from ks_gen.registry import load_rules
from ks_gen.rules.alma8.rngd_entropy import RULE as ALMA8_RULE
from ks_gen.rules.alma9.rngd_entropy import RULE as ALMA9_RULE
from ks_gen.writer import build_bundle


def test_alma8_installs_and_enables_rngd(minimal_cfg):
    assert ALMA8_RULE.applies(minimal_cfg)
    assert ALMA8_RULE.emit_packages(minimal_cfg) == ["rng-tools"]
    assert "systemctl enable rngd.service" in ALMA8_RULE.emit_post(minimal_cfg)


def test_alma8_completes_the_stig_so_it_tailors_nothing(minimal_cfg):
    """rngd is what the skipped STIG rules ask for: no disable, no exception."""
    assert ALMA8_RULE.emit_tailoring(minimal_cfg) == []
    assert ALMA8_RULE.exception_entry(minimal_cfg) is None


def test_alma9_and_alma10_never_apply(minimal_cfg):
    assert not ALMA9_RULE.applies(minimal_cfg)
    alma10 = {r.id: r for r in load_rules("alma10")}["rngd_entropy"]
    assert alma10 is ALMA9_RULE


def test_alma8_kickstart_carries_rng_tools_and_enables_rngd(minimal_cfg):
    cfg = minimal_cfg.model_validate(
        {**minimal_cfg.model_dump(exclude={"meta", "install"}), "distro": "alma8"}
    )
    ks = build_bundle(cfg).ks_cfg
    packages = ks.split("%packages", 1)[1].split("%end", 1)[0].split()
    assert "rng-tools" in packages
    assert "systemctl enable rngd.service" in ks


def test_alma8_excluding_rng_tools_opts_out(minimal_cfg):
    """Enabling a unit whose package was excluded would abort %post."""
    packages = minimal_cfg.packages.model_copy(
        update={"excluded": [*minimal_cfg.packages.excluded, "rng-tools"]}
    )
    cfg = minimal_cfg.model_copy(update={"packages": packages})
    assert not ALMA8_RULE.applies(cfg)
