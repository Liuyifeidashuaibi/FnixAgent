/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * First-run onboarding — BYOK → test → open folder.
 * Path A: download → key → workspace → Work/Code.
 */

import { useState } from "react";
import { CheckCircle2, FolderOpen, KeyRound, Loader2, X } from "lucide-react";
import { ensureFnixWorkspace, pingAgentd, syncHarnessConfig, testHarnessLlm } from "../../lib/fnixBridge";
import { LOCAL_LLM } from "./localLlm";

const STORAGE_KEY = "fnix.onboarding.done";

export function isOnboardingDone(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return true;
  }
}

export function markOnboardingDone(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* ignore */
  }
}

interface Props {
  initialKey?: string;
  initialModel?: string;
  initialBaseUrl?: string;
  projectPath?: string;
  onPickFolder: () => Promise<string | null>;
  onComplete: (result: {
    apiKey: string;
    model: string;
    baseUrl: string;
    projectPath: string;
  }) => void;
  onSkip: () => void;
}

type Step = 1 | 2 | 3;

export function OnboardingWizard({
  initialKey = "",
  initialModel = LOCAL_LLM.model,
  initialBaseUrl = LOCAL_LLM.baseUrl,
  projectPath = "",
  onPickFolder,
  onComplete,
  onSkip,
}: Props) {
  const [step, setStep] = useState<Step>(1);
  const [apiKey, setApiKey] = useState(initialKey);
  const [model, setModel] = useState(initialModel || LOCAL_LLM.model);
  const [baseUrl, setBaseUrl] = useState(initialBaseUrl || LOCAL_LLM.baseUrl);
  const [folder, setFolder] = useState(projectPath);
  const [testing, setTesting] = useState(false);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [agentdOk, setAgentdOk] = useState<boolean | null>(null);
  const [testPreview, setTestPreview] = useState<string | null>(null);
  const [skipWarning, setSkipWarning] = useState<string | null>(null);

  const runTest = async () => {
    setTesting(true);
    setTestOk(null);
    setToast(null);
    setTestPreview(null);
    try {
      const alive = await pingAgentd();
      setAgentdOk(alive);
      if (!alive) {
        setTestOk(false);
        setToast("本地服务正在启动中，请稍候重试测试连接");
        return;
      }
      if (!apiKey.trim()) {
        setTestOk(false);
        setToast("请填写 API Key");
        return;
      }
      const res = await testHarnessLlm({
        provider: LOCAL_LLM.provider,
        model: model.trim() || LOCAL_LLM.model,
        base_url: baseUrl.trim() || LOCAL_LLM.baseUrl,
        api_key: apiKey.trim(),
      });
      setTestOk(res.ok);
      setToast(res.ok ? "连接成功" : res.error || "连接失败");
      if (res.ok) {
        const preview = (res.preview || "").trim();
        if (preview) {
          // 前 50 字预览，让用户确认 Key 真的能用
          setTestPreview(preview.slice(0, 50));
        }
        await syncHarnessConfig({
          provider: LOCAL_LLM.provider,
          model: model.trim() || LOCAL_LLM.model,
          base_url: baseUrl.trim() || LOCAL_LLM.baseUrl,
          api_key: apiKey.trim(),
        });
      }
    } catch (e) {
      setTestOk(false);
      setToast(`测试失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTesting(false);
    }
  };

  const pick = async () => {
    const path = await onPickFolder();
    if (path) {
      setFolder(path);
      await ensureFnixWorkspace(path);
    }
  };

  const finish = () => {
    markOnboardingDone();
    onComplete({
      apiKey: apiKey.trim(),
      model: model.trim() || LOCAL_LLM.model,
      baseUrl: baseUrl.trim() || LOCAL_LLM.baseUrl,
      projectPath: folder,
    });
  };

  // 跳过守门：必须至少有 API Key 或文件夹其一才能跳过
  const skipWithGuard = () => {
    const hasKey = Boolean(apiKey.trim());
    const hasFolder = Boolean(folder.trim());
    if (!hasKey && !hasFolder) {
      setSkipWarning("请至少填写 API Key 或选择文件夹");
      return;
    }
    markOnboardingDone();
    onSkip();
  };

  return (
    <div className="fnix-onboard-root" role="dialog" aria-label="欢迎使用 Fnix">
      <div className="fnix-onboard-card">
        <header className="fnix-onboard-head">
          <div>
            <h1>欢迎使用 Fnix</h1>
            <p>填自己的 API Key → 选文件夹 → 开始 Work / Code</p>
          </div>
          <button type="button" className="fnix-ibtn" onClick={skipWithGuard} aria-label="跳过">
            <X size={18} />
          </button>
        </header>

        {skipWarning ? (
          <div className="fnix-onboard-toast bad" role="alert">
            {skipWarning}
          </div>
        ) : null}

        <div className="fnix-onboard-progress" aria-hidden="true">
          <div
            className="fnix-onboard-progress-fill"
            style={{ width: `${(step / 3) * 100}%` }}
          />
        </div>

        <div className="fnix-onboard-steps">
          {[1, 2, 3].map((n) => (
            <span key={n} className={`fnix-onboard-dot${step === n ? " on" : step > n ? " done" : ""}`}>
              {n}
            </span>
          ))}
        </div>

        {step === 1 && (
          <section className="fnix-onboard-body">
            <h2>
              <KeyRound size={18} /> API Key
            </h2>
            <p className="fnix-onboard-hint">Key 只保存在你的本机，不会上传到云端。</p>
            <label className="fnix-field">
              <span>DashScope / OpenAI-compatible Key</span>
              <input
                type="password"
                value={apiKey}
                placeholder="sk-…"
                onChange={(e) => setApiKey(e.target.value)}
              />
            </label>
            <label className="fnix-field">
              <span>Model</span>
              <input value={model} onChange={(e) => setModel(e.target.value)} />
            </label>
            <details className="fnix-advanced">
              <summary>高级</summary>
              <label className="fnix-field">
                <span>Base URL</span>
                <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
              </label>
            </details>
            {toast && <div className={`fnix-onboard-toast${testOk === false ? " bad" : ""}`}>{toast}</div>}
            {testPreview && (
              <div className="fnix-onboard-preview" title="前 50 字预览，确认 Key 可用">
                预览：{testPreview}
              </div>
            )}
            <div className="fnix-onboard-actions">
              <button type="button" className="fnix-set-save ghost" disabled={testing} onClick={() => void runTest()}>
                {testing ? <Loader2 size={14} className="spin" /> : null}
                测试连接
              </button>
              <button
                type="button"
                className="fnix-set-save"
                disabled={!apiKey.trim() || testOk === false}
                onClick={() => setStep(2)}
              >
                {testOk ? <CheckCircle2 size={14} /> : null}
                下一步
              </button>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="fnix-onboard-body">
            <h2>
              <FolderOpen size={18} /> 工作区
            </h2>
            <p className="fnix-onboard-hint">选一个本地文件夹作为项目根目录（Code 需要；Work 也可交付到此）。</p>
            <div className="fnix-info-card">
              <b>当前路径</b>
              <span>{folder || "尚未选择"}</span>
            </div>
            <div className="fnix-onboard-actions">
              <button type="button" className="fnix-set-save ghost" onClick={() => setStep(1)}>
                上一步
              </button>
              <button type="button" className="fnix-set-save ghost" onClick={() => void pick()}>
                <FolderOpen size={14} />
                选择文件夹
              </button>
              <button type="button" className="fnix-set-save" onClick={() => setStep(3)}>
                {folder ? "下一步" : "跳过（稍后选择）"}
              </button>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="fnix-onboard-body">
            <h2>
              <CheckCircle2 size={18} /> 可以开始了
            </h2>
            <ul className="fnix-onboard-list">
              <li>
                <b>Work</b>：Ask / Plan / Craft — 办公与轻量交付
              </li>
              <li>
                <b>Code</b>：Preview → Accept — 工程改动审完再写盘
              </li>
              <li>
                Composer 输入 <code>/benchmark</code> 可跑全链路自检
              </li>
            </ul>
            <div className="fnix-onboard-actions">
              <button type="button" className="fnix-set-save ghost" onClick={() => setStep(2)}>
                上一步
              </button>
              <button type="button" className="fnix-set-save" onClick={finish}>
                进入 Fnix
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
