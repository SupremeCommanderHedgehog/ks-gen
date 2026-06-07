## Summary

<one to three sentences describing the change>

## Related issue

Closes #

## Test plan

- [ ] Local CI parity: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
- [ ] <feature-specific verification, if any>

## Checklist

- [ ] Conventional-commit subject (`feat:`, `fix:`, `docs:`, `refactor:`, `style:`, `test:`, `chore:`, `ci:`)
- [ ] Commits GPG-signed
- [ ] CHANGELOG entry added, or commits are conventional so release-please picks them up
- [ ] Documentation updated if behavior or surface changed
