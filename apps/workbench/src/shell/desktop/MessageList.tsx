/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Desktop-client transcript — windowed turns + memoized bubbles.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import type { ChatMsg } from "./useChatFlow";
import type { CodeFileChange } from "./fnixRuntime";
import { sendFeedback } from "./fnixRuntime";
import { MessageBubble } from "./MessageBubble";
import { MESSAGE_WINDOW, windowMessages } from "./windowing";
import "highlight.js/styles/github.css";

interface Props {
  messages: ChatMsg[];
  streaming: boolean;
  status?: string | null;
  onRegenerate?: () => void;
  fileChanges?: CodeFileChange[];
  onOpenDiff?: (path: string) => void;
  /** 钉选文件到 Canvas Dock（DiffBlock 用）*/
  onPin?: (path: string) => void;
  /** widget 内 sendPrompt 按钮 → 回灌为新用户消息（dynamic-ui）*/
  onSendPrompt?: (text: string) => void;
}

export function MessageList({
  messages,
  streaming,
  status,
  onRegenerate,
  fileChanges,
  onOpenDiff,
  onPin,
  onSendPrompt,
}: Props) {
  const feedRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const [showJump, setShowJump] = useState(false);
  // 用户滚上去后新增的消息计数（流式 + 非流式）
  const [newCount, setNewCount] = useState(0);
  const lastMsgCountRef = useRef(messages.length);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [vote, setVote] = useState<Record<string, "up" | "down" | undefined>>({});
  const [showAll, setShowAll] = useState(false);

  const { visible, hidden } = useMemo(
    () => (showAll ? { visible: messages, hidden: 0 } : windowMessages(messages, MESSAGE_WINDOW)),
    [messages, showAll],
  );

  // Track whether the user is pinned to the bottom. Don't yank them back down
  // while they're scrolling up to read earlier content.
  useEffect(() => {
    const feed = feedRef.current;
    if (!feed) return;
    const onScroll = () => {
      const near = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
      pinnedRef.current = near;
      setShowJump(!near);
      if (near) setNewCount(0);
    };
    feed.addEventListener("scroll", onScroll, { passive: true });
    return () => feed.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const feed = feedRef.current;
    if (!feed) return;
    // Only auto-scroll when the user is already at the bottom. If they've
    // scrolled up to read, leave them alone (no interrupting jumps).
    if (pinnedRef.current) {
      feed.scrollTop = feed.scrollHeight;
    } else {
      // User is reading history — count new messages since they scrolled away
      const delta = messages.length - lastMsgCountRef.current;
      if (delta > 0) setNewCount((c) => c + delta);
    }
    lastMsgCountRef.current = messages.length;
  }, [visible, streaming, status, messages.length]);

  const jumpToLatest = useCallback(() => {
    const feed = feedRef.current;
    if (!feed) return;
    pinnedRef.current = true;
    setShowJump(false);
    feed.scrollTop = feed.scrollHeight;
  }, []);

  // Reset window and scroll state when switching threads (length shrinks a lot)
  useEffect(() => {
    if (messages.length <= MESSAGE_WINDOW) setShowAll(false);
    // 会话切换：消息数量骤降时重置滚动状态，避免残留 jump 按钮、新消息计数、pinned 标记
    if (messages.length < lastMsgCountRef.current) {
      setShowJump(false);
      setNewCount(0);
      pinnedRef.current = true;
    }
    lastMsgCountRef.current = messages.length;
  }, [messages.length]);

  const onCopy = useCallback((id: string, text: string) => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id);
      window.setTimeout(() => setCopiedId(null), 1400);
    });
  }, []);

  const onVote = useCallback(
    (id: string, v: "up" | "down") => {
      setVote((prev) => ({ ...prev, [id]: v }));
      // 用户反馈信号回流 (用户反馈信号机制):
      // 找到这条 assistant 消息对应的上一条 user 消息, 把反馈写入 HERA
      const msgIdx = messages.findIndex((m) => m.id === id);
      if (msgIdx < 0) return;
      // 向前找最近的 user 消息
      for (let i = msgIdx - 1; i >= 0; i--) {
        if (messages[i].role === "user") {
          const userInput = messages[i].content || "";
          if (userInput.trim()) {
            // fire-and-forget, 失败静默降级 (不阻断 UI)
            void sendFeedback({ userInput, feedback: v });
          }
          break;
        }
      }
    },
    [messages],
  );

  return (
    <div className="fnix-feed" ref={feedRef}>
      {/* a11y: role=log 隐含 aria-live=polite — 流式新消息按序播报且不打断用户；
          aria-atomic=false 确保只播报新增内容而非整段重读 */}
      <div
        className="fnix-feed-inner"
        role="log"
        aria-live="polite"
        aria-atomic="false"
        aria-label="对话消息"
      >
        {hidden > 0 ? (
          <div className="fnix-feed-window">
            <button type="button" className="fnix-expand-msg" onClick={() => setShowAll(true)}>
              显示更早的消息（已隐藏 {hidden} 条）
            </button>
          </div>
        ) : null}

        {visible.map((m, idx) => {
          const absoluteIdx = messages.length - visible.length + idx;
          const isLastAssistant =
            m.role === "assistant" && absoluteIdx === messages.length - 1;
          return (
            <MessageBubble
              key={m.id}
              message={m}
              isLastAssistant={isLastAssistant}
              streaming={streaming}
              status={status}
              fileChanges={isLastAssistant ? fileChanges : undefined}
              onOpenDiff={onOpenDiff}
              onRegenerate={onRegenerate}
              copiedId={copiedId}
              onCopy={onCopy}
              vote={vote[m.id]}
              onVote={onVote}
              onPin={onPin}
              onSendPrompt={onSendPrompt}
            />
          );
        })}
      </div>
      {showJump ? (
        <div className="fnix-jump-latest">
          <button
            type="button"
            className={`fnix-jump-btn${newCount > 0 ? " has-new" : ""}`}
            title={newCount > 0 ? `${newCount} 条新消息` : "回到最新"}
            aria-label="回到最新"
            onClick={jumpToLatest}
          >
            <ArrowDown size={18} />
            {newCount > 0 ? (
              <span className="fnix-jump-badge">{newCount > 99 ? "99+" : newCount}</span>
            ) : null}
          </button>
        </div>
      ) : null}
    </div>
  );
}
