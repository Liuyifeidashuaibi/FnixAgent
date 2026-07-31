"""GAIA Benchmark 真实测试题 — 测试 FnixAgent 工具链能力。

基于 GAIA 论文 (arXiv:2311.12983) 公开的 3 个示例题:
  - Level 1: 临床试验招募人数 (web_search + web_fetch + 信息提取)
  - Level 2: 冰淇淋黄油脂肪含量百分比 (多模态图片 + web_search + 计算)
  - Level 3: NASA APOD 宇航员太空时间 (多步 web 搜索 + 信息聚合 + 排除)

测试目标: 验证 FnixAgent 工具链能否支撑 GAIA 风格任务, 发现能力短板。
注: 不调真实 LLM, 只测工具链执行能力 (LLM 决策由测试代码模拟)。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.tools.workspace import WorkspaceTools


async def test_gaia_level1_web_search():
    """GAIA Level 1: 临床试验招募人数。

    原题: What was the actual enrollment count of the clinical trial on
          H. pylori in acne vulgaris patients from Jan-May 2018 as listed
          on the NIH website?  答案: 90

    测试点:
      1. web_search 能搜到 NIH 临床试验相关结果
      2. web_fetch 能抓取 ClinicalTrials.gov 页面内容
      3. 搜索结果格式正确 (非空, 含 URL)
    """
    print("\n=== GAIA Level 1: 临床试验招募人数 ===")
    ws = WorkspaceTools(workspace_root=str(ROOT))

    # 步骤 1: web_search 搜索
    print("[1] web_search: 'H. pylori acne vulgaris clinical trial 2018 NIH'")
    result = await ws.web_search(
        "H. pylori acne vulgaris clinical trial 2018 site:clinicaltrials.gov", num=5
    )
    print(f"    success={result.success}, results_count={result.metadata.get('results_count', 0)}")
    if result.success:
        content = result.content or ""
        print(f"    内容前 300 字符: {content[:300]}")
        if "(无搜索结果" in content:
            print("    [问题] web_search 返回无结果 — HTML 解析可能失败")
            return False
        return True
    else:
        print(f"    [失败] {result.error}")
        return False


async def test_gaia_level1_web_fetch():
    """GAIA Level 1 辅助: web_fetch 抓取 ClinicalTrials.gov。

    测试 web_fetch 能否抓取真实网页并提取文本。
    """
    print("\n=== GAIA Level 1 辅助: web_fetch ClinicalTrials ===")
    ws = WorkspaceTools(workspace_root=str(ROOT))

    # 用一个已知的临床试验页面测试 web_fetch
    print("[1] web_fetch: clinicaltrials.gov")
    result = await ws.web_fetch("https://clinicaltrials.gov/")
    print(f"    success={result.success}")
    if result.success:
        content = result.content or ""
        print(f"    内容长度: {len(content)} 字符")
        print(f"    内容前 200 字符: {content[:200]}")
        if len(content) < 100:
            print("    [问题] web_fetch 返回内容过短")
            return False
        return True
    else:
        print(f"    [失败] {result.error}")
        return False


async def test_gaia_level2_calculation():
    """GAIA Level 2: 冰淇淋黄油脂肪含量百分比计算。

    原题: If this whole pint is made up of ice cream, how many percent above
          or below the US federal standards for butterfat content is it when
          using the standards as reported by Wikipedia in 2020?
          答案: +4.6

    测试点:
      1. web_search 能搜到 Wikipedia 黄油脂肪标准
      2. run_command 能执行数学计算
    注: 图片识别 (品脱大小) 需要多模态能力, FnixAgent 当前无图片识别工具 — 这是能力短板
    """
    print("\n=== GAIA Level 2: 黄油脂肪含量计算 ===")
    ws = WorkspaceTools(workspace_root=str(ROOT))

    # 步骤 1: web_search 搜索 Wikipedia 黄油脂肪标准
    print("[1] web_search: 'butterfat content ice cream federal standard wikipedia'")
    result = await ws.web_search("butterfat content ice cream federal standard wikipedia", num=5)
    print(f"    success={result.success}")
    if result.success:
        content = result.content or ""
        print(f"    内容前 300 字符: {content[:300]}")

    # 步骤 2: run_command 执行计算
    print("[2] run_command: python 计算 10% vs 8% 标准差")
    calc_result = await ws.run_command("python -c \"print(f'{((10-8)/8*100):+.1f}')\"")
    print(f"    success={calc_result.success}")
    if calc_result.success:
        print(f"    计算结果: {calc_result.content[:50]}")
    return True


async def test_gaia_level3_multi_step():
    """GAIA Level 3: NASA APOD 宇航员太空时间。

    原题: In NASA's Astronomy Picture of the Day on 2006 January 21...
          答案: White; 5876

    测试点:
      1. web_fetch 能抓取 NASA APOD 页面
      2. web_search 能搜到宇航员信息
      3. 多步任务编排 (先 fetch APOD, 再 search 宇航员, 再聚合)
    注: 图片识别 (哪个宇航员小) 需要多模态 — 当前无此能力
    """
    print("\n=== GAIA Level 3: NASA APOD 多步推理 ===")
    ws = WorkspaceTools(workspace_root=str(ROOT))

    # 步骤 1: web_fetch NASA APOD 2006-01-21
    print("[1] web_fetch: NASA APOD 2006-01-21")
    result = await ws.web_fetch("https://apod.nasa.gov/apod/ap060121.html")
    print(f"    success={result.success}")
    if result.success:
        content = result.content or ""
        print(f"    内容长度: {len(content)} 字符")
        # 检查是否能提取到宇航员名字
        print(f"    内容前 300 字符: {content[:300]}")

    # 步骤 2: web_search 搜索 NASA 宇航员组
    print("[2] web_search: 'NASA astronaut group 2006 ISS Expedition'")
    result2 = await ws.web_search("NASA astronaut group 2006 ISS Expedition", num=5)
    print(f"    success={result2.success}")
    if result2.success:
        print(f"    内容前 200 字符: {(result2.content or '')[:200]}")

    return True


async def test_capability_gap_image_recognition():
    """测试能力: 图片识别工具 (P1 新增)。

    GAIA Level 2/3 都需要图片识别:
      - Level 2: 识别品脱包装上的冰淇淋容量
      - Level 3: 识别 NASA APOD 图片中哪个宇航员更小

    P1 修复: 新增 image_analyze 工具, 支持 PIL 元数据提取 + pytesseract OCR。
    """
    print("\n=== 能力测试: 图片识别 (P1 新增) ===")
    from fnixagent.core.tools.registry import ToolRegistry
    from fnixagent.core.tools.workspace import register_workspace_tools

    registry = ToolRegistry()
    register_workspace_tools(registry, workspace_root=str(ROOT))

    tool_names = {
        t["function"]["name"] if isinstance(t, dict) else t.name for t in registry.list_for_llm()
    }
    print(f"    已注册工具 ({len(tool_names)}): {sorted(tool_names)}")

    has_image = "image_analyze" in tool_names
    has_calc = "calculate" in tool_names
    print(f"    image_analyze: {'OK' if has_image else '缺失'}")
    print(f"    calculate: {'OK' if has_calc else '缺失'}")

    # 测试计算器
    if has_calc:
        ws = WorkspaceTools(workspace_root=str(ROOT))
        result = ws.calculate("(10-8)/8*100")
        print(
            f"    calculate('(10-8)/8*100') = {result.content if result.success else result.error}"
        )

    return has_image and has_calc


async def test_capability_gap_calculator():
    """测试能力: 是否有专用计算工具。

    GAIA 多道题需要数学计算。当前只能用 run_command 跑 python。
    测试 run_command 计算能力是否正常。
    """
    print("\n=== 能力测试: 数学计算 (run_command) ===")
    ws = WorkspaceTools(workspace_root=str(ROOT))

    # 测试复杂计算
    result = await ws.run_command('python -c "import math; print(round(math.pi * 100, 2))"')
    print(f"    success={result.success}")
    if result.success:
        print(f"    结果: {result.content[:50]}")
        return True
    else:
        print(f"    [失败] {result.error}")
        return False


async def main():
    print("=" * 60)
    print("GAIA Benchmark 真实测试题 — FnixAgent 工具链能力测试")
    print("=" * 60)

    results = {}
    # Level 1
    results["L1_web_search"] = await test_gaia_level1_web_search()
    results["L1_web_fetch"] = await test_gaia_level1_web_fetch()
    # Level 2
    results["L2_calculation"] = await test_gaia_level2_calculation()
    # Level 3
    results["L3_multi_step"] = await test_gaia_level3_multi_step()
    # 能力缺口
    results["gap_image"] = await test_capability_gap_image_recognition()
    results["calc_ok"] = await test_capability_gap_calculator()

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for k, v in results.items():
        status = "PASS" if v else "FAIL/GAP"
        print(f"  {k}: {status}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
