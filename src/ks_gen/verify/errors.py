from __future__ import annotations

from ks_gen.loader import ExitCode


class VerifyError(Exception):
    """Base class for ks-gen verify failures. Subclasses set exit_code."""

    exit_code: ExitCode = ExitCode.TRANSPORT_FAIL


class SshConnectError(VerifyError):
    """ssh exit 255 — host unreachable, key rejected, kex failure."""


class SudoPromptError(VerifyError):
    """sudo -n returned 'a password is required' or non-zero before oscap ran."""


class OscapInvocationError(VerifyError):
    """oscap exit not in {0, 2}. Tailoring missing, profile typo, ssg unpopulated, OOM."""


class ArfMissingError(VerifyError):
    """oscap claimed success but the ARF file isn't on the host or pulled 0 bytes."""


class ArfParseError(VerifyError):
    """ARF is XML but doesn't look like SCAP ARF — wrong namespace, no TestResult."""


class ToolMissingError(VerifyError):
    """system ssh or scp not on PATH."""

    exit_code: ExitCode = ExitCode.TOOL_MISSING
