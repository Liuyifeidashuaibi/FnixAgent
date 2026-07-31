# Open Source Release Checklist（Community）

Use this before tagging a public **Community** release (e.g. `v1.0.0-beta.1`).

双轨边界见 [`layers/COMMERCIAL.md`](./layers/COMMERCIAL.md)。企业部署见 [`DEPLOY.md`](./DEPLOY.md)。

## Product

- [x] Desktop starts with `pnpm dev:all:tauri` / `pnpm dev`
- [x] BYOK gate works (no API Key → banner + disabled submit)
- [ ] Work stream completes with user-provided Key（需有效 Key 手测）
- [x] Code Agent Diff Accept 路径可用（`@file` + Accept/Reject）
- [x] README + INSTALL / GETTING_STARTED 无强制登录

## Security

- [x] No real secrets in git (`.env` gitignored)
- [x] `.env.example` uses placeholder tokens
- [x] `FNIX_API_ONLY=1` documented（Desktop 默认）

## Build

- [ ] `pnpm verify:beta` passes（发版前跑）
- [ ] `pnpm build` / `pnpm prepare:release` produces installer locally
- [x] GitHub Release workflow exists (`.github/workflows/release.yml`)

## GitHub

- [ ] Release notes with download links（打 tag 后）
- [x] LICENSE (Apache-2.0) at repo root
- [x] Six-layer reports in `docs/layers/`

## Disk / CI hygiene

- [x] `pnpm clean:cache` documented
- [x] `.gitignore` excludes `target/`, `node_modules/`, `.env`, runtime data
