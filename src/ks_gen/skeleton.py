from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ks_gen import __version__
from ks_gen.config import HostConfig


@dataclass(frozen=True)
class PostBlock:
    rule_id: str
    body: str


def _env() -> Environment:
    templates_path = files("ks_gen") / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_path)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    # Import locally to avoid module-load-time circular import risk.
    from ks_gen.disk_layout import (
        effective_fsoptions,
        effective_size_mb,
        size_to_mb,
    )
    from ks_gen.disk_luks import (
        kickstart_passphrase_quoted,
        resolve_passphrase,
    )

    env.globals["effective_size_mb"] = effective_size_mb
    env.globals["effective_fsoptions"] = effective_fsoptions
    env.globals["size_to_mb"] = size_to_mb
    env.globals["resolve_passphrase"] = resolve_passphrase
    env.globals["kickstart_passphrase_quoted"] = kickstart_passphrase_quoted
    return env


def render_skeleton(
    cfg: HostConfig,
    post_blocks: list[PostBlock | str],
    rule_packages: list[str] | None = None,
) -> str:
    env = _env()
    template = env.get_template("ks.cfg.j2")
    return template.render(
        cfg=cfg,
        post_blocks=post_blocks,
        rule_packages=rule_packages or [],
        version=__version__,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def render_user_data(cfg: HostConfig) -> str:
    """Render the autoinstall + cloud-init user-data for an ubuntu2404 host.

    Phase 2: emits a minimal placeholder (identity + empty late-commands).
    Phase 3 will populate late-commands from the ubuntu2404 rule registry.
    """
    env = _env()
    template = env.get_template("user-data.j2")
    return template.render(cfg=cfg)


def render_meta_data(cfg: HostConfig) -> str:
    """Render the cloud-init NoCloud meta-data for an ubuntu2404 host."""
    env = _env()
    template = env.get_template("meta-data.j2")
    return template.render(cfg=cfg)
