"use client";

import * as React from "react";
import { motion } from "motion/react";
import {
  Sparkles,
  Send,
  RotateCcw,
  ExternalLink,
  ChevronRight,
  CircleAlert,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { TabBar } from "@/components/tab-bar";
import { ChatMarkdown } from "@/components/chat-markdown";
import {
  sendChat,
  SUGGESTED_QUESTIONS,
  type ChatSource,
  type ChatState,
} from "@/lib/chat";

type Message = {
  id: string;
  role: "user" | "bot";
  text: string;
  sources?: ChatSource[];
  error?: boolean;
};

let idSeq = 0;
const nextId = () => `${Date.now()}-${idSeq++}`;

export default function ChatPage() {
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [chatState, setChatState] = React.useState<ChatState>(null);
  const [input, setInput] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  const scrollRef = React.useRef<HTMLDivElement>(null);
  const taRef = React.useRef<HTMLTextAreaElement>(null);

  const isEmpty = messages.length === 0;

  // 새 메시지/타이핑 표시 시 항상 맨 아래로
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || loading) return;

    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";

    setMessages((prev) => [...prev, { id: nextId(), role: "user", text }]);
    setLoading(true);

    try {
      const res = await sendChat(text, chatState);
      setChatState(res.state);
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "bot",
          text: res.answer,
          sources: res.sources ?? [],
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "bot",
          text: (err as Error).message,
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const onInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const reset = () => {
    setMessages([]);
    setChatState(null);
    setInput("");
  };

  return (
    <div className="mx-auto flex h-dvh w-full max-w-md flex-col bg-background">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-2 border-b border-border bg-background/90 px-4 py-3 backdrop-blur">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <Sparkles className="h-[18px] w-[18px]" />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-bold leading-tight tracking-tight text-foreground">
            공지 챗봇
          </h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            공지사항을 물어보세요
          </p>
        </div>
        {!isEmpty && (
          <button
            type="button"
            onClick={reset}
            className="flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            새 대화
          </button>
        )}
      </header>

      {/* Messages */}
      <main
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
      >
        {isEmpty ? (
          <EmptyState onPick={send} />
        ) : (
          <ul className="space-y-4">
            {messages.map((m) => (
              <li key={m.id}>
                {m.role === "user" ? (
                  <UserBubble text={m.text} />
                ) : (
                  <BotBubble message={m} />
                )}
              </li>
            ))}
            {loading && (
              <li>
                <TypingBubble />
              </li>
            )}
          </ul>
        )}
      </main>

      {/* Quick chips + input */}
      <div className="shrink-0 border-t border-border bg-background px-3 pb-2 pt-2">
        {!isEmpty && <QuickChips onPick={send} disabled={loading} />}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-end gap-2"
        >
          <textarea
            ref={taRef}
            rows={1}
            value={input}
            onChange={onInputChange}
            onKeyDown={onKeyDown}
            placeholder="공지에 대해 물어보세요…"
            className="max-h-[120px] flex-1 resize-none rounded-2xl border border-input bg-muted px-4 py-2.5 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            aria-label="보내기"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm transition-opacity disabled:opacity-40"
          >
            <Send className="h-[18px] w-[18px]" />
          </button>
        </form>
        <p className="mt-1.5 text-center text-[10px] leading-tight text-muted-foreground">
          AI가 공지를 바탕으로 답해요. 정확한 내용은 원문을 확인하세요.
        </p>
      </div>

      {/* 하단 고정 TabBar 자리 확보 */}
      <div className="h-[58px] shrink-0" aria-hidden />
      <TabBar active="chat" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Empty state — greeting + suggested questions                        */
/* ------------------------------------------------------------------ */

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-1 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent text-primary">
        <Sparkles className="h-8 w-8" />
      </div>
      <h2 className="text-lg font-bold tracking-tight text-foreground">
        무엇이든 물어보세요
      </h2>
      <p className="mt-1.5 max-w-xs text-sm leading-relaxed text-muted-foreground">
        학사·장학·채용 등 컴퓨터공학과 공지를 챗봇이 찾아서 알려드려요.
      </p>

      <div className="mt-7 w-full">
        <p className="mb-2.5 flex items-center justify-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" /> 이런 걸 물어볼 수 있어요
        </p>
        <div className="flex flex-col gap-2">
          {SUGGESTED_QUESTIONS.map((q) => (
            <motion.button
              key={q}
              type="button"
              whileTap={{ scale: 0.98 }}
              onClick={() => onPick(q)}
              className="flex items-center justify-between gap-2 rounded-xl border border-border bg-background px-4 py-3 text-left text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-accent/50"
            >
              <span>{q}</span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Bubbles                                                             */
/* ------------------------------------------------------------------ */

function UserBubble({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-end"
    >
      <div className="max-w-[82%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm">
        {text}
      </div>
    </motion.div>
  );
}

function BotBubble({ message }: { message: Message }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-2"
    >
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
        <Sparkles className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <div
          className={cn(
            "w-fit max-w-full break-words rounded-2xl rounded-tl-md px-4 py-2.5 text-sm leading-relaxed",
            message.error
              ? "bg-red-50 text-red-700"
              : "bg-secondary text-foreground"
          )}
        >
          {message.error ? (
            <span className="flex items-start gap-1.5">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="whitespace-pre-wrap">{message.text}</span>
            </span>
          ) : (
            <ChatMarkdown>{message.text}</ChatMarkdown>
          )}
        </div>

        {message.sources && message.sources.length > 0 && (
          <div className="space-y-1.5">
            <p className="px-1 text-[11px] font-medium text-muted-foreground">
              참고한 공지 {message.sources.length}건
            </p>
            {message.sources.map((s, i) => (
              <SourceCard key={s.id ?? i} source={s} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function TypingBubble() {
  return (
    <div className="flex gap-2">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
        <Sparkles className="h-4 w-4" />
      </div>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-md bg-secondary px-4 py-3.5">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60"
            animate={{ opacity: [0.3, 1, 0.3], y: [0, -2, 0] }}
            transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }}
          />
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Source card (from ChatSource)                                       */
/* ------------------------------------------------------------------ */

function formatSourceDate(s: string): string {
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;
}

function SourceCard({ source }: { source: ChatSource }) {
  const body = (
    <div className="group flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2.5 transition-colors hover:border-primary/40 hover:bg-accent/40">
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-[13px] font-medium leading-snug text-foreground group-hover:text-primary">
          {source.title}
        </p>
        {source.publishedAt && (
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            게시 {formatSourceDate(source.publishedAt)}
          </p>
        )}
      </div>
      {source.url && (
        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70 group-hover:text-primary" />
      )}
    </div>
  );

  if (source.url) {
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        {body}
      </a>
    );
  }
  return body;
}

/* ------------------------------------------------------------------ */
/* Quick chips (compact suggestions above the input)                   */
/* ------------------------------------------------------------------ */

function QuickChips({
  onPick,
  disabled,
}: {
  onPick: (q: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="-mx-3 mb-2 flex gap-2 overflow-x-auto px-3 pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {SUGGESTED_QUESTIONS.map((q) => (
        <button
          key={q}
          type="button"
          disabled={disabled}
          onClick={() => onPick(q)}
          className="shrink-0 whitespace-nowrap rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-accent/60 disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
