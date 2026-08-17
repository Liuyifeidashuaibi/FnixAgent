# NOTICE

`apps/workbench` is the **Fnix** desktop UI (React + Tauri + Tailwind + Monaco).

It was **derived from** [PunamIDE](https://github.com/mandaloriantrader/PunamIDE) (MIT). Original license text: `LICENSE-MIT-PUNAMIDE`.

Fnix-specific changes include:

- Product identity, prompts, settings keys, and data dirs (`.fnix`, `fnix-settings*.json`)
- Harness bridge to Fnix agentd (`src/lib/fnixBridge.ts`) for BYOK → `~/.fnix`
- Workspace ensure → `{workspace}/.fnix`
- Project rules: `.fnix/rules.md` / `AGENTS.md`
- No default third-party Sentry DSN

This tree is maintained as Fnix product code, not an upstream fork mirror.
