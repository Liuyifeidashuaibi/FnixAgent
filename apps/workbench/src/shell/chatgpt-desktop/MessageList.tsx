/**
 * ChatGPT-client transcript — windowed turns + memoized bubbles.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChatMsg } from "./useChatFlow";
import type { CodexFileChange } from "./fnixRuntime";
import { sendFeedback } from "./fnixRuntime";
import { MessageBubble } from "./MessageBubble";
import { MESSAGE_WINDOW, windowMessages } from "./windowing";
import "highlight.js/styles/github.css";

interface Props {
  messages: ChatMsg[];
  streaming: boolean;
  status?: string | null;
  onRegenerate?: () => void;
  fileChanges?: CodexFileChange[];
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
    }
  }, [visible, streaming, status]);

  const jumpToLatest = useCallback(() => {
    const feed = feedRef.current;
    if (!feed) return;
    pinnedRef.current = true;
    setShowJump(false);
    feed.scrollTop = feed.scrollHeight;
  }, []);

  // Reset window when switching threads (length shrinks a lot)
  useEffect(() => {
    if (messages.length <= MESSAGE_WINDOW) setShowAll(false);
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
      // 用户反馈信号回流 (对标 Cursor Bugbot Learning):
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
    <div className="oai-feed" ref={feedRef}>
      <div className="oai-feed-inner">
        {hidden > 0 ? (
          <div className="oai-feed-window">
            <button type="button" className="oai-expand-msg" onClick={() => setShowAll(true)}>
              Show earlier messages ({hidden} hidden)
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
        <div className="oai-jump-latest">
          <button type="button" className="oai-jump-btn" onClick={jumpToLatest}>
            ↓ Latest
          </button>
        </div>
      ) : null}
    </div>
  );
}
