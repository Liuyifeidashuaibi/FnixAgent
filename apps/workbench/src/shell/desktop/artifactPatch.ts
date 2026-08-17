/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Spec 3: Artifact 增量编辑 (diff-apply)
 * ============================================================
 * 对标:
 *   - e2b-dev/fragments 的 Morph Apply 集成
 *   - 语义 diff + 代码应用
 *   - Aider 的 SEARCH/REPLACE block 格式
 *
 * 设计:
 *   - 不引入 Yjs(协同编辑复杂度过高,与本地优先原则冲突)
 *   - 不引入 OT(需要中心化服务器)
 *   - 使用 SEARCH/REPLACE block 格式 — LLM 友好,可审计,可回滚
 *   - 本地 diff-match-patch 做字符级 diff 用于"显示变更"
 *
 * SEARCH/REPLACE 格式:
 *   <<<<<<< SEARCH
 *   原始代码片段(必须精确匹配文件中某处)
 *   =======
 *   替换后的代码
 *   >>>>>>> REPLACE
 *
 *   多个 block 之间用空行分隔。
 *
 * 用例:
 *   const patches = parseSearchReplace(rawPatchText);
 *   const result = applyPatches(originalContent, patches);
 *   if (result.ok) save(result.content);
 *   else showError(result.errors);
 */

export interface SearchReplaceBlock {
  search: string;
  replace: string;
}

export interface ApplyResult {
  ok: boolean;
  content: string;
  /** 每个 block 的应用结果 */
  results: Array<{
    applied: boolean;
    error?: string;
    /** 应用后该 block 的字符级 diff(用于光标闪烁动画) */
    diffRanges?: Array<{ start: number; end: number }>;
  }>;
}

const SEARCH_START = "<<<<<<< SEARCH";
const DIVIDER = "=======";
const REPLACE_END = ">>>>>>> REPLACE";

/**
 * 解析 SEARCH/REPLACE 文本为结构化 block 数组
 *
 * 容错:
 *   - 允许 SEARCH/REPLACE 前后有空格
 *   - 允许 block 之间任意空行
 *   - 不区分大小写
 *   - 末尾无换行也接受
 */
export function parseSearchReplace(raw: string): SearchReplaceBlock[] {
  const lines = raw.split("\n");
  const blocks: SearchReplaceBlock[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().toUpperCase().startsWith(SEARCH_START.toUpperCase())) {
      const search: string[] = [];
      const replace: string[] = [];
      i++;
      // 收集 SEARCH 段
      while (i < lines.length && !lines[i].trim().startsWith(DIVIDER)) {
        search.push(lines[i]);
        i++;
      }
      if (i >= lines.length) {
        // 残缺:只有 SEARCH 没 DIVIDER
        break;
      }
      i++; // 跳过 DIVIDER
      // 收集 REPLACE 段
      while (i < lines.length && !lines[i].trim().toUpperCase().startsWith(REPLACE_END.toUpperCase())) {
        replace.push(lines[i]);
        i++;
      }
      if (i >= lines.length) {
        break;
      }
      i++; // 跳过 REPLACE_END
      blocks.push({
        search: search.join("\n").replace(/\n$/, ""),
        replace: replace.join("\n").replace(/\n$/, ""),
      });
    } else {
      i++;
    }
  }
  return blocks;
}

/**
 * 应用 patches 到原文本
 *
 * 策略:
 *   1. 每个 block 按 SEARCH 精确匹配,找到第一个匹配位置
 *   2. 替换为 REPLACE 内容
 *   3. 记录变更位置,供前端做光标闪烁
 *   4. 任一 block 失败不阻断其他 block,返回完整 results 数组
 */
export function applyPatches(original: string, blocks: SearchReplaceBlock[]): ApplyResult {
  let content = original;
  const results: ApplyResult["results"] = [];
  let allOk = true;
  let offset = 0; // 累计偏移量,因为前一次替换会改变后续 index

  for (const block of blocks) {
    if (!block.search) {
      results.push({ applied: false, error: "空 SEARCH 段" });
      allOk = false;
      continue;
    }
    const idx = content.indexOf(block.search);
    if (idx < 0) {
      results.push({
        applied: false,
        error: "SEARCH 段未在原文本中找到精确匹配",
      });
      allOk = false;
      continue;
    }
    const before = content.slice(0, idx);
    const after = content.slice(idx + block.search.length);
    content = before + block.replace + after;
    // 记录 REPLACE 段在最终文本中的范围(供前端高亮)
    const start = offset + before.length;
    const end = start + block.replace.length;
    results.push({
      applied: true,
      diffRanges: [{ start, end }],
    });
    offset += block.replace.length - block.search.length;
  }

  return {
    ok: allOk,
    content,
    results,
  };
}

/**
 * 生成简易"统一 diff" 文本(用于在 UI 显示变更预览)
 *
 * 实现:基于逐行对比(不做 LCS 优化,简单可读)
 * 大文件场景请用 react-diff-viewer
 */
export function generateUnifiedDiff(original: string, patched: string): string {
  const oldLines = original.split("\n");
  const newLines = patched.split("\n");
  const maxLen = Math.max(oldLines.length, newLines.length);
  const out: string[] = [];
  for (let i = 0; i < maxLen; i++) {
    const o = oldLines[i];
    const n = newLines[i];
    if (o === n) {
      if (o !== undefined) out.push(` ${o}`);
    } else {
      if (o !== undefined) out.push(`-${o}`);
      if (n !== undefined) out.push(`+${n}`);
    }
  }
  return out.join("\n");
}

/**
 * 校验 patch 是否能完全应用(不实际应用)
 *
 * 用例:LLM 生成 patch 后,前端先校验,通过再提示用户确认
 */
export function validatePatch(original: string, raw: string): {
  ok: boolean;
  blocks: SearchReplaceBlock[];
  errors: string[];
} {
  const blocks = parseSearchReplace(raw);
  const errors: string[] = [];
  if (blocks.length === 0) {
    errors.push("未找到任何 SEARCH/REPLACE block");
  }
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (!b.search) {
      errors.push(`block #${i + 1}: SEARCH 段为空`);
      continue;
    }
    if (!original.includes(b.search)) {
      errors.push(`block #${i + 1}: SEARCH 段未在原文本中找到精确匹配`);
    }
  }
  return {
    ok: errors.length === 0,
    blocks,
    errors,
  };
}
