# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.3.x   | yes       |
| < 0.3   | no        |

## Reporting a vulnerability

Please use **GitHub's private vulnerability reporting** for new reports:

  https://github.com/SupremeCommanderHedgehog/ks-gen/security/advisories/new

For out-of-band contact, email **github.v5f9w@bitbucket.onl** (PGP fingerprint
`5741F291946EBD4A8B698BA1BE707B220C995478`). Do **not** open a public
issue for security problems.

Expect an initial response within 5 business days. Once a fix lands,
we will coordinate disclosure timing with you before publishing.

## Release attestation

Tags through `v0.3.0` are GPG-signed by the maintainer. From `v0.3.1`
forward, releases are automated via `release-please`; tags are
GitHub-attested (TLS + signed merge commits) rather than GPG-signed.
The release commit on `main` continues to be GPG-signed.

## Secret scanning

Once this repository is public, GitHub secret scanning and push
protection are enabled. Until then, the maintainer relies on local
pre-commit hooks and Dependabot for supply-chain coverage.
