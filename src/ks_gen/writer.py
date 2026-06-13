from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import render_exceptions_md
from ks_gen.registry import load_rules
from ks_gen.skeleton import PostBlock, render_skeleton
from ks_gen.tailoring import build_tailoring_xml
from ks_gen.topo import topo_sort


@dataclass(frozen=True)
class Bundle:
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
    rules = topo_sort(load_rules())
    applicable = [r for r in rules if r.applies(cfg)]
    tailoring_ops = []
    for r in applicable:
        tailoring_ops.extend(r.emit_tailoring(cfg))
    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    return build_tailoring_xml(tailoring_ops, profile_id=profile_id)


def build_bundle(cfg: HostConfig) -> Bundle:
    rules = topo_sort(load_rules())
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

    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    tailoring_xml = build_tailoring_xml(tailoring_ops, profile_id=profile_id)
    ks_cfg = render_skeleton(cfg, post_blocks=list(post_blocks), rule_packages=rule_packages)
    host_yaml = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    exceptions_md = render_exceptions_md(cfg, applicable)
    return Bundle(
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )


def write_bundle(bundle: Bundle, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ks.cfg").write_text(bundle.ks_cfg, encoding="utf-8", newline="\n")
    (out_dir / "tailoring.xml").write_text(bundle.tailoring_xml, encoding="utf-8", newline="\n")
    (out_dir / "host.yaml").write_text(bundle.host_yaml, encoding="utf-8", newline="\n")
    (out_dir / "exceptions.md").write_text(bundle.exceptions_md, encoding="utf-8", newline="\n")
