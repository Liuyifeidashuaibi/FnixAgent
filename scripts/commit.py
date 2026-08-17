#!/usr/bin/env python3
"""
FnixAgent 一键 git 提交脚本
智能检测当前分支,安全 commit + push

用法:
    python scripts/commit.py                    # 自动检测
    python scripts/commit.py --message "msg"    # 自定义信息
    python scripts/commit.py --no-push          # 只 commit,不 push
    python scripts/commit.py --branch main      # 强制指定分支
    python scripts/commit.py --merge-to main    # 提交到当前分支后,合并到 main 并 push 两者
"""

from __future__ import annotations
import subprocess
import sys
import argparse
from pathlib import Path


def run(cmd: list[str], cwd: Path = None, check: bool = True,
        capture: bool = False) -> subprocess.CompletedProcess:
    """运行命令。capture=True 时收集 stdout/stderr 返回对象"""
    print(f"$ {' '.join(cmd)}")
    if capture:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            encoding='utf-8', errors='replace',
        )
        if check and result.returncode != 0:
            print(f"[FAIL] {result.stderr}")
            sys.exit(result.returncode)
        return result
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=False, text=True,
        encoding='utf-8', errors='replace',
    )
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result


def current_branch(repo_root: Path) -> str:
    """读取当前分支名"""
    r = run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root, capture=True, check=False)
    return r.stdout.strip() or "main"


def main() -> int:
    parser = argparse.ArgumentParser(description="FnixAgent git commit helper")
    parser.add_argument("--message", "-m", help="Commit message override")
    parser.add_argument("--no-push", action="store_true", help="Skip push step")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    parser.add_argument("--branch", help="Override target branch")
    parser.add_argument("--merge-to",
                        help="After commit, merge current branch into this branch "
                             "and push both. e.g. --merge-to main")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    print(f"== FnixAgent Git Commit Helper ==")
    print(f"[Repo]  {repo_root}")

    branch = args.branch or current_branch(repo_root)
    print(f"[Branch] {branch}")

    # 检查 git 状态
    result = run(["git", "status", "--short"], cwd=repo_root,
                 capture=True, check=False)
    if not result.stdout.strip():
        print("[OK] Nothing to commit. Working tree clean.")
        return 0

    # 统计文件数
    files = [l for l in result.stdout.strip().split("\n") if l.strip()]
    print(f"\n[Files] {len(files)} pending changes")
    if len(files) <= 10:
        for f in files:
            print(f"  {f}")
    else:
        for f in files[:5]:
            print(f"  {f}")
        print(f"  ... and {len(files) - 5} more")

    if args.dry_run:
        print("\n[Dry run] Skipping actual commit.")
        return 0

    # 默认 commit 信息
    commit_msg = args.message or """feat: top-tier proprietary project governance (All Rights Reserved)

## Legal & Branding
- LICENSE: bilingual All Rights Reserved with View-Only License clause
- LICENSE-COMMERCIAL.md: commercial licensing flow
- TRADEMARKS.md: trademark policy
- NOTICE: third-party components + legal notice
- README.md, CONTRIBUTING.md: aligned with proprietary stance

## Architecture Decision Records
- 5 ADRs (MADR 4.0): Tauri runtime, BYOK, Markdown+Git memory,
  KTG/STP/MFP, Python+uv
- docs/adr/README.md with index and template

## Core Documentation (60+ files)
- FAQ.md (24 Q&A)
- API.md (Python/Rust/TS SDK + HTTP API + CLI + MCP)
- EXAMPLES.md (12 runnable examples)
- docs/GLOSSARY.md, MIGRATION.md, COMPARISON.md, INTEGRATIONS.md
- docs/operations/TROUBLESHOOTING.md

## Engineering Docs
- PERFORMANCE, ACCESSIBILITY, TESTING, I18N, PLUGINS
- SECURITY: THREAT-MODEL (STRIDE), PRIVACY

## Operations Docs
- INCIDENT-RESPONSE, REVIEWER-GUIDE, TRIAGE
- MAINTAINER-ONBOARDING
- CITATIONS, FUNDING, HIRING-ONE-PAGER, INTERVIEW-PREP

## Marketing Templates
- PRESS-KIT, BLOG-TEMPLATE, SOCIAL-GUIDE, TALK-TEMPLATE
- DEMO-SCRIPT.md (5-min recording script)

## Governance
- 8 issue templates + PR template + Discussion categories
- 38 label taxonomy
- 8 GitHub Actions workflows (codeql, scorecard, stale, etc.)
- All-Contributors config

## Sub-project READMEs
- desktop-tauri, fnix-local, protocol, sdk (4 fully rewritten)

## Brand Assets
- logo.svg, icon.svg (isometric cube + neural nodes)
- logo-NN.png (16/32/64/128/256/512/1024)
- icon-NN.png (16/32/64/128/256/512/1024)
- favicon.png / favicon.ico
- og-image.png (1280x640 with text)
- colors.md, typography.md, usage.md (updated to match logo)

## Tauri Icon Set
- 15 PNG icons (32/128/256/284/310/...)
- icon.ico (multi-size Windows)
- icons/generator/generate.py (Pillow-based, no cairo dep)

## K8s Manifests
- namespace, deployment, service, PDB/HPA/NetworkPolicy
- README with security hardening

## Scripts
- scripts/commit.py (one-click commit + push)

## Top-Level
- OPEN_SOURCE_CHECKLIST.md (all 17 categories checked)

Co-Authored-By: Liu Yifei <hello@github.com/Liuyifeidashuaibi/FnixAgent>"""

    print(f"\n[Commit message] {len(commit_msg)} chars")
    print(f"  First 200 chars: {commit_msg[:200]}...")

    # git add
    print("\n[Step 1/4] git add -A")
    run(["git", "add", "-A"], cwd=repo_root)

    # git commit
    print("\n[Step 2/4] git commit")
    result = subprocess.run(
        ["git", "commit", "-F", "-"],
        cwd=repo_root,
        input=commit_msg,
        text=True,
        encoding='utf-8',
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"[FAIL] {result.stderr}")
        if "nothing to commit" in (result.stderr or ""):
            print("[OK] Nothing to commit (already committed).")
        return result.returncode
    print(result.stdout)

    # git push
    if not args.no_push:
        print(f"\n[Step 3/4] git push origin {branch}")
        result = run(["git", "push", "origin", branch], cwd=repo_root,
                     capture=True, check=False)
        if result.returncode != 0:
            print(f"[FAIL] {result.stderr}")
            print(f"[Hint] First push? Try: git push -u origin {branch}")
            print("[Hint] Auth issue? Set up SSH key or GitHub CLI login.")
            return result.returncode
        print(result.stdout if result.stdout else "[OK] pushed")

        # 验证 remote
        print(f"\n[Step 4/4] Verify remote state")
        r = run(["git", "ls-remote", "--heads", "origin", branch],
                cwd=repo_root, capture=True, check=False)
        if r.returncode == 0 and branch in r.stdout:
            local_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root, capture_output=True, text=True,
            ).stdout.strip()
            if local_sha in r.stdout:
                print(f"[Verified] origin/{branch} is at {local_sha[:8]}")
                print(f"\n{'=' * 50}")
                print("[SUCCESS] Commit pushed and verified!")
                print(f"  https://github.com/Liuyifeidashuaibi/FnixAgent/tree/{branch}")
                print(f"{'=' * 50}")
            else:
                print(f"[WARN] origin has different SHA, but push succeeded")
        else:
            print(f"[WARN] Could not verify remote (branch {branch})")

    # merge-to main
    if args.merge_to and args.merge_to != branch:
        print(f"\n[Extra] Merging {branch} -> {args.merge_to}")
        run(["git", "checkout", args.merge_to], cwd=repo_root, check=False)
        result = run(["git", "merge", "--no-ff", branch,
                      "-m", f"Merge branch '{branch}'"],
                     cwd=repo_root, capture=True, check=False)
        if result.returncode != 0:
            print(f"[FAIL] merge failed: {result.stderr}")
            return result.returncode
        print(result.stdout)
        if not args.no_push:
            run(["git", "push", "origin", args.merge_to], cwd=repo_root)
            print(f"\n[SUCCESS] {args.merge_to} also updated!")

    # 后续步骤
    print("\n[NEXT STEPS - Manual on GitHub]")
    print("  1. Visit https://github.com/Liuyifeidashuaibi/FnixAgent")
    print("  2. Settings -> General -> Features: enable Discussions")
    print("  3. Settings -> General -> Social preview:")
    print("       upload assets/brand/og-image.png")
    print("  4. Settings -> Security -> Code security: enable CodeQL")
    print("  5. Settings -> Security -> Dependabot: enable")
    if branch != "main":
        print(f"  6. Open PR: feat/{branch} -> main for review")

    return 0


if __name__ == "__main__":
    sys.exit(main())