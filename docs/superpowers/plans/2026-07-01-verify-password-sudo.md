# verify password-sudo support (#16) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `ks-gen verify` authenticate `sudo` with a password (via `--ask-sudo-pass`, sourced from `KSGEN_SUDO_PASSWORD` or a `getpass` prompt) while keeping passwordless `sudo -n` the zero-config default, and make all host-file retrieval work under strict `/root` perms + STIG root umask 077.

**Architecture:** A frozen `SudoAuth` value object (password `None` ⇒ `sudo -n`; a string ⇒ `sudo -S -p ''`) plus a `sudo_prefix` helper is threaded through the verify SSH layer. `ssh_exec` gains a `stdin_input` param so the password reaches remote `sudo -S` over the already key-authenticated channel (never argv, never a file). All three file pulls (current ARF, install ARF, `/root/tailoring.xml`) move from `scp` to `sudo cat`, and `scp` is dropped from the toolchain.

**Tech Stack:** Python 3.14, typer CLI, pytest, `unittest.mock.patch`, `subprocess`. Design doc: `docs/superpowers/specs/2026-07-01-verify-password-sudo-design.md`.

**Before you start:** Create a feature branch (`git switch -c feat/verify-password-sudo`). Every commit MUST be signed — this machine requires it:

```bash
git -c user.email="github.v5f9w@bitbucket.onl" \
    -c user.signingkey=BE707B220C995478 \
    commit -S -m "<message>"
```

Use that exact `git ... commit -S` form for every commit step below (the steps abbreviate it as `git commit -S -m "..."`). Do **not** pass `--no-gpg-sign`.

---

## File Structure

- **Create** `src/ks_gen/verify/auth.py` — `SudoAuth`, `sudo_prefix`, `resolve_sudo_auth`. Depends only on `ks_gen.loader`. One responsibility: model + resolve the sudo credential.
- **Modify** `src/ks_gen/verify/ssh.py` — add `stdin_input` to `ssh_exec`; add `sudo_pull`; remove `scp_pull`; drop `scp` from `check_tools`.
- **Modify** `src/ks_gen/verify/remote.py` — thread `SudoAuth`; add a private `_sudo_ssh` wrapper; route pulls through `sudo_pull`; branch `probe_sudo`'s error message.
- **Modify** `src/ks_gen/verify/__init__.py` — `run_verify` gains `sudo_auth`; docstring corrections.
- **Modify** `src/ks_gen/cli.py` — `--ask-sudo-pass` flag; resolve + thread `SudoAuth`.
- **Modify** tests: `tests/test_verify_ssh.py`, `tests/test_verify_remote.py`, `tests/test_verify_run.py`, `tests/test_cli/test_verify.py`; **create** `tests/test_verify_auth.py`.

---

## Task 1: `SudoAuth` value object + `sudo_prefix`

**Files:**
- Create: `src/ks_gen/verify/auth.py`
- Test: `tests/test_verify_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verify_auth.py
from __future__ import annotations

from ks_gen.verify.auth import SudoAuth, sudo_prefix


def test_sudo_auth_passwordless_by_default() -> None:
    auth = SudoAuth()
    assert auth.password is None
    assert auth.is_password is False


def test_sudo_auth_with_password_is_password() -> None:
    auth = SudoAuth(password="hunter2")
    assert auth.is_password is True


def test_sudo_auth_repr_hides_password() -> None:
    assert "hunter2" not in repr(SudoAuth(password="hunter2"))


def test_sudo_prefix_passwordless() -> None:
    assert sudo_prefix(SudoAuth()) == "sudo -n"


def test_sudo_prefix_password() -> None:
    assert sudo_prefix(SudoAuth(password="x")) == "sudo -S -p ''"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ks_gen.verify.auth'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ks_gen/verify/auth.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SudoAuth:
    """Sudo credential for verify's remote commands.

    `password is None` selects passwordless mode (`sudo -n`); a string selects
    password mode (`sudo -S`, fed over stdin). `repr=False` on the field keeps
    the secret out of tracebacks and log lines.
    """

    password: str | None = field(default=None, repr=False)

    @property
    def is_password(self) -> bool:
        return self.password is not None


def sudo_prefix(auth: SudoAuth) -> str:
    """Return the sudo invocation prefix for `auth`'s mode."""
    return "sudo -S -p ''" if auth.is_password else "sudo -n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_auth.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/verify/auth.py tests/test_verify_auth.py
git commit -S -m "feat(verify): add SudoAuth value object + sudo_prefix (#16)"
```

---

## Task 2: `resolve_sudo_auth` (env var → getpass → error)

**Files:**
- Modify: `src/ks_gen/verify/auth.py`
- Test: `tests/test_verify_auth.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_verify_auth.py`)

```python
import pytest

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.auth import resolve_sudo_auth


def test_resolve_not_ask_returns_passwordless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "ignored")
    auth = resolve_sudo_auth(False, user="u", host="h")
    assert auth.password is None


def test_resolve_ask_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "fromenv")
    auth = resolve_sudo_auth(True, user="u", host="h")
    assert auth.password == "fromenv"


def test_resolve_ask_prompts_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KSGEN_SUDO_PASSWORD", raising=False)
    monkeypatch.setattr("ks_gen.verify.auth.getpass.getpass", lambda prompt: "typed")
    auth = resolve_sudo_auth(True, user="u", host="h")
    assert auth.password == "typed"


def test_resolve_ask_empty_password_raises_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "")
    with pytest.raises(ConfigError) as ei:
        resolve_sudo_auth(True, user="u", host="h")
    assert ei.value.exit_code == ExitCode.USAGE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_auth.py -k resolve -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_sudo_auth'`

- [ ] **Step 3: Write minimal implementation** (add to `src/ks_gen/verify/auth.py`)

Add these imports at the top (below `from __future__`):

```python
import getpass
import os

from ks_gen.loader import ConfigError, ExitCode
```

Add the constant near the top and the function at the end:

```python
_ENV_VAR = "KSGEN_SUDO_PASSWORD"


def resolve_sudo_auth(ask: bool, *, user: str, host: str) -> SudoAuth:
    """Resolve the sudo credential for a verify run.

    `ask=False` (the default CLI path) returns a passwordless `SudoAuth`.
    `ask=True` reads `KSGEN_SUDO_PASSWORD`, falling back to a no-echo prompt.
    An empty resolved password is a usage error, never a silent fallback to
    passwordless mode.
    """
    if not ask:
        return SudoAuth()
    password = os.environ.get(_ENV_VAR)
    if password is None:
        password = getpass.getpass(f"sudo password for {user}@{host}: ")
    if not password:
        raise ConfigError(
            f"--ask-sudo-pass given but no password supplied (set {_ENV_VAR} "
            "or enter one at the prompt)",
            ExitCode.USAGE,
        )
    return SudoAuth(password=password)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_auth.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/verify/auth.py tests/test_verify_auth.py
git commit -S -m "feat(verify): resolve sudo password from env var or getpass (#16)"
```

---

## Task 3: `ssh_exec` accepts `stdin_input`

**Files:**
- Modify: `src/ks_gen/verify/ssh.py:31-55`
- Test: `tests/test_verify_ssh.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_verify_ssh.py`)

```python
def test_ssh_exec_forwards_stdin_input() -> None:
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(0)) as run:
        ssh_exec("host", "user", "sudo -S -p '' true", stdin_input="pw\n")
    assert run.call_args.kwargs["input"] == "pw\n"


def test_ssh_exec_stdin_input_defaults_to_none() -> None:
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(0)) as run:
        ssh_exec("host", "user", "ls /")
    assert run.call_args.kwargs["input"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_ssh.py -k stdin_input -v`
Expected: FAIL — `TypeError: ssh_exec() got an unexpected keyword argument 'stdin_input'`

- [ ] **Step 3: Write minimal implementation**

In `src/ks_gen/verify/ssh.py`, change the `ssh_exec` signature and the `subprocess.run` call:

```python
def ssh_exec(
    host: str,
    user: str,
    remote_cmd: str,
    *,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
    stdin_input: str | None = None,
) -> SshResult:
    cmd: list[str] = ["ssh", "-o", "BatchMode=yes"]
    if extra_opts:
        cmd.extend(extra_opts)
    cmd.append(f"{user}@{host}")
    cmd.append(remote_cmd)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            input=stdin_input,
        )
    except subprocess.TimeoutExpired as e:
        raise SshConnectError(f"ssh timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ToolMissingError("ssh not on PATH") from e

    if proc.returncode == 255:
        raise SshConnectError(f"ssh exit 255: {_first_stderr_line(proc.stderr)}")

    return SshResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_ssh.py -v`
Expected: PASS (all existing ssh tests + 2 new)

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/verify/ssh.py tests/test_verify_ssh.py
git commit -S -m "feat(verify): thread stdin_input through ssh_exec (#16)"
```

---

## Task 4: `sudo_pull` (sudo cat retrieval)

**Files:**
- Modify: `src/ks_gen/verify/ssh.py` (add import `shlex`; add `sudo_pull`)
- Test: `tests/test_verify_ssh.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_verify_ssh.py`)

```python
from ks_gen.verify.auth import SudoAuth
from ks_gen.verify.ssh import sudo_pull


def test_sudo_pull_passwordless_writes_stdout(tmp_path: Path) -> None:
    local = tmp_path / "out.xml"
    with patch(
        "ks_gen.verify.ssh.subprocess.run",
        return_value=_completed(0, "<TestResult/>"),
    ) as run:
        sudo_pull("host", "user", "/root/f.xml", local, auth=SudoAuth(), extra_opts=["-q"])
    assert local.read_text(encoding="utf-8") == "<TestResult/>"
    cmd = run.call_args.args[0]
    assert cmd[-1] == "sudo -n cat /root/f.xml"
    assert run.call_args.kwargs["input"] is None
    assert "-q" in cmd


def test_sudo_pull_password_sends_stdin_and_uses_dash_s(tmp_path: Path) -> None:
    local = tmp_path / "out.xml"
    with patch(
        "ks_gen.verify.ssh.subprocess.run",
        return_value=_completed(0, "<x/>"),
    ) as run:
        sudo_pull("host", "user", "/root/f.xml", local, auth=SudoAuth(password="pw"))
    cmd = run.call_args.args[0]
    assert cmd[-1] == "sudo -S -p '' cat /root/f.xml"
    assert run.call_args.kwargs["input"] == "pw\n"


def test_sudo_pull_nonzero_exit_raises(tmp_path: Path) -> None:
    with (
        patch(
            "ks_gen.verify.ssh.subprocess.run",
            return_value=_completed(1, "", "cat: /root/f.xml: No such file"),
        ),
        pytest.raises(SshConnectError, match="sudo cat"),
    ):
        sudo_pull("host", "user", "/root/f.xml", tmp_path / "x", auth=SudoAuth())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_ssh.py -k sudo_pull -v`
Expected: FAIL — `ImportError: cannot import name 'sudo_pull'`

- [ ] **Step 3: Write minimal implementation**

In `src/ks_gen/verify/ssh.py`, add `import shlex` to the top imports and add the imports + function:

```python
from ks_gen.verify.auth import SudoAuth, sudo_prefix
```

```python
def sudo_pull(
    host: str,
    user: str,
    remote_path: str,
    local_path: Path,
    *,
    auth: SudoAuth,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
) -> None:
    """Retrieve a root-owned remote file via `sudo cat` over the ssh channel.

    Replaces scp: works when the login user cannot traverse /root and when
    STIG root umask 077 makes even /tmp artifacts non-world-readable. Writes
    the file's text to `local_path`.
    """
    stdin_input = f"{auth.password}\n" if auth.is_password else None
    result = ssh_exec(
        host,
        user,
        f"{sudo_prefix(auth)} cat {shlex.quote(remote_path)}",
        extra_opts=extra_opts,
        timeout=timeout,
        stdin_input=stdin_input,
    )
    if result.exit_code != 0:
        raise SshConnectError(
            f"sudo cat {remote_path} exit {result.exit_code}: "
            f"{_first_stderr_line(result.stderr)}"
        )
    local_path.write_text(result.stdout, encoding="utf-8")
```

Note: `shlex.quote("/root/f.xml")` returns `/root/f.xml` unchanged (no metacharacters), so the test assertions on the exact command string hold.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_ssh.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/verify/ssh.py tests/test_verify_ssh.py
git commit -S -m "feat(verify): add sudo_pull for root-owned file retrieval (#16)"
```

---

## Task 5: Thread `SudoAuth` through `remote.py`, switch to `sudo_pull`

**Files:**
- Modify: `src/ks_gen/verify/remote.py`
- Test: `tests/test_verify_remote.py`

This task rewrites `remote.py` to (a) take a `SudoAuth`, (b) build every privileged command through a `_sudo_ssh` wrapper, (c) pull files with `sudo_pull`, and (d) branch `probe_sudo`'s message. The existing tests patch `remote.scp_pull` and pass `ssh_extra_opts=[]` — they must be updated to patch `remote.sudo_pull` and pass `sudo_auth=SudoAuth()`.

- [ ] **Step 1: Update the tests to the new interface**

Replace the top imports of `tests/test_verify_remote.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ks_gen.verify.auth import SudoAuth
from ks_gen.verify.errors import (
    ArfMissingError,
    OscapInvocationError,
    SudoPromptError,
)
from ks_gen.verify.remote import CollectedArfs, collect_arfs, collect_deployed_tailoring, probe_sudo
from ks_gen.verify.ssh import SshResult
```

Replace the two `probe_sudo` tests:

```python
def test_probe_sudo_passwordless_passes_and_uses_sudo_n() -> None:
    with patch("ks_gen.verify.remote.ssh_exec", return_value=SshResult("", "", 0)) as ssh:
        probe_sudo("h", "u", sudo_auth=SudoAuth(), ssh_extra_opts=[])
    assert ssh.call_args.args[2] == "sudo -n true"
    assert ssh.call_args.kwargs["stdin_input"] is None


def test_probe_sudo_password_uses_sudo_s_and_sends_stdin() -> None:
    with patch("ks_gen.verify.remote.ssh_exec", return_value=SshResult("", "", 0)) as ssh:
        probe_sudo("h", "u", sudo_auth=SudoAuth(password="pw"), ssh_extra_opts=[])
    assert ssh.call_args.args[2] == "sudo -S -p '' true"
    assert ssh.call_args.kwargs["stdin_input"] == "pw\n"


def test_probe_sudo_passwordless_failure_says_passwordless() -> None:
    with (
        patch("ks_gen.verify.remote.ssh_exec", return_value=SshResult("", "", 1)),
        pytest.raises(SudoPromptError, match="passwordless"),
    ):
        probe_sudo("h", "u", sudo_auth=SudoAuth(), ssh_extra_opts=[])


def test_probe_sudo_password_failure_says_wrong_password() -> None:
    with (
        patch("ks_gen.verify.remote.ssh_exec", return_value=SshResult("", "", 1)),
        pytest.raises(SudoPromptError, match="wrong password or user not in sudoers"),
    ):
        probe_sudo("h", "u", sudo_auth=SudoAuth(password="pw"), ssh_extra_opts=[])
```

In every `collect_arfs` / `collect_deployed_tailoring` test, make these mechanical edits:
1. Rename each `fake_scp` to `fake_pull` and change its signature to accept the new kwargs:
   `def fake_pull(host, user, remote, local, **kw): ...` (body unchanged — it still writes `local`).
2. Change each `patch("ks_gen.verify.remote.scp_pull", ...)` to `patch("ks_gen.verify.remote.sudo_pull", ...)`.
3. Add `sudo_auth=SudoAuth()` to every `collect_arfs(...)` and `collect_deployed_tailoring(...)` call.

The `sudo -n test -r ...`, `sudo -n rm ...`, and `oscap xccdf eval` command-string assertions in the existing `fake_ssh` bodies stay correct (the `_sudo_ssh` wrapper reproduces those exact strings in passwordless mode).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_verify_remote.py -v`
Expected: FAIL — `probe_sudo() got an unexpected keyword argument 'sudo_auth'` / `cannot import name 'sudo_pull'` references in patches.

- [ ] **Step 3: Rewrite `src/ks_gen/verify/remote.py`**

Update imports (drop `scp_pull`, add `sudo_pull` and auth helpers):

```python
from ks_gen.verify.auth import SudoAuth, sudo_prefix
from ks_gen.verify.ssh import ssh_exec, sudo_pull
```

Add a private wrapper after the module constants:

```python
def _sudo_ssh(
    host: str,
    user: str,
    cmd: str,
    *,
    auth: SudoAuth,
    ssh_extra_opts: list[str],
    timeout: float | None = None,
) -> "SshResult":
    """Run `cmd` under sudo, feeding the password on stdin in password mode."""
    stdin_input = f"{auth.password}\n" if auth.is_password else None
    return ssh_exec(
        host,
        user,
        f"{sudo_prefix(auth)} {cmd}",
        extra_opts=ssh_extra_opts,
        stdin_input=stdin_input,
        timeout=timeout,
    )
```

(Import `SshResult` for the annotation: add `SshResult` to the `from ks_gen.verify.ssh import ...` line, i.e. `from ks_gen.verify.ssh import SshResult, ssh_exec, sudo_pull`. Then the `"SshResult"` string annotation can be unquoted.)

Rewrite `probe_sudo`:

```python
def probe_sudo(host: str, user: str, *, sudo_auth: SudoAuth, ssh_extra_opts: list[str]) -> None:
    result = _sudo_ssh(host, user, "true", auth=sudo_auth, ssh_extra_opts=ssh_extra_opts)
    if result.exit_code != 0:
        if sudo_auth.is_password:
            raise SudoPromptError(
                f"sudo failed (exit {result.exit_code}) on {host} as {user}: "
                f"wrong password or user not in sudoers"
            )
        raise SudoPromptError(
            f"sudo -n true failed (exit {result.exit_code}) on {host} as {user}: "
            f"passwordless sudo is required"
        )
```

Change `_oscap_command` to drop the hardcoded `sudo -n ` prefix (the wrapper adds it):

```python
def _oscap_command(cfg: HostConfig) -> str:
    return (
        "oscap xccdf eval "
        f"--tailoring-file {REMOTE_TAILORING} "
        f"--profile xccdf_org.ssgproject.content_profile_{cfg.meta.profile} "
        "--fetch-remote-resources "
        f"--results-arf {REMOTE_CURRENT_ARF} "
        f"/usr/share/xml/scap/ssg/content/{cfg.meta.scap_content}"
    )
```

Rewrite `collect_arfs` — add `sudo_auth: SudoAuth = SudoAuth()` (keyword-only), route every privileged call through `_sudo_ssh`, and every file pull through `sudo_pull`:

```python
def collect_arfs(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool,
    ssh_extra_opts: list[str],
    timeout: int,
    sudo_auth: SudoAuth = SudoAuth(),
) -> CollectedArfs:
    probe_sudo(host, user, sudo_auth=sudo_auth, ssh_extra_opts=ssh_extra_opts)

    tailoring_check = _sudo_ssh(
        host, user, f"test -r {REMOTE_TAILORING}", auth=sudo_auth, ssh_extra_opts=ssh_extra_opts
    )
    if tailoring_check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    try:
        oscap_result = _sudo_ssh(
            host,
            user,
            _oscap_command(cfg),
            auth=sudo_auth,
            ssh_extra_opts=ssh_extra_opts,
            timeout=timeout,
        )
        if oscap_result.exit_code not in (0, 2):
            stderr_first = (oscap_result.stderr.splitlines() or [""])[0]
            raise OscapInvocationError(f"oscap exit {oscap_result.exit_code}: {stderr_first}")

        local_current = workdir / "current.arf.xml"
        sudo_pull(
            host,
            user,
            REMOTE_CURRENT_ARF,
            local_current,
            auth=sudo_auth,
            extra_opts=ssh_extra_opts,
        )
        if not local_current.exists() or local_current.stat().st_size == 0:
            raise ArfMissingError(f"pulled current ARF is empty or missing: {local_current}")
        current_text = local_current.read_text(encoding="utf-8")

        install_text: str | None = None
        if not no_drift:
            check = _sudo_ssh(
                host,
                user,
                f"test -r {REMOTE_INSTALL_ARF}",
                auth=sudo_auth,
                ssh_extra_opts=ssh_extra_opts,
            )
            if check.exit_code == 0:
                local_install = workdir / "install.arf.xml"
                sudo_pull(
                    host,
                    user,
                    REMOTE_INSTALL_ARF,
                    local_install,
                    auth=sudo_auth,
                    extra_opts=ssh_extra_opts,
                )
                if local_install.exists() and local_install.stat().st_size > 0:
                    install_text = local_install.read_text(encoding="utf-8")

        return CollectedArfs(current_text=current_text, install_text=install_text)
    finally:
        try:
            _sudo_ssh(
                host,
                user,
                f"rm -f {REMOTE_CURRENT_ARF}",
                auth=sudo_auth,
                ssh_extra_opts=ssh_extra_opts,
            )
        except Exception:
            # Best-effort cleanup; never mask the primary error.
            pass
```

Rewrite `collect_deployed_tailoring` the same way:

```python
def collect_deployed_tailoring(
    *,
    host: str,
    user: str,
    workdir: Path,
    ssh_extra_opts: list[str],
    sudo_auth: SudoAuth = SudoAuth(),
) -> str:
    """scp-free pull of `/root/tailoring.xml` for drift comparison.

    Sibling to `collect_arfs`. Does not share state with the ARF pull —
    `--check-tailoring` and `--no-drift` are independent axes.

    Returns the file's text contents.

    Raises:
        SudoPromptError: sudo unavailable (or wrong password).
        OscapInvocationError: `/root/tailoring.xml` not readable on host.
        ArfMissingError: pull succeeded but the file is 0 bytes.
        SshConnectError: ssh transport failure.
        ToolMissingError: ssh not on PATH.
    """
    probe_sudo(host, user, sudo_auth=sudo_auth, ssh_extra_opts=ssh_extra_opts)

    check = _sudo_ssh(
        host, user, f"test -r {REMOTE_TAILORING}", auth=sudo_auth, ssh_extra_opts=ssh_extra_opts
    )
    if check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    local = workdir / "deployed-tailoring.xml"
    sudo_pull(host, user, REMOTE_TAILORING, local, auth=sudo_auth, extra_opts=ssh_extra_opts)
    if not local.exists() or local.stat().st_size == 0:
        raise ArfMissingError(f"pulled tailoring is empty or missing: {local}")
    return local.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_verify_remote.py -v`
Expected: PASS (all rewritten + new probe_sudo tests)

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/verify/remote.py tests/test_verify_remote.py
git commit -S -m "feat(verify): thread SudoAuth through remote, pull via sudo cat (#16)"
```

---

## Task 6: Remove `scp_pull`; drop `scp` from `check_tools`

**Files:**
- Modify: `src/ks_gen/verify/ssh.py` (delete `scp_pull`; simplify `check_tools`)
- Modify: `src/ks_gen/verify/errors.py:36-39` (`ToolMissingError` docstring)
- Test: `tests/test_verify_ssh.py`

- [ ] **Step 1: Update the tests**

In `tests/test_verify_ssh.py`:
1. Delete `test_check_tools_raises_when_scp_missing`, `test_scp_pull_invokes_scp_with_user_host_remote_target`, and `test_scp_pull_nonzero_exit_raises_ssh_connect_error`.
2. Remove `scp_pull` from the `from ks_gen.verify.ssh import ...` line.
3. Replace `test_check_tools_passes_when_ssh_and_scp_present` with:

```python
def test_check_tools_passes_when_ssh_present() -> None:
    with patch("ks_gen.verify.ssh.shutil.which", side_effect=lambda t: f"/usr/bin/{t}"):
        check_tools()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_verify_ssh.py -v`
Expected: FAIL — `test_check_tools_raises_when_ssh_missing` still passes, but the import line still names `scp_pull` only if you missed step 1.2; the intended failure is that nothing references the removed symbols yet. (If green already, proceed — this step just confirms no stale references.)

- [ ] **Step 3: Implementation**

In `src/ks_gen/verify/ssh.py`, replace `check_tools` and delete `scp_pull` entirely:

```python
def check_tools() -> None:
    if not shutil.which("ssh"):
        raise ToolMissingError("required tool not on PATH: ssh")
```

Delete the whole `def scp_pull(...)` function.

In `src/ks_gen/verify/errors.py`, update the `ToolMissingError` docstring:

```python
class ToolMissingError(VerifyError):
    """system ssh not on PATH."""

    exit_code: ExitCode = ExitCode.TOOL_MISSING
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_verify_ssh.py tests/test_verify_errors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/verify/ssh.py src/ks_gen/verify/errors.py tests/test_verify_ssh.py
git commit -S -m "refactor(verify): drop scp; ssh is the only required tool (#16)"
```

---

## Task 7: `run_verify` gains `sudo_auth`

**Files:**
- Modify: `src/ks_gen/verify/__init__.py`
- Test: `tests/test_verify_run.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_verify_run.py`; add `from ks_gen.verify.auth import SudoAuth` to the imports)

```python
def test_run_verify_threads_sudo_auth_to_collect_arfs(tmp_path: Path) -> None:
    current = (FIXTURES / "arf-mixed.xml").read_text(encoding="utf-8")
    auth = SudoAuth(password="pw")
    seen: dict[str, object] = {}

    def fake_collect(**kw: object) -> CollectedArfs:
        seen["sudo_auth"] = kw["sudo_auth"]
        return CollectedArfs(current_text=current, install_text=None)

    with patch("ks_gen.verify.collect_arfs", side_effect=fake_collect):
        run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            ssh_extra_opts=[],
            timeout=600,
            sudo_auth=auth,
        )

    assert seen["sudo_auth"] is auth
```

This reuses the file's existing `_cfg()` factory and `FIXTURES` constant. `no_drift=True` avoids the install-ARF path so a single collector mock suffices.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_run.py -k sudo_auth -v`
Expected: FAIL — `run_verify() got an unexpected keyword argument 'sudo_auth'`

- [ ] **Step 3: Implementation**

In `src/ks_gen/verify/__init__.py`:

Add the import:

```python
from ks_gen.verify.auth import SudoAuth
```

Add the parameter to `run_verify` (keyword-only, after `timeout`):

```python
    timeout: int = 600,
    sudo_auth: SudoAuth = SudoAuth(),
) -> VerifyReport:
```

Pass it into both collector calls:

```python
        deployed_xml = collect_deployed_tailoring(
            host=host,
            user=user,
            workdir=workdir,
            ssh_extra_opts=extra_opts,
            sudo_auth=sudo_auth,
        )
```

```python
    arfs = collect_arfs(
        cfg=cfg,
        host=host,
        user=user,
        workdir=workdir,
        no_drift=effective_no_drift,
        ssh_extra_opts=extra_opts,
        timeout=timeout,
        sudo_auth=sudo_auth,
    )
```

Docstring corrections (the behavior changed): in the summary line change
"(requires passwordless sudo)" to "(passwordless sudo by default; pass a
password-mode `sudo_auth` for password sudo)"; add a `sudo_auth:` entry to the
Args block; and in Raises change `ToolMissingError: system ssh or scp not on
PATH.` to `ToolMissingError: system ssh not on PATH.` and
`SudoPromptError: passwordless sudo unavailable for user on host.` to
`SudoPromptError: sudo unavailable — passwordless missing, or wrong password.`
Also change the two `ssh_extra_opts` mentions of "ssh/scp" to "ssh".

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_run.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/verify/__init__.py tests/test_verify_run.py
git commit -S -m "feat(verify): run_verify accepts sudo_auth (#16)"
```

---

## Task 8: `--ask-sudo-pass` CLI flag

**Files:**
- Modify: `src/ks_gen/cli.py`
- Test: `tests/test_cli/test_verify.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_cli/test_verify.py`; add `from ks_gen.verify.auth import SudoAuth` to the imports)

The file already provides `_write_cfg(tmp_path)`, `_clean_report()`, a `CliRunner`, and patches `ks_gen.cli.run_verify` / `ks_gen.cli.check_tools`. Mirror that:

```python
def test_verify_ask_sudo_pass_threads_password_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_cfg(tmp_path)
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "secret")
    captured: dict[str, object] = {}

    def fake_run_verify(**kw: object) -> VerifyReport:
        captured["sudo_auth"] = kw["sudo_auth"]
        return _clean_report()

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--ask-sudo-pass"]
        )
    assert result.exit_code == 0, result.output
    assert isinstance(captured["sudo_auth"], SudoAuth)
    assert captured["sudo_auth"].is_password is True


def test_verify_default_is_passwordless(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_cfg(tmp_path)
    monkeypatch.delenv("KSGEN_SUDO_PASSWORD", raising=False)
    captured: dict[str, object] = {}

    def fake_run_verify(**kw: object) -> VerifyReport:
        captured["sudo_auth"] = kw["sudo_auth"]
        return _clean_report()

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert captured["sudo_auth"].is_password is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli/test_verify.py -k sudo -v`
Expected: FAIL — no such option `--ask-sudo-pass` / `sudo_auth` not passed.

- [ ] **Step 3: Implementation**

In `src/ks_gen/cli.py`, add the import:

```python
from ks_gen.verify.auth import resolve_sudo_auth
```

Add the flag to `verify_cmd` (place it after the `timeout` option, before the closing `) -> None:`):

```python
    ask_sudo_pass: bool = typer.Option(
        False,
        "--ask-sudo-pass",
        help=(
            "Use password-based sudo on the host: read the password from "
            "KSGEN_SUDO_PASSWORD, or prompt if unset. Default is passwordless "
            "(sudo -n). Never pass the password via --ssh-opts."
        ),
    ),
```

After `resolved_user = user or cfg.user.admin.name` and the existing
`extra_opts = shlex.split(...)` line, resolve the auth:

```python
    try:
        sudo_auth = resolve_sudo_auth(ask_sudo_pass, user=resolved_user, host=host)
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None
```

Add `sudo_auth=sudo_auth,` to the `run_verify(...)` call inside `_do`:

```python
            report = run_verify(
                cfg=cfg,
                host=host,
                user=resolved_user,
                workdir=workdir,
                no_drift=no_drift,
                check_tailoring=check_tailoring,
                baseline_path=baseline,
                capture_to=capture_baseline,
                ssh_extra_opts=extra_opts,
                timeout=timeout,
                sudo_auth=sudo_auth,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli/test_verify.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_verify.py
git commit -S -m "feat(verify): --ask-sudo-pass flag for password sudo (#16)"
```

---

## Task 9: Docs + full CI parity + code review

**Files:**
- Modify: any verify docs that describe the passwordless requirement (grep first)

- [ ] **Step 1: Update docs**

Run: `grep -rn "passwordless\|sudo -n\|nopasswd" docs/ README.md 2>/dev/null`
For each operator-facing doc hit that states verify *requires* passwordless sudo, add a sentence: verify now also supports password-based sudo via `--ask-sudo-pass` (password from `KSGEN_SUDO_PASSWORD` or a prompt; never via `--ssh-opts`). If there are no operator docs for verify beyond `--help`, skip — the flag help text (Task 8) is the doc.

- [ ] **Step 2: Run the full CI parity chain**

Run (from repo root; use the WSL venv per project notes if needed):

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all four green. If `ruff format --check` fails, run `ruff format src tests`, re-check, and commit the formatting as a `style:` commit.

- [ ] **Step 3: Commit any doc/style changes**

```bash
git add -A
git commit -S -m "docs(verify): note --ask-sudo-pass password mode (#16)"
```

- [ ] **Step 4: Code review before shipping**

Run `/code-review` on the working diff (branch vs `main`). Address or consciously dismiss each finding. This is required before opening the PR (project + global policy).

- [ ] **Step 5: Open the PR**

```bash
git push -u origin feat/verify-password-sudo
gh pr create --fill
```

Merge policy is **squash-only** (`gh pr merge --squash` after checks pass). Do not rebase-merge (deadlocks required signatures).

---

## Notes for the implementer

- **Signing:** every `commit -S` uses key `BE707B220C995478` and author `github.v5f9w@bitbucket.onl`. If a commit fails because gpg isn't found or the key is locked, STOP and tell the user — never fall back to `--no-gpg-sign`.
- **`SudoAuth()` as a default arg** is safe: the dataclass is frozen/immutable, so the shared instance can't be mutated.
- **Why `sudo -S -p ''`:** `-S` reads the password from stdin; `-p ''` empties the prompt so nothing lands in captured stderr. The verify commands (`test`, `oscap`, `rm`, `cat FILE`) never read stdin themselves, so the trailing password newline is harmless.
- **No golden-snapshot impact:** verify does not touch generated `ks.cfg`. Do not run `--snapshot-update`.
- **Install-regression harness:** not required — this change is verify-side only and does not affect what anaconda does.
```
