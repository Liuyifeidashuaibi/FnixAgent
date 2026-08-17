# Governance

> **TL;DR:** FnixAgent is a **sole-maintainer** project. All decisions are made by the maintainer. External contributions are not accepted (All Rights Reserved license).

## Maintainer

- **Current:** [@Liuyifeidashuaibi](https://github.com/Liuyifeidashuaibi)
- Sets project vision, releases, and all technical decisions.
- Owns the roadmap, security disclosures, and external communications.

## Decision-making

| Decision type        | Process                                           |
| -------------------- | ------------------------------------------------- |
| Bug fixes, refactors | Maintainer discretion                             |
| New features         | Tracked in [ROADMAP.md](../docs/ROADMAP.md)       |
| Public API change    | Maintainer approval + changelog                   |
| Security fix         | Private process per [SECURITY.md](../SECURITY.md) |
| License change       | Maintainer decision + community notice            |

## Release process

1. Cut a release branch from `main`.
2. Run the full release gate (`pnpm verify:beta && pnpm gate:*`).
3. Publish artifacts via the `release.yml` GitHub Actions workflow.
4. Maintainer signs off on the GitHub Release before publishing.

See [RELEASE.md](RELEASE.md) for the full procedure.

## Conflict resolution

1. Discuss on the relevant issue or [Discussions](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions) with civility (per [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)).
2. Maintainer makes the final binding decision.

---

_Last updated: 2026-08-17_
