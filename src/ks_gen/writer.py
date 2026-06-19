from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import render_exceptions_md
from ks_gen.registry import load_rules
from ks_gen.skeleton import PostBlock, render_skeleton
from ks_gen.tailoring import build_tailoring_xml
from ks_gen.topo import topo_sort


@dataclass(frozen=True)
class Bundle:
    """Generated artifacts for one host.

    Fields split into a shared core (always populated) and a distro-specific
    payload (exactly one set populated per `distro`). `__post_init__` enforces
    the invariant so callers downstream of construction can rely on it.
    """

    distro: Literal["alma9", "ubuntu2404"]
    tailoring_xml: str
    host_yaml: str
    exceptions_md: str
    ks_cfg: str | None = None
    user_data: str | None = None
    meta_data: str | None = None

    def __post_init__(self) -> None:
        if self.distro == "alma9":
            if self.ks_cfg is None:
                raise ValueError("alma9 bundle requires ks_cfg")
            if self.user_data is not None or self.meta_data is not None:
                raise ValueError("alma9 bundle must not set user_data/meta_data")
        elif self.distro == "ubuntu2404":
            if self.user_data is None:
                raise ValueError("ubuntu2404 bundle requires user_data")
            if self.meta_data is None:
                raise ValueError("ubuntu2404 bundle requires meta_data")
            if self.ks_cfg is not None:
                raise ValueError("ubuntu2404 bundle must not set ks_cfg")


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
    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    return build_tailoring_xml(tailoring_ops, profile_id=profile_id)


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

    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    tailoring_xml = build_tailoring_xml(tailoring_ops, profile_id=profile_id)
    ks_cfg = render_skeleton(cfg, post_blocks=list(post_blocks), rule_packages=rule_packages)
    host_yaml = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    exceptions_md = render_exceptions_md(cfg, applicable)
    return Bundle(
        distro="alma9",
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )


def write_bundle(bundle: Bundle, out_dir: Path) -> None:
    assert bundle.ks_cfg is not None, "write_bundle only supports alma9 bundles (ks_cfg required)"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ks.cfg").write_text(bundle.ks_cfg, encoding="utf-8", newline="\n")
    (out_dir / "tailoring.xml").write_text(bundle.tailoring_xml, encoding="utf-8", newline="\n")
    (out_dir / "host.yaml").write_text(bundle.host_yaml, encoding="utf-8", newline="\n")
    (out_dir / "exceptions.md").write_text(bundle.exceptions_md, encoding="utf-8", newline="\n")
