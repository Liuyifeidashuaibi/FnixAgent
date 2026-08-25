/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * 全链路真实测试 — 浏览器 UI → agentd → 真实 LLM → 工作区产物 → 确定性判定。
 *
 * 测试题取自项目内专业基准 benchmarks/forge/suites/core（选取 4 题代表四类能力：
 * 指令遵循 / 代码生成 / 精确编辑 / 中文语义），判定复用 Forge 的确定性检查语义
 * （file_equals / contains / command_succeeds），无 LLM 裁判。
 *
 * 运行（需 .env 配有真实 API Key）:
 *   $env:FNIX_E2E_WORKSPACE="..."; npx playwright test --config=playwright.fullchain.config.ts
 */

import { test, expect } from '@playwright/test';
import { electronMock } from './electron-mock';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const WORKSPACE = process.env.FNIX_E2E_WORKSPACE || path.join(process.cwd(), '.tmp', 'fullchain-ws');
if (!existsSync(WORKSPACE)) mkdirSync(WORKSPACE, { recursive: true });

/** 单题定义：setup 预置文件 + prompt + 确定性判定 */
interface Case {
  id: string;
  setup?: Record<string, string>;
  prompt: string;
  /** 流式结束后必须存在的产物文件（作为完成硬信号） */
  awaitFile?: string;
  /** 或：轮询等待某文件内容包含指定文本（编辑类任务的完成信号） */
  awaitContains?: { file: string; text: string };
  verify: Array<
    | { kind: 'file_equals'; file: string; content: string }
    | { kind: 'contains'; file: string; text: string }
    | { kind: 'not_contains'; file: string; text: string }
    | { kind: 'python'; code: string; stdoutPattern?: string }
  >;
}

const CASES: Case[] = [
  {
    id: 'inst-002_字符串变换',
    prompt:
      '把字符串 fnix-forge-rocks 转换成全大写，并用连字符替换下划线（若有），结果写入当前目录的 shout.txt，文件中只包含转换结果这一行，不要加引号或说明。',
    awaitFile: 'shout.txt',
    verify: [{ kind: 'file_equals', file: 'shout.txt', content: 'FNIX-FORGE-ROCKS' }],
  },
  {
    id: 'code-001_fib生成',
    prompt:
      '在当前目录创建 fib.py，定义函数 fib(n)：返回第 n 个斐波那契数（fib(0)=0, fib(1)=1）。只创建这一个文件。',
    awaitFile: 'fib.py',
    verify: [
      {
        kind: 'python',
        code: 'from fib import fib; assert fib(0)==0 and fib(1)==1 and fib(10)==55 and fib(20)==6765',
      },
    ],
  },
  {
    id: 'edit-001_最小化配置编辑',
    setup: {
      'config.ini': '[server]\nhost = 0.0.0.0\nport = 8080\nmode = debug\nworkers = 4\n',
    },
    prompt: '当前目录有 config.ini，把其中的 mode 从 debug 改为 release，其余内容一字不动。',
    awaitContains: { file: 'config.ini', text: 'mode = release' },
    verify: [
      { kind: 'contains', file: 'config.ini', text: 'mode = release' },
      { kind: 'not_contains', file: 'config.ini', text: 'mode = debug' },
      { kind: 'contains', file: 'config.ini', text: 'workers = 4' },
    ],
  },
  {
    id: 'lang-001_中文精确落盘',
    prompt:
      '新建 greeting.txt，内容写：你好，世界。注意：不要带句号，不要带引号，文件里就这六个字符。',
    awaitFile: 'greeting.txt',
    verify: [{ kind: 'file_equals', file: 'greeting.txt', content: '你好，世界' }],
  },
];

function resetWorkspace(): void {
  for (const e of existsSync(WORKSPACE) ? require('node:fs').readdirSync(WORKSPACE) : []) {
    rmSync(path.join(WORKSPACE, String(e)), { recursive: true, force: true });
  }
}

function waitForFile(rel: string, timeoutMs = 300_000): string {
  const full = path.join(WORKSPACE, rel);
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (existsSync(full) && existsSync(path.join(WORKSPACE, '.fnix'))) {
      // 再等一拍让写盘稳定
      const size1 = require('node:fs').statSync(full).size;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 1500);
      const size2 = existsSync(full) ? require('node:fs').statSync(full).size : -1;
      if (size1 === size2) return full;
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 1500);
  }
  throw new Error(`等待产物超时: ${rel}`);
}

function runChecks(c: Case): string[] {
  const failures: string[] = [];
  for (const v of c.verify) {
    if (v.kind === 'file_equals') {
      const p = path.join(WORKSPACE, v.file);
      const got = existsSync(p) ? readText(p).replace(/\r/g, '').replace(/\n+$/, '') : '<missing>';
      if (got !== v.content.replace(/\n+$/, '')) failures.push(`${v.file} 内容不符: got=${got.slice(0, 60)}`);
    } else if (v.kind === 'contains') {
      const p = path.join(WORKSPACE, v.file);
      const got = existsSync(p) ? readText(p) : '';
      if (!got.includes(v.text)) failures.push(`${v.file} 缺少: ${v.text}`);
    } else if (v.kind === 'not_contains') {
      const p = path.join(WORKSPACE, v.file);
      const got = existsSync(p) ? readText(p) : '';
      if (got.includes(v.text)) failures.push(`${v.file} 不应包含: ${v.text}`);
    } else if (v.kind === 'python') {
      const r = spawnSync(process.platform === 'win32' ? 'python' : 'python3', ['-c', v.code], {
        cwd: WORKSPACE,
        encoding: 'utf8',
        timeout: 30_000,
      });
      if (r.status !== 0) {
        failures.push(`python 校验失败: ${(r.stderr || r.stdout || '').slice(0, 160)}`);
      } else if (v.stdoutPattern && !(r.stdout || '').includes(v.stdoutPattern)) {
        failures.push(`stdout 未匹配: ${v.stdoutPattern}`);
      }
    }
  }
  return failures;
}

function readText(p: string): string {
  return require('node:fs').readFileSync(p, 'utf8');
}

test.describe('全链路真实任务(Forge 专业测试题抽样)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(electronMock);
    await page.addInitScript(() => {
      try {
        localStorage.setItem('fnix.onboarding.done', '1');
      } catch {
        /* ignore */
      }
    });
    resetWorkspace();
  });

  for (const c of CASES) {
    test(`全链路: ${c.id}`, async ({ page }) => {
      if (c.setup) {
        for (const [f, content] of Object.entries(c.setup)) {
          const p = path.join(WORKSPACE, f);
          mkdirSync(path.dirname(p), { recursive: true });
          writeFileSync(p, content, 'utf8');
        }
      }

      await page.goto('/');
      const composer = page.getByPlaceholder(/描述要构建|输入你的问题|提问/).first();
      await expect(composer).toBeVisible({ timeout: 20_000 });
      await expect(composer).toBeEnabled();

      await composer.fill(c.prompt);
      const sendBtn = page.getByRole('button', { name: /发送/ }).first();
      if (await sendBtn.isEnabled().catch(() => false)) {
        await sendBtn.click();
      } else {
        await composer.press('Enter');
      }

      // 流式开始：优先观察停止按钮；个别主题下为 SVG 图标，观察不到则跳过（产物落盘才是硬门槛）
      try {
        await expect(page.locator('button').filter({ hasText: /■|停止/ }).first()).toBeVisible({
          timeout: 15_000,
        });
      } catch {
        console.log('[fullchain] 停止按钮未捕获(非阻塞)');
      }

      // 完成硬信号：awaitFile 存在 / awaitContains 内容出现（真实 LLM 执行期，最长 5 分钟）
      try {
        if (c.awaitFile)
          await expect
            .poll(() => existsSync(path.join(WORKSPACE, c.awaitFile!)), { timeout: 300_000, intervals: [2_000] })
            .toBe(true);
        if (c.awaitContains)
          await expect
            .poll(
              () => {
                const p = path.join(WORKSPACE, c.awaitContains!.file);
                return existsSync(p) ? readText(p).includes(c.awaitContains!.text) : false;
              },
              { timeout: 300_000, intervals: [2_000] }
            )
            .toBe(true);
      } catch (e) {
        const mainText = await page.locator('main').innerText().catch(() => '');
        throw new Error(
          `${c.id} 产物未落盘。\n--- 页面尾部内容 ---\n${mainText.slice(-1200)}\n--- 原始错误 ---\n${String(e)}`
        );
      }

      // 会话回到空闲态（composer 可再次输入）
      await expect(composer).toBeEnabled({ timeout: 120_000 });

      // 确定性判定（Forge 同款语义）
      const failures = runChecks(c);

      if (failures.length) {
        const mainText = await page.locator('main').innerText().catch(() => '');
        throw new Error(
          `${c.id} 判定失败:\n${failures.join('\n')}\n--- 页面尾部内容 ---\n${mainText.slice(-800)}`
        );
      }
    });
  }
});
