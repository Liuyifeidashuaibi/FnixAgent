<!-- markdownlint-disable MD041 -->
# `.github/` — repository configuration

This folder contains **GitHub-side** configuration for the `Liuyifeidashuaibi/FnixAgent` repository. Nothing in here ships with the product — it only affects how GitHub presents, triages, and automates this repo.

## Layout

```text
.github/
├── workflows/                 # GitHub Actions CI/CD
│   ├── ci.yml                 # Main CI (lint, typecheck, test, build)
│   ├── release.yml            # Tauri 2 cross-platform build
│   ├── release-drafter.yml    # Auto-draft release notes
│   ├── codeql.yml             # CodeQL static analysis
│   ├── scorecard.yml          # OpenSSF Scorecard
│   ├── security.yml           # Security scans
│   ├── stale.yml              # Stale-bot
│   ├── first-interaction.yml  # Greet new contributors
│   ├── labeler.yml            # Auto-label PRs by path
│   ├── labels.yml             # Sync repo labels
│   ├── issue-pr-link.yml      # Close issues when PRs merge
│   ├── markdown-link-check.yml
│   ├── build.yml              # Dev / nightly builds
│   ├── nightly-quality.yml    # Nightly deep quality gates
│   └── fnix-se-core.yml       # Self-evolution flywheel
│
├── ISSUE_TEMPLATE/            # Issue forms
│   ├── config.yml             # Chooser + contact links
│   ├── bug_report.md
│   ├── feature_request.md
│   ├── question.md
│   ├── documentation.md
│   ├── performance.md
│   ├── security.md
│   ├── rfc.md
│   └── blank.md
│
├── PULL_REQUEST_TEMPLATE/
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── branch-target.md
│   └── incomplete.md
│
├── DISCUSSION_TEMPLATE/
│   └── discussion-template.md
│
├── SUPPORT.md                 # Where to get help
├── FUNDING.yml                # Sponsor links
├── CODEOWNERS                 # Auto-assign reviewers
├── dependabot.yml             # Dependabot config
├── labeler.yml                # PR labeler rules
├── labels.yml                 # Label set
├── release-drafter.yml        # Release-drafter config
├── markdown-link-check.json   # Link-check config
└── README.md                  # ← you are here
```

## Conventions

- **PR template** lives at the top level so GitHub picks it up automatically.
- **Issue templates** live in `ISSUE_TEMPLATE/` and use the `config.yml` chooser.
- **CI workflows** are namespaced: `ci.yml` runs on PRs, `release.yml` runs on tags,
  `nightly-quality.yml` runs nightly, `codeql.yml` / `scorecard.yml` are supply-chain.
- **Labels** are declared once in `labels.yml` and synced via `labels.yml` workflow.
- **CODEOWNERS** is the source of truth for reviewer auto-assignment.

## Modifying

Before adding a new workflow, please:

1. Discuss in an issue (or RFC) for anything user-visible.
2. Pin versions of third-party actions by SHA for security.
3. Add the workflow to the table above.

See the root [CONTRIBUTING.md](../CONTRIBUTING.md) for the general contribution process.
