from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ks_gen.config import Distro, HostConfig
from ks_gen.exceptions_report import render_exceptions_md
from ks_gen.registry import load_rules
from ks_gen.rules._types import TailoringOp
from ks_gen.skeleton import PostBlock, render_skeleton
from ks_gen.tailoring import base_profile_id, build_tailoring_xml
from ks_gen.topo import topo_sort


def _exception_tailoring_ops(cfg: HostConfig) -> list[TailoringOp]:
    """Deselect every STIG rule named in an operator-declared exception.

    ``cfg.exceptions`` used to feed only exceptions.md (documentation) and the
    verify expected-failure set; the rules were never actually deselected in
    tailoring.xml, so the oscap remediation still enforced them. These ops are
    appended AFTER each rule's own emit_tailoring, so an explicit exception
    wins when a rule would otherwise select the same id.
    """
    ops: list[TailoringOp] = []
    seen: set[str] = set()
    for ex in cfg.exceptions:
        for rid in ex.stig_rules_disabled:
            if rid not in seen:
                seen.add(rid)
                ops.append(TailoringOp(rule_id=rid, action="disable"))
    return ops


def dump_host_yaml(cfg: HostConfig) -> str:
    """Serialize `cfg` as a host.yaml, minus derived and deprecated fields.

    `overrides.fips_mode` is derived from crypto.policy, so writing it
    back out bakes in a value that goes stale the next time the derivation
    changes — which is exactly what broke `verify` on older bundles (#84).
    `overrides.ssh_keep_open.ensure_ufw_port` is accepted only so bundles from
    before the Ubuntu removal still load (#103); writing it out would keep it
    alive forever.
    """
    return yaml.safe_dump(
        cfg.model_dump(
            mode="json",
            exclude={"overrides": {"fips_mode": True, "ssh_keep_open": {"ensure_ufw_port"}}},
        ),
        sort_keys=False,
        default_flow_style=False,
    )


@dataclass(frozen=True)
class Bundle:
    """Generated artifacts for one host."""

    distro: Distro
    ks_cfg: str
    tailoring_xml: str
    host_yaml: str
    exceptions_md: str


def render_tailoring(cfg: HostConfig) -> str:
    """Render the tailoring.xml for `cfg` without rendering ks.cfg / exceptions.md.

    Used by `build_bundle` (the full bundle path) and by `verify` (for
    tailoring drift detection). The embedded `<xccdf:version time="...">`
    timestamp comes from `build_tailoring_xml`'s `datetime.now(UTC)` call —
    callers comparing two renders must strip it first.
    """
    rules = topo_sort(load_rules(cfg.distro))
    applicable = [r for r in rules if r.applies(cfg)]
    tailoring_ops = []
    for r in applicable:
        tailoring_ops.extend(r.emit_tailoring(cfg))
    tailoring_ops.extend(_exception_tailoring_ops(cfg))
    profile_id = base_profile_id(cfg.meta.profile)
    return build_tailoring_xml(
        tailoring_ops, profile_id=profile_id, scap_content=cfg.meta.scap_content
    )


def build_bundle(cfg: HostConfig) -> Bundle:
    rules = topo_sort(load_rules(cfg.distro))
    applicable = [r for r in rules if r.applies(cfg)]

    post_blocks: list[PostBlock] = []
    tailoring_ops = []
    rule_packages: list[str] = []
    already = set(cfg.packages.effective_required)
    for r in applicable:
        body = r.emit_post(cfg).rstrip()
        if body:
            post_blocks.append(PostBlock(rule_id=r.id, body=body))
        tailoring_ops.extend(r.emit_tailoring(cfg))
        for pkg in r.emit_packages(cfg):
            if pkg not in already:
                rule_packages.append(pkg)
                already.add(pkg)

    tailoring_ops.extend(_exception_tailoring_ops(cfg))
    profile_id = base_profile_id(cfg.meta.profile)
    tailoring_xml = build_tailoring_xml(
        tailoring_ops, profile_id=profile_id, scap_content=cfg.meta.scap_content
    )
    ks_cfg = render_skeleton(cfg, post_blocks=list(post_blocks), rule_packages=rule_packages)
    host_yaml = dump_host_yaml(cfg)
    exceptions_md = render_exceptions_md(cfg, applicable)
    return Bundle(
        distro=cfg.distro,
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )


def write_bundle(bundle: Bundle, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tailoring.xml").write_text(bundle.tailoring_xml, encoding="utf-8", newline="\n")
    (out_dir / "host.yaml").write_text(bundle.host_yaml, encoding="utf-8", newline="\n")
    (out_dir / "exceptions.md").write_text(bundle.exceptions_md, encoding="utf-8", newline="\n")
    (out_dir / "ks.cfg").write_text(bundle.ks_cfg, encoding="utf-8", newline="\n")
