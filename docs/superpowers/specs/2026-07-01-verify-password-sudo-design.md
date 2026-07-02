# `ks-gen verify` password-sudo support (#16)

- **Status:** design approved, pre-implementation
- **Date:** 2026-07-01
- **Issue:** #16 (ks-gen verify: password sudo / root SSH support)
- **Scope decision:** password-required sudo only. Direct root SSH
  (`--user root` + verify-only key) is explicitly **out of scope** and
  stays parked on #16 for a future opt-in.

## Problem

`ks-gen verify` today assumes two things about the target host:

1. SSH login is key-based (`BatchMode=yes`, no interactive auth), and
2. the login user has **passwordless** sudo — every privileged remote
   command runs as `sudo -n <cmd>` and `probe_sudo` gates on
   `sudo -n true`.

This matches the wizard's `sudo: nopasswd_yes` default. It does not cover
a host on a strict policy where the admin user's sudo **requires a
password**. On such a host verify cannot run at all.

A second, related gap surfaces the moment we look closely at file
retrieval. Verify pulls three files off the host:

- `/tmp/ksgen-verify-current.arf.xml` — freshly written by
  `sudo oscap --results-arf`, owned root.
- `/root/oscap-remediation-results.xml` — the install-time ARF, root-only.
- `/root/tailoring.xml` — `chmod 0600`, root-owned, inside `/root`
  (`0550`, non-root cannot traverse).

All three are pulled today with a plain `scp` running **as the login
user**. That can only succeed where the admin user can already read the
path — which a strict host will not permit for `/root`, and which STIG's
common **root umask 077** breaks even for the `/tmp` current ARF (oscap
inherits root's umask, producing a `0600` file). So the plain-scp path is
latently fragile for passwordless hosts too, not just password-sudo ones.

## Goals

- Let `verify` authenticate sudo with a password when the host requires it.
- Keep the passwordless `sudo -n` path the zero-config default —
  behavior without the new flag is byte-for-byte identical to today.
- Never expose the password: not in argv, not in a temp file, not in the
  report/JSON output, not in any log line or object `repr`.
- Fix file retrieval so it works on strict / umask-077 hosts, as a
  coherent part of the same change.
- Shape the auth seam so #10 (fleet mode) reuses it without rework.

## Non-goals

- Direct root SSH (parked on #16).
- Per-command sudo password caching / `sudo -k` management.
- Fleet / multi-host fan-out (#10) — only the reusable seam is in scope.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Which auth path | Password-required sudo only (not root SSH) |
| Password source | `KSGEN_SUDO_PASSWORD` env var, falling back to a `getpass` prompt |
| Mode trigger | Explicit `--ask-sudo-pass` flag; default stays `sudo -n` |
| Code shape | Approach A: a small `SudoAuth` value object + `sudo_prefix` helper, threaded as one param |
| File pull | Add sudo-staging; route **all** pulls through `sudo cat`, removing scp |

## Design

### 1. `SudoAuth` value object + helpers — `src/ks_gen/verify/auth.py` (new)

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class SudoAuth:
    password: str | None = field(default=None, repr=False)  # None => sudo -n; str => sudo -S

    @property
    def is_password(self) -> bool:
        return self.password is not None


def sudo_prefix(auth: SudoAuth) -> str:
    return "sudo -S -p ''" if auth.is_password else "sudo -n"


def resolve_sudo_auth(ask: bool, *, user: str, host: str) -> SudoAuth:
    # not ask                -> SudoAuth(None)  (passwordless, today's behavior)
    # ask + KSGEN_SUDO_PASSWORD set and non-empty -> SudoAuth(that value)
    # ask + env unset        -> getpass.getpass(f"sudo password for {user}@{host}: ")
    # resolved value empty   -> ConfigError (usage exit); never silently fall back to -n
```

`password` carries `repr=False` so a stray traceback or debug log never
prints the secret. This object is the single seam #10 will instantiate
once per host.

### 2. Execution plumbing — `src/ks_gen/verify/ssh.py`

`ssh_exec` gains one parameter:

```python
def ssh_exec(host, user, remote_cmd, *, extra_opts=None, timeout=None,
             stdin_input: str | None = None) -> SshResult:
    ...
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, check=False, input=stdin_input)
```

- `BatchMode=yes` **stays** — SSH login remains key-based; the password is
  only for sudo, delivered over the already-authenticated channel via
  stdin.
- No `ssh -t` / no TTY. `sudo -S` reads the password from the first stdin
  line. The privileged commands verify runs (`test -r`, `oscap`, `rm -f`,
  `cat FILE`) do not read stdin, so the trailing newline is harmless —
  `cat FILE` reads its file argument, not the pipe.

### 3. File retrieval — `sudo_pull`, replacing scp — `src/ks_gen/verify/ssh.py`

```python
def sudo_pull(host, user, remote_path, local_path, *, auth, extra_opts, timeout=None):
    r = ssh_exec(host, user, f"{sudo_prefix(auth)} cat {shlex.quote(remote_path)}",
                 extra_opts=extra_opts, timeout=timeout,
                 stdin_input=(f"{auth.password}\n" if auth.is_password else None))
    if r.exit_code != 0:
        raise SshConnectError(f"sudo cat {remote_path} exit {r.exit_code}: "
                              f"{_first_stderr_line(r.stderr)}")
    local_path.write_text(r.stdout, encoding="utf-8")
```

All three pulls in `remote.py` move from `scp_pull` to `sudo_pull`. The
existing 0-byte / missing-file guards in `collect_arfs` /
`collect_deployed_tailoring` remain (now checking the written file).

`scp_pull` is **removed**, and `check_tools()` drops its `scp` check
(now only `ssh` is required). Rationale: `/root` `0550` + STIG root
umask 077 mean plain scp cannot reliably read any of the three files even
in the passwordless case; one `sudo cat` path is both correct on strict
hosts and a latent-robustness fix for the default path.

ARFs are UTF-8 XML in the low-MB range — `subprocess` stdout capture and a
text write handle them fine.

### 4. `remote.py` threading

`probe_sudo`, `collect_arfs`, `collect_deployed_tailoring`, and the
`finally`-block cleanup all take a `SudoAuth` and build privileged
commands as `f"{sudo_prefix(auth)} {cmd}"`, passing
`stdin_input=f"{auth.password}\n"` when `auth.is_password`.

`probe_sudo` runs `f"{sudo_prefix(auth)} true"`. Its error message
branches on mode:

- passwordless: "passwordless sudo is required" (unchanged).
- password: "sudo failed (exit N) — wrong password or user not in sudoers".

### 5. CLI surface — `src/ks_gen/cli.py`

One new flag on `verify`:

```
--ask-sudo-pass   Use password-based sudo on the host: read the password
                  from KSGEN_SUDO_PASSWORD, or prompt if unset. Default is
                  passwordless (sudo -n).
```

Resolution happens after `resolved_user` is known:

```python
try:
    sudo_auth = resolve_sudo_auth(ask_sudo_pass, user=resolved_user, host=host)
except ConfigError as e:
    typer.echo(str(e), err=True); raise typer.Exit(code=int(e.exit_code)) from None
```

`sudo_auth` threads into `run_verify(..., sudo_auth=sudo_auth)` →
`collect_arfs` / `collect_deployed_tailoring`. `run_verify` in
`src/ks_gen/verify/__init__.py` gains a `sudo_auth: SudoAuth` parameter.

### 6. Security handling

- Password lives only in memory and the subprocess stdin pipe — never in
  argv, never a temp file, never the report/JSON, never a log line
  (`repr=False` on the field).
- `-p ''` suppresses sudo's stderr prompt so captured stderr cannot carry
  the prompt text.
- `getpass` for the interactive prompt (no terminal echo).
- Empty resolved password is a hard `ConfigError`, not a silent
  passwordless fallback — the operator asked for password mode and gets it
  or a clear error.
- Documented caveat in `--help` / docs: supply the password only via the
  env var or the prompt, never via `--ssh-opts`.

## Testing

Unit-only; no host required, no golden-snapshot impact (verify does not
touch generated `ks.cfg`).

- `sudo_prefix`: `SudoAuth(None)` → `"sudo -n"`; `SudoAuth("x")` →
  `"sudo -S -p ''"`.
- `resolve_sudo_auth`: not-ask → `password is None`; ask + env set →
  that value; ask + env unset → `getpass` (mocked); resolved empty →
  `ConfigError`.
- `SudoAuth` repr omits the password: `"secret" not in repr(SudoAuth("secret"))`.
- `ssh_exec` forwards `stdin_input` as `subprocess.run(input=...)` (mock
  `subprocess.run`, assert the kwarg).
- `sudo_pull`: success writes stdout to the local path; nonzero exit
  raises `SshConnectError`.
- `collect_arfs` + `collect_deployed_tailoring`: under password auth emit
  `sudo -S -p ''` and pass the password on stdin; under passwordless emit
  `sudo -n` with `stdin_input=None`.
- `probe_sudo`: password-mode failure yields the wrong-password/sudoers
  message; passwordless failure unchanged.
- CLI: `--ask-sudo-pass` with `KSGEN_SUDO_PASSWORD` set threads a
  password-mode `SudoAuth`; without the flag the auth is passwordless.

## Files touched

- `src/ks_gen/verify/auth.py` — **new**: `SudoAuth`, `sudo_prefix`, `resolve_sudo_auth`.
- `src/ks_gen/verify/ssh.py` — `ssh_exec` `stdin_input`; new `sudo_pull`; remove `scp_pull`; `check_tools` drops `scp`.
- `src/ks_gen/verify/remote.py` — thread `SudoAuth`; `sudo_prefix` for all privileged commands; `sudo_pull` for all retrievals; `probe_sudo` message branch.
- `src/ks_gen/verify/__init__.py` — `run_verify` gains `sudo_auth`.
- `src/ks_gen/cli.py` — `--ask-sudo-pass`; resolve + thread `SudoAuth`.
- `tests/` — unit coverage per the Testing section.
- Docs/help — `--ask-sudo-pass`, `KSGEN_SUDO_PASSWORD`, the "never via `--ssh-opts`" caveat.

## Rejected alternatives

- **Root SSH** — out of scope per the issue; conflicts with the STIG
  `permit_root_login: no` default.
- **Env-var-only / prompt-only** password source — env+prompt covers both
  CI/automation and manual use.
- **Flag-or-env / auto-fallback** mode triggers — an exported var silently
  changing behavior (or masking not-in-sudoers as a password prompt) is a
  footgun; explicit flag chosen.
- **`SudoRunner` class (Approach B)** — cleaner for fleet fan-out but a
  larger refactor of working code for a #10 benefit not yet shaped; YAGNI.
- **Bare `sudo_password: str` threaded everywhere (Approach C)** — scatters
  the sudo-form logic and sprays a raw secret through six signatures.
- **`sudo cat` for `/root` only, keep scp for `/tmp` ARF** — leaves the
  umask-077 fragility in place and keeps two retrieval paths; unified
  `sudo cat` chosen.
