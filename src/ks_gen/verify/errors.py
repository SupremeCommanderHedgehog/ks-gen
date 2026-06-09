from __future__ import annotations

from ks_gen.loader import ExitCode


class VerifyError(Exception):
    """Base class for ks-gen verify failures. Subclasses set exit_code."""

    exit_code: ExitCode = ExitCode.TRANSPORT_FAIL


class SshConnectError(VerifyError):
    """ssh/scp transport failure.

    Covers ssh exit 255 (host unreachable, key rejected, kex failure), scp
    transfer errors (any nonzero scp exit), and transport-layer timeouts.
    """


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


class SuggestApplyError(VerifyError):
    """Apply-side failure: malformed host.yaml, schema-rejecting candidate,
    or write/backup IO error. Exit code is CONFIG_INVALID (2) because the
    operator's config file content (not CLI invocation) is what needs fixing."""

    exit_code: ExitCode = ExitCode.CONFIG_INVALID


class TailoringParseError(VerifyError):
    """Tailoring XML failed to parse — malformed XML or missing <Profile>.

    Exit code is VERIFY_FAIL (6); the parse failure is treated as a verify
    failure rather than a transport failure because the bytes arrived but
    aren't usable. Message text names which side failed (deployed vs
    re-rendered) so the operator knows whether to suspect host tampering
    or a ks-gen renderer regression."""

    exit_code: ExitCode = ExitCode.VERIFY_FAIL
