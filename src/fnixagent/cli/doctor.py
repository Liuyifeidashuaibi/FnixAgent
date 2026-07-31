"""fnixagent doctor — environment checks (Fnix CLI)."""

from __future__ import annotations

import os
import shutil
import sys


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!] {msg}")


def _fail(msg: str) -> None:
    print(f"  [X] {msg}")


def run_doctor() -> int:
    from fnixagent.harness.config import read_config_toml
    from fnixagent.harness.paths import (
        config_path,
        memories_dir,
        sessions_dir,
        skills_dir,
        soul_path,
    )
    from fnixagent.harness.secrets import secrets_status
    from fnixagent.harness.workspace import ensure_home_layout

    failed = 0
    print("\nFnix Harness Doctor\n")

    print(f"Python {sys.version.split()[0]}")
    if sys.version_info < (3, 11):
        _fail("Python 3.11+ required")
        failed += 1
    else:
        _ok("Python version")

    home = ensure_home_layout()
    _ok(f"FNIX_HOME = {home}")

    for label, path in (
        ("config.toml", config_path()),
        ("SOUL.md", soul_path()),
        ("memories/", memories_dir()),
        ("skills/", skills_dir()),
        ("sessions/", sessions_dir()),
    ):
        if path.exists():
            _ok(label)
        else:
            _fail(f"missing {label}")
            failed += 1

    cfg = read_config_toml()
    provider = str(cfg.get("provider") or "").strip()
    model = str(cfg.get("model") or "").strip()
    if provider and model:
        _ok(f"model: {provider} / {model}")
    else:
        _warn("provider/model not set — run: fnixagent setup")

    sec = secrets_status()
    if sec.get("has_api_key"):
        _ok(f"API Key: {sec.get('key_hint')}")
    else:
        _warn("API Key not set — Desktop Settings or fnixagent setup")

    profile = os.getenv("FNIXAGENT_PROFILE", "standalone")
    _ok(f"FNIXAGENT_PROFILE={profile}")

    for cmd in ("git", "node", "pnpm"):
        if shutil.which(cmd):
            _ok(cmd)
        else:
            _warn(f"{cmd} not on PATH (needed for Desktop from source)")

    try:
        from fnixagent.core.profile import profile_info

        info = profile_info()
        _ok(f"profile={info.get('profile')} storage={info.get('storage')}")
    except Exception as e:
        _fail(f"profile load failed: {e}")
        failed += 1

    # agentd / vite reachability (developer open-box)
    import urllib.error
    import urllib.request

    ports = []
    for env_key in ("FNIX_API_PORT", "VITE_API_BASE", "API_TARGET"):
        raw = (os.getenv(env_key) or "").strip()
        if raw.isdigit():
            ports.append(int(raw))
        elif "://" in raw:
            try:
                from urllib.parse import urlparse

                hostport = urlparse(raw).netloc or ""
                if ":" in hostport:
                    ports.append(int(hostport.rsplit(":", 1)[-1]))
            except Exception:
                pass
    for p in (8003, 8011, 8000):
        if p not in ports:
            ports.append(p)

    agentd_ok = False
    for port in ports[:6]:
        url = f"http://127.0.0.1:{port}/health"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    _ok(f"agentd healthy on :{port} ({url})")
                    agentd_ok = True
                    break
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    if not agentd_ok:
        _warn(
            "agentd not reachable on common ports "
            f"({', '.join(str(p) for p in ports[:6])}) — "
            "start with: python -m fnixagent.main serve --port 8003 --no-reload"
        )
        _warn("Workbench VITE_API_BASE must match that port (see apps/workbench/.env.local)")

    # Packaging / standalone readiness (Day 15–30)
    from pathlib import Path

    here = Path(__file__).resolve()
    repo = next(
        (
            candidate
            for candidate in (here.parents[3], here.parents[2], Path.cwd())
            if (candidate / "apps" / "workbench").is_dir()
        ),
        here.parents[3],
    )
    agentd_dir = repo / "apps" / "workbench" / "src-tauri" / "resources" / "agentd"
    names = ("fnix-agentd.exe", "fnix-agentd", "agentd.exe", "agentd")
    if any((agentd_dir / name).is_file() for name in names):
        _ok(f"bundled agentd sidecar present ({agentd_dir})")
    else:
        _warn("bundled agentd missing — run: pnpm bundle:agentd (needs PyInstaller)")

    cap = (os.getenv("FNIX_CAPABILITY_TOKEN") or "").strip()
    if cap:
        _ok("FNIX_CAPABILITY_TOKEN set")
    else:
        _warn("FNIX_CAPABILITY_TOKEN unset (desktop-managed runtime injects one at boot)")

    print("\n---")
    print("Paths:")
    print("  End user  -> GitHub Releases")
    print("  Developer -> pnpm setup && pnpm doctor && pnpm dev")
    print("  CLI       -> fnixagent setup && fnixagent chat")
    print("  Product   -> docs/FNIX_PRODUCT.md\n")

    if failed:
        print(f"Doctor: {failed} failed")
        return 1
    print("Doctor: ready")
    return 0
