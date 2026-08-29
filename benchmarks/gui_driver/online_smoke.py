# -*- coding: utf-8 -*-
"""在线只读冒烟（P0 最后一项）：发现"我们没想到过的性质"。

与脏页面压力集的关系是互补的，谁也替代不了谁：

  脏页面集：性质逐个隔离、可复现、可判定、可归因——但都是我们自己造的，
            证明不了"真实分布上还有什么没见过"。
  在线冒烟：真实站点、真实分布——但不可复现（改版 / A-B / 反爬），
            基线一漂就没有度量意义，**因此只报告，绝不进回归门禁**。

纪律（都是核心任务文档里写过的）：

  - **只读**：只导航 + 快照 + 只读断言，不做任何改变对方状态的点击。
  - **失败分两类，不许混**：
      环境不可达（网络 / 反爬 / 改版跳转）——不是驱动的问题，如实标注；
      驱动行为（快照为空、期望元素缺失、盲区未报告）——这才是要看的。
  - **期望要抗漂**：只断言极稳定的东西（example.com 的链接是 RFC 示例页、
    wikipedia 必有搜索框这一类），其余只记录量测（元素数、截断、盲区），
    不做硬性通过/失败判定。

用法：.venv python online_smoke.py，结果落 online_smoke_report.json。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

_ROLE_TEXTBOX = "textbox"


@dataclass
class SmokeSite:
    id: str
    url: str
    # 只读期望：("link_name_contains", 子串) / ("has_role", 角色) /
    #           ("title_contains", 子串) / ("min_refs", 数量)
    expects: list[tuple[str, Any]] = field(default_factory=list)
    note: str = ""


SITES: list[SmokeSite] = [
    SmokeSite(
        "example_com", "https://example.com",
        [("title_contains", "Example Domain"),
         ("link_name_contains", "Learn more"),
         ("min_refs", 1)],
        note="RFC 2606 示例页。2026-08-30 实测其内容已漂移：链接文案由"
             "「More information...」变为「Learn more」——正是真实站点不可当"
             "门禁的实证，期望按当前内容更新",
    ),
    SmokeSite(
        "python_org", "https://www.python.org",
        [("link_name_contains", "Downloads"),
         ("title_contains", "Python"),
         ("min_refs", 10)],
        note="顶部导航十年未大改",
    ),
    SmokeSite(
        "zh_wikipedia", "https://zh.wikipedia.org",
        [("has_role", _ROLE_TEXTBOX),
         ("min_refs", 20)],
        note="首页，预期有搜索框；观察 iframe/模板复杂度",
    ),
    SmokeSite(
        "mdn", "https://developer.mozilla.org/en-US/",
        [("min_refs", 20)],
        note="MDN 首页（导航常改版，只量测不断言具体文案）",
    ),
    SmokeSite(
        "github", "https://github.com",
        [("min_refs", 10)],
        note="可能被反爬拦——拦截本身也是要记录的真实分布性质",
    ),
    SmokeSite(
        "gitee", "https://gitee.com",
        [("min_refs", 10)],
        note="国内站点对照",
    ),
    SmokeSite(
        "w3_org", "https://www.w3.org",
        [("min_refs", 5)],
        note="",
    ),
]


def _check_expect(snap: Any, title: str, kind: str, want: Any) -> tuple[bool, str]:
    if kind == "link_name_contains":
        hits = [r for r in snap.refs if str(want).lower() in (r.name or "").lower()]
        return bool(hits), f"名称含「{want}」的元素 {len(hits)} 个"
    if kind == "has_role":
        hits = [r for r in snap.refs if r.role == want]
        return bool(hits), f"role={want} 的元素 {len(hits)} 个"
    if kind == "title_contains":
        ok = str(want).lower() in (title or "").lower()
        return ok, f"标题「{title[:40]}」"
    if kind == "min_refs":
        return len(snap.refs) >= int(want), f"快照元素 {len(snap.refs)} 个（期望 ≥{want}）"
    return False, f"未知期望类型 {kind}"


async def run_site(session: Any, site: SmokeSite) -> dict:
    rec: dict = {"id": site.id, "url": site.url, "note": site.note}
    t0 = time.perf_counter()
    try:
        state = await session.navigate(site.url)
    except Exception as e:  # noqa: BLE001
        rec.update(kind="环境不可达", error=str(e)[:200])
        return rec
    if state.error:
        err = str(state.error)
        rec.update(kind="环境不可达" if ("net::" in err or "Navigation" in err) else "驱动失败",
                   error=err[:200])
        return rec

    try:
        snap = await session.snapshot_ref()
    except Exception as e:  # noqa: BLE001
        rec.update(kind="驱动失败", error=f"快照异常: {e}"[:200])
        return rec

    title = state.title or ""
    checks = []
    for kind, want in site.expects:
        ok, detail = _check_expect(snap, title, kind, want)
        checks.append({"expect": kind, "want": str(want), "ok": ok, "detail": detail})

    rec.update(
        kind="观察完成",
        title=title[:80],
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        refs=len(snap.refs),
        truncated=snap.truncated,
        total_on_page=snap.total_on_page,
        frames=len(snap.frames),
        frame_elements=snap.hidden_frame_count,
        canvas=snap.canvas,
        checks=checks,
        # 期望全过 ≠ "通过"（这不是门禁）；期望有缺口 = 值得人看一眼的信号
        all_expects_met=all(c["ok"] for c in checks) if checks else None,
    )
    return rec


async def main() -> dict:
    from fnixagent.core.tools.browser import BrowserSession

    session = BrowserSession()
    results: list[dict] = []
    try:
        for site in SITES:
            r = await run_site(session, site)
            results.append(r)
            kind = r.get("kind", "?")
            extra = ""
            if kind == "观察完成":
                unmet = [c for c in r["checks"] if not c["ok"]]
                extra = (f"refs={r['refs']} frames={r['frames']}"
                         f"{' 盲区未达预期:' + ';'.join(c['detail'] for c in unmet) if unmet else ''}")
            print(f"  [{kind}] {site.id:<12} {r.get('elapsed_ms', 0):>7.0f}ms {extra}"
                  f"{(' / ' + r.get('error', '')) if kind != '观察完成' else ''}",
                  flush=True)
        await session.close()
    except Exception:  # noqa: BLE001
        try:
            await session.close()
        except Exception:  # noqa: BLE001
            pass
        raise

    observed = [r for r in results if r.get("kind") == "观察完成"]
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "在线只读冒烟：发现性质，不做门禁（见文件头部纪律）",
        "total_sites": len(results),
        "observed": len(observed),
        "unreachable": sum(1 for r in results if r.get("kind") == "环境不可达"),
        "driver_failure": sum(1 for r in results if r.get("kind") == "驱动失败"),
        "sites_with_frames": sum(1 for r in observed if r.get("frames")),
        "sites_with_canvas": sum(1 for r in observed if int((r.get("canvas") or {}).get("count") or 0) > 0),
        "snapshots_truncated": sum(1 for r in observed if r.get("truncated")),
        "empty_snapshots": sum(1 for r in observed if r.get("refs") == 0),
        "sites": results,
    }
    out_path = HERE / "online_smoke_report.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n── 在线只读冒烟（只报告，不做门禁）──")
    print(f"  站点: {out['total_sites']}　观察完成: {out['observed']}　"
          f"环境不可达: {out['unreachable']}　驱动失败: {out['driver_failure']}")
    print(f"  含 iframe 的站点: {out['sites_with_frames']}　含 canvas: {out['sites_with_canvas']}　"
          f"快照被截断: {out['snapshots_truncated']}　空快照: {out['empty_snapshots']}")
    print(f"\n已写入 {out_path}")
    return out


if __name__ == "__main__":
    asyncio.run(main())
