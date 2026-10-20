"""Operator-declared exception ids are checked against the datastream (#69)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ks_gen.config import ExceptionDecl, HostConfig
from ks_gen.ssg_ids import RULE_PREFIX, _lists, check_exception_ids

_REPO = Path(__file__).resolve().parent.parent
_DISTROS = ["alma8", "alma9", "alma10"]
_SELECTED = f"{RULE_PREFIX}encrypt_partitions"
# In alma9's datastream but selected by neither the stig pin nor its floor.
_UNSELECTED = f"{RULE_PREFIX}account_emergency_expire_date"


def _cfg(minimal_cfg: HostConfig, *ids: str, distro: str = "alma9", **meta) -> HostConfig:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    data = {
        **base,
        "distro": distro,
        "exceptions": [{"id": "ex", "reason": "r", "stig_rules_disabled": list(ids)}],
    }
    if meta:
        data["meta"] = meta
    return HostConfig.model_validate(data)


@pytest.mark.parametrize("distro", _DISTROS)
def test_every_distro_has_lists(distro):
    lists = _lists(distro)
    assert lists is not None, f"no rule-id lists for {distro}"
    known, selected = lists
    assert selected <= known
    assert _SELECTED in selected


def test_selected_full_id_passes(minimal_cfg):
    report = check_exception_ids(_cfg(minimal_cfg, _SELECTED))
    assert report.errors == [] and report.warnings == []


def test_bare_id_is_an_error_with_a_hint(minimal_cfg):
    report = check_exception_ids(_cfg(minimal_cfg, "encrypt_partitions"))
    assert len(report.errors) == 1
    assert "deselect nothing" in report.errors[0]
    assert f"did you mean {_SELECTED!r}" in report.errors[0]


def test_unknown_id_is_an_error_without_a_hint(minimal_cfg):
    report = check_exception_ids(_cfg(minimal_cfg, f"{RULE_PREFIX}no_such_rule"))
    assert len(report.errors) == 1
    assert "did you mean" not in report.errors[0]


def test_unselected_id_warns_under_stig_only(minimal_cfg):
    report = check_exception_ids(_cfg(minimal_cfg, _UNSELECTED))
    assert report.errors == []
    assert len(report.warnings) == 1 and "no effect" in report.warnings[0]
    other = check_exception_ids(_cfg(minimal_cfg, _UNSELECTED, profile="cis"))
    assert other.errors == [] and other.warnings == []


def test_ids_are_checked_per_distro(minimal_cfg):
    """An id from another distro's datastream is still unknown here."""
    alma9_only = sorted(_lists("alma9")[0] - _lists("alma10")[0])[0]
    assert check_exception_ids(_cfg(minimal_cfg, alma9_only)).errors == []
    assert check_exception_ids(_cfg(minimal_cfg, alma9_only, distro="alma10")).errors


def test_missing_lists_fail_closed(minimal_cfg, monkeypatch):
    monkeypatch.setattr("ks_gen.ssg_ids._lists", lambda distro: None)
    report = check_exception_ids(_cfg(minimal_cfg, _SELECTED))
    assert report.errors and "cannot be checked" in report.errors[0]


def test_no_exceptions_needs_no_lists(minimal_cfg, monkeypatch):
    monkeypatch.setattr("ks_gen.ssg_ids._lists", lambda distro: None)
    cfg = minimal_cfg.model_copy(update={"exceptions": []})
    assert check_exception_ids(cfg).errors == []


@pytest.mark.parametrize(
    "rid",
    ["content_rule_encrypt_partitions", f"{RULE_PREFIX}encrypt_partition"],
)
def test_partial_prefix_and_typo_get_a_hint(minimal_cfg, rid):
    (error,) = check_exception_ids(_cfg(minimal_cfg, rid)).errors
    assert f"did you mean {_SELECTED!r}" in error


def test_wheel_ships_the_lists_where_ssg_ids_reads_them():
    """Every test runs from a checkout, where the docs/ fallback hides a broken
    wheel mapping. Pin the force-include to the path _data_dir() reads."""
    import tomllib

    from ks_gen.ssg_ids import PACKAGED_DIR

    pyproject = tomllib.loads((_REPO / "pyproject.toml").read_text(encoding="utf-8"))
    force = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert force.get("docs/audit-story") == f"ks_gen/{PACKAGED_DIR}"


def _repo_configs():
    globs = (
        "tests/golden/*.yaml",
        "tests/install-regression/fixtures/*.tmpl",
        "examples/**/*.yaml",
    )
    for pattern in globs:
        yield from sorted(_REPO.glob(pattern))


def test_repo_configs_only_declare_known_exception_ids():
    """Configs in the repo never carry a dud id. None declares exceptions today;
    the guard is for the first one that does."""
    for path in _repo_configs():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            continue
        distro = data.get("distro", "alma9")
        lists = _lists(distro)
        assert lists is not None, f"{path.relative_to(_REPO)}: no rule-id lists for {distro!r}"
        known = lists[0]
        for ex in data.get("exceptions") or []:
            decl = ExceptionDecl.model_validate(ex)
            unknown = [rid for rid in decl.stig_rules_disabled if rid not in known]
            assert not unknown, f"{path.relative_to(_REPO)}: {decl.id}: {unknown}"
