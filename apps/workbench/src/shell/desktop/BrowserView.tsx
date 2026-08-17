/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * BrowserView — HTML 成果浏览器（右侧工作台 · 浏览器）
 * ============================================================
 * 以"终端用户"视角体验 HTML 成果。与画布分工：
 *   - 画布 = 审视 / 编辑（源码 / 双视图 / AI 改）
 *   - 浏览器 = 体验（地址栏 / 刷新 / 响应式设备宽度 / 新窗口）
 *
 * 安全：复用 ArtifactCanvas 的沙箱模式 —— iframe sandbox="allow-scripts"
 *       （不给 allow-same-origin）+ 注入 CSP（connect-src 'none'）。
 *
 * 交互：
 *   - 地址 pill 点击展开 HTML 产物列表；默认跟随最新产物，手动选择后保持
 *   - 设备宽度：桌面 100% / 平板 768 / 手机 390，验证响应式
 *   - 刷新 / 新窗口打开
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ExternalLink,
  Globe,
  Loader2,
  Monitor,
  RotateCw,
  Smartphone,
  Tablet,
} from "lucide-react";
import { authHeaders } from "../../lib/fnixBridge";
import type { ArtifactContent } from "./ArtifactCanvas";
import type { ArtifactRef } from "./useChatFlow";

interface Props {
  artifacts: ArtifactRef[];
  apiBase: string;
}

type Device = "desktop" | "tablet" | "mobile";
const DEVICE_W: Record<Device, string> = { desktop: "100%", tablet: "768px", mobile: "390px" };
const DEVICES: { id: Device; icon: typeof Monitor; label: string }[] = [
  { id: "desktop", icon: Monitor, label: "桌面" },
  { id: "tablet", icon: Tablet, label: "平板" },
  { id: "mobile", icon: Smartphone, label: "手机" },
];

/** 注入 CSP（无 <head> 时前置补一个），与 ArtifactCanvas 保持一致 */
function withCsp(html: string): string {
  const csp =
    `<meta http-equiv="Content-Security-Policy" content="default-src 'unsafe-inline' 'unsafe-eval' data:; img-src 'unsafe-inline' data: https:; connect-src 'none';"></meta>`;
  return /<head>/i.test(html) ? html.replace(/<head>/i, `<head>${csp}`) : csp + html;
}

export function BrowserView({ artifacts, apiBase }: Props) {
  const htmlArts = useMemo(() => artifacts.filter((a) => /\.html?$/i.test(a.path)), [artifacts]);

  const latest = useMemo(
    () =>
      htmlArts.reduce<ArtifactRef | null>(
        (best, a) => (!best || (a.createdAt ?? 0) > (best.createdAt ?? 0) ? a : best),
        null,
      ),
    [htmlArts],
  );

  const [pickedPath, setPickedPath] = useState<string | null>(null);
  const [device, setDevice] = useState<Device>("desktop");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  /** 加载结果（带 path，避免切换产物时旧数据串台）*/
  const [load, setLoad] = useState<{ path: string; data: ArtifactContent | null; error: string | null } | null>(null);

  // 选择：优先用户手动所选（仍有效时），否则跟随最新 HTML 产物
  const selectedPath =
    pickedPath && htmlArts.some((a) => a.path === pickedPath) ? pickedPath : latest?.path ?? null;

  const selected = useMemo(
    () => htmlArts.find((a) => a.path === selectedPath) ?? null,
    [htmlArts, selectedPath],
  );

  // 加载产物内容：仅在异步回调里 setLoad，结果与 path 绑定
  useEffect(() => {
    if (!selectedPath) return;
    let cancelled = false;
    void (async () => {
      try {
        const url = `${apiBase}/api/v1/work/artifacts/read?path=${encodeURIComponent(selectedPath)}`;
        const resp = await fetch(url, { headers: authHeaders() });
        const json = (await resp.json()) as ArtifactContent;
        if (cancelled) return;
        setLoad(
          json.ok
            ? { path: selectedPath, data: json, error: null }
            : { path: selectedPath, data: null, error: json.error || "加载失败" },
        );
      } catch (e) {
        if (!cancelled) setLoad({ path: selectedPath, data: null, error: String(e) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedPath, apiBase, reloadKey]);

  const current = load && load.path === selectedPath ? load : null;
  const loading = !!selectedPath && !current;
  const data = current?.data ?? null;
  const error = current?.error ?? null;

  const srcDoc = useMemo(
    () => (data && data.is_html ? withCsp(data.content) : ""),
    [data],
  );

  const pick = useCallback((path: string) => {
    setPickedPath(path);
    setPickerOpen(false);
  }, []);

  const openNewWindow = useCallback(() => {
    if (!data) return;
    const blob = new Blob([data.content], { type: "text/html" });
    window.open(URL.createObjectURL(blob), "_blank", "noopener");
  }, [data]);

  /** 刷新：清空当前结果（触发 loading）并重新加载 */
  const reload = useCallback(() => {
    setLoad(null);
    setReloadKey((k) => k + 1);
  }, []);

  return (
    <div className="fnx-browser">
      <div className="fnx-browser-bar">
        <Globe size={14} className="fnx-browser-globe" />
        <div className="fnx-browser-addrwrap">
          <button
            type="button"
            className="fnx-browser-addr"
            onClick={() => setPickerOpen((o) => !o)}
            title="选择 HTML 产物"
            disabled={htmlArts.length === 0}
          >
            <span className="fnx-browser-addr-name">{selected?.name ?? "未选择产物"}</span>
            {selected ? <span className="fnx-browser-addr-path">{selected.path}</span> : null}
            <ChevronDown size={12} />
          </button>
          {pickerOpen && htmlArts.length > 0 ? (
            <>
              <div className="fnx-browser-backdrop" role="button" tabIndex={-1} aria-label="关闭下拉" onClick={() => setPickerOpen(false)} onKeyDown={(e) => { if (e.key === "Escape") setPickerOpen(false); }} />
              <div className="fnx-browser-menu" role="listbox" aria-label="HTML 产物">
                {htmlArts.map((a) => (
                  <button
                    key={a.path}
                    type="button"
                    role="option"
                    aria-selected={a.path === selectedPath}
                    className={`fnx-browser-menu-item${a.path === selectedPath ? " on" : ""}`}
                    onClick={() => pick(a.path)}
                  >
                    <Globe size={12} />
                    <span>{a.name ?? a.path}</span>
                  </button>
                ))}
              </div>
            </>
          ) : null}
        </div>
        <button
          type="button"
          className="fnix-ibtn sm"
          title="刷新"
          onClick={reload}
          disabled={!selected}
        >
          <RotateCw size={13} />
        </button>
        <div className="fnx-browser-dev" role="tablist" aria-label="设备宽度">
          {DEVICES.map((d) => (
            <button
              key={d.id}
              type="button"
              role="tab"
              aria-selected={device === d.id}
              title={d.label}
              className={`fnx-browser-dev-btn${device === d.id ? " on" : ""}`}
              onClick={() => setDevice(d.id)}
            >
              <d.icon size={13} />
            </button>
          ))}
        </div>
        <button
          type="button"
          className="fnix-ibtn sm"
          title="新窗口打开"
          onClick={openNewWindow}
          disabled={!data}
        >
          <ExternalLink size={13} />
        </button>
      </div>

      <div className="fnx-browser-viewport">
        {loading ? (
          <div className="fnx-studio-empty">
            <Loader2 size={24} className="spin" />
            <p>正在加载…</p>
          </div>
        ) : error ? (
          <div className="fnx-studio-empty">
            <Globe size={28} />
            <p>预览加载失败</p>
            <p className="dim">{error}</p>
            <button type="button" className="wb-mini-btn" onClick={reload}>
              重试
            </button>
          </div>
        ) : srcDoc ? (
          <iframe
            className="fnx-browser-frame"
            style={{ width: DEVICE_W[device] }}
            sandbox="allow-scripts"
            srcDoc={srcDoc}
            title={selected?.name ?? "HTML 预览"}
          />
        ) : (
          <div className="fnx-studio-empty">
            <Globe size={28} />
            <p>生成 HTML 成果后，可以在这里像用户一样预览</p>
            <p className="dim">支持桌面 / 平板 / 手机宽度 · 刷新 · 新窗口</p>
          </div>
        )}
      </div>
    </div>
  );
}
