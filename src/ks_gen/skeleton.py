from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from shlex import quote as _shlex_quote

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

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
        # Templates render kickstart/shell/cloud-init text, never HTML — so
        # HTML autoescaping stays off for those. select_autoescape still
        # engages for any future .html/.xml template rather than hardcoding
        # autoescape=False (shell injection is handled by shlex quoting).
        autoescape=select_autoescape(enabled_extensions=("html", "xml"), default=False),
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


def render_user_data(
    cfg: HostConfig,
    post_blocks: list[PostBlock],
    rule_packages: list[str] | None = None,
) -> str:
    """Render the autoinstall + cloud-init user-data for an ubuntu2404 host.

    Emits a ``#cloud-config`` document with ``autoinstall.version: 1``, an
    ``identity`` block from ``cfg.system.hostname`` and ``cfg.user.admin.name``,
    a cloud-init ``users:`` block from ``cfg.user.admin``, and a ``late-commands:``
    list with one entry per ``PostBlock`` (wrapped as
    ``curtin in-target --target=/target -- bash -c <shlex-quoted body>`` inside a
    YAML literal block).

    If ``rule_packages`` is non-empty, also emits an ``autoinstall.packages:``
    list. This carries rule-declared apt deps (e.g. ``ufw`` for
    ``ssh_keep_open``) into subiquity's install-time package set — without it,
    late-commands targeting those binaries would fail with ``command not found``
    on a fresh install.
    """
    env = _env()
    template = env.get_template("user-data.j2")
    return template.render(
        cfg=cfg,
        late_commands_block=_format_late_commands(post_blocks),
        rule_packages=rule_packages or [],
    )


def _format_late_commands(post_blocks: list[PostBlock]) -> str:
    """Format a list of PostBlocks as the YAML suffix for the late-commands key.

    Returns either ``" []"`` (so the template emits ``late-commands: []`` on
    one line) or ``"\\n  - |\\n    <entry>\\n  - |\\n    ..."`` (so each entry
    becomes a YAML list item under late-commands at the correct indentation).
    Each bash body is shell-quoted with shlex.quote so embedded single quotes
    survive bash re-parse; the per-entry ``# rule:<id>`` comment lives inside
    the quoted body so it stays attached to its bash payload through the YAML
    parser.
    """
    if not post_blocks:
        return " []"
    lines: list[str] = []
    for block in post_blocks:
        body = f"# rule:{block.rule_id}\n{block.body}"
        bash_cmd = f"curtin in-target --target=/target -- bash -c {_shlex_quote(body)}"
        # YAML literal block requires every body line to share at least the
        # first line's indentation. The template renders entries at column 2
        # (sibling of `version:`), so the literal block content lives at
        # column 4.
        indented_body = "\n    ".join(bash_cmd.splitlines())
        lines.append(f"  - |\n    {indented_body}")
    return "\n" + "\n".join(lines)


def render_meta_data(cfg: HostConfig) -> str:
    """Render the cloud-init NoCloud meta-data for an ubuntu2404 host."""
    env = _env()
    template = env.get_template("meta-data.j2")
    return template.render(cfg=cfg)
