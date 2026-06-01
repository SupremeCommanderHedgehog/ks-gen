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
    return Environment(
        loader=FileSystemLoader(str(templates_path)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_skeleton(cfg: HostConfig, post_blocks: list[PostBlock | str]) -> str:
    env = _env()
    template = env.get_template("ks.cfg.j2")
    return template.render(
        cfg=cfg,
        post_blocks=post_blocks,
        version=__version__,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
