# Release Process

How we cut a release of FnixAgent. This document is for **maintainers**. If you're a contributor, you don't need to read this — opening a PR labeled `release-blocker` is enough.

> 📌 **TL;DR:** Branch → freeze → train → ship → announce.

---

## 🗓️ Cadence

- **Minor** (1.x.0): every 8–10 weeks
- **Patch** (1.x.y): as needed, on a 24–72 h notice
- **Pre-release** (1.x.y-beta.N): weekly during the last month before GA

The exact date is set in [Discussions → Announcements](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/announcements) 2 weeks before the cut.

---

## 🚦 Release gates

A release is **ready to ship** when all of the following are green on `main`:

| Gate                       | What it checks                                             | Where                                               |
| -------------------------- | ---------------------------------------------------------- | --------------------------------------------------- |
| **CI**                     | ruff, pyright, pytest (3.11/3.12/3.13), bandit, shellcheck | [ci.yml](../.github/workflows/ci.yml)               |
| **CodeQL**                 | Static analysis (Python + TS)                              | [codeql.yml](../.github/workflows/codeql.yml)       |
| **Scorecard**              | Supply-chain posture ≥ 7                                   | [scorecard.yml](../.github/workflows/scorecard.yml) |
| **Coverage**               | ≥ 80 % overall, 100 % on `core/security/`                  | Codecov report                                      |
| **E2E**                    | Playwright + agentd smoke                                  | [ci.yml](../.github/workflows/ci.yml)               |
| **OpenSSF Best Practices** | All "passing" criteria met                                 | bestpractices.coreinfrastructure.org                |
| **Manual sign-off**        | Lead maintainer approves                                   | Discussions → Announcements                         |

If a gate is red, the release is **held**. Hotfixes are exempt with lead-approver sign-off.

---

## 🌲 Branching model

```text
main                 ← always releasable
 ├── release/1.2.0   ← cut at RC, only bug fixes
 │     ├── hotfix/1.2.0-typo        (merged back to main)
 │     └── hotfix/1.2.0-race        (merged back to main)
 ├── feature/...
 └── fix/...
```

- `main` is the **trunk**. Everything merges here via squash.
- `release/<version>` is a **stable line**. It only accepts cherry-picks from `main`.
- `feature/*` and `fix/*` are short-lived branches off `main`.

---

## 📋 Step-by-step

### 1. Cut the release branch

```bash
# On main, ensure it's clean
git checkout main
git pull --rebase origin main
pnpm verify:beta       # full local gate

# Create the release branch
git checkout -b release/1.2.0
git push -u origin release/1.2.0
```

### 2. Bump the version

- Update `version` in `pyproject.toml`.
- Update `version` in `apps/workbench/package.json`.
- Update `version` in `Cargo.toml` (root + any sub-crates).
- Update the docker tags in `deploy/docker/`.
- Add a new section at the top of `CHANGELOG.md`:

```markdown
## [1.2.0] - 2026-09-15

### Added

- ... (most-impactful feature first)

### Changed

- ...

### Fixed

- ...

### Security

- ...

See [Release notes](https://github.com/Liuyifeidashuaibi/FnixAgent/releases/tag/v1.2.0).
```

### 3. Open the Release Candidate PR

- Push a `v1.2.0-rc.1` tag.
- The `release-drafter` workflow auto-drafts the GitHub Release notes.
- Open a PR `release/1.2.0 → main` titled **"Release 1.2.0"**.
- Mark it as **draft** until CI is green.
- Pin the PR to the repo so reviewers see it first.

### 4. Freeze window

From RC cut until GA:

- **No new features** to `release/1.2.0` — only bug fixes and doc updates.
- Daily **smoke** runs (`nightly-quality.yml`).
- If a critical regression is found, **roll forward**, do not backport to a frozen release line.

### 5. Sign off

The lead maintainer:

1. Reviews the **Release notes** draft.
2. Re-runs the full gate locally: `pnpm verify:beta && pnpm gate:* && pnpm e2e:full`.
3. Tests the installers on **at least 2 platforms** (Windows + macOS, or macOS + Linux).
4. Approves the release PR.
5. Squashes and merges.

### 6. Tag & ship

```bash
git checkout main
git pull --rebase
git tag -s v1.2.0 -m "Release 1.2.0"
git push origin v1.2.0
```

This triggers `release.yml`, which:

- Builds the **Tauri 2 desktop** for Windows, macOS, Linux.
- Signs the binaries (cosign for SBOM, code-signing on Windows/macOS).
- Uploads to the **draft** GitHub Release.
- Publishes to the update server.

### 7. Publish the GitHub Release

- The `release-drafter` workflow updates the draft with the final notes.
- The lead maintainer clicks **Publish**.
- The Tauri updater picks up the new version on the next launch.

### 8. Announce

- 📣 [Discussions → Announcements](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/announcements) — one post with highlights + links.
- 🐦 Twitter / X — short thread.
- 📧 `liuyifeidashuaibi@gmail.com` mailing list.
- 🇨🇳 WeChat / 中文社区 — 中文要点.

### 9. Post-release

- [ ] Close the milestone.
- [ ] Open any follow-up issues for known issues.
- [ ] Update the **Roadmap** ([docs/ROADMAP.md](../docs/ROADMAP.md)).
- [ ] Update [MAINTAINERS.md](../MAINTAINERS.md) if maintainer roles changed.
- [ ] Bump `version` in `main` to `<next>-dev` (e.g. `1.3.0-dev`).

---

## 🔥 Hotfix process

For **critical** issues on a released version:

1. Branch from the release tag: `git checkout -b hotfix/1.2.0-fix-typo v1.2.0`.
2. Fix + test.
3. Open a PR to **both** `release/1.2.0` **and** `main`.
4. Tag as `v1.2.1`, ship, announce.

Non-critical fixes can wait for the next scheduled patch.

---

## 🪦 Yanking a release

If a release must be pulled (e.g., a security issue ships):

1. **Mark the GitHub Release as "Pre-release"** (do not delete — git history matters).
2. **Pull the Tauri update** so existing installs don't auto-update to the bad version.
3. Open an advisory (see [SECURITY.md](../SECURITY.md)).
4. Cut a `v1.2.1` with the fix.
5. Re-publish as stable.

---

## 🤖 Automation

Most of this is wired up. The human-only steps are:

- Final sign-off (step 5)
- Publishing the GitHub Release (step 7)
- Sending the announcement (step 8)

Everything else runs in CI.

---

## 📚 Further reading

- [Keep a Changelog](https://keepachangelog.com/)
- [Semantic Versioning](https://semver.org/)
- [Tauri auto-updater docs](https://v2.tauri.app/plugin/updater/)

---

_Last updated: 2026-08-17_
