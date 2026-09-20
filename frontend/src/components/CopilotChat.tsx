import { useEffect, useRef, useState } from "react";
import { copilotAsk } from "../api";
import RichText from "./RichText";

interface Message {
  role: "user" | "assistant";
  text: string;
  model?: string;
  fallback?: boolean;
}

const SUGGESTIONS = [
  "Which loans are highest risk right now?",
  "Summarize the exceptions flagged in this portfolio.",
  "What credit bands are most vulnerable?",
];

const TINT = "color-mix(in srgb, var(--accent) 16%, transparent)";

const Spark = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 2.5l2 6.2 6.2 2-6.2 2-2 6.3-2-6.3-6.2-2 6.2-2z" />
  </svg>
);

const ArrowUp = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 19V5M5 12l7-7 7 7" />
  </svg>
);

const Chevron = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M9 6l6 6-6 6" />
  </svg>
);

// Scoped styles. Everything reads the dashboard's existing CSS variables,
// so it follows whatever theme the dashboard is in.
const STYLES = `
.cp-chip { transition: background-color .15s, border-color .15s; }
.cp-chip:hover {
  background: color-mix(in srgb, var(--accent) 9%, transparent);
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
}
.cp-chip .cp-chev { opacity: 0; transform: translateX(-4px); transition: opacity .15s, transform .15s; }
.cp-chip:hover .cp-chev, .cp-chip:focus-visible .cp-chev { opacity: .8; transform: none; }
.cp-chip:focus-visible, .cp-send:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.cp-input { transition: border-color .15s, box-shadow .15s; }
.cp-input:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}

.cp-list { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }

.cp-msg { animation: cp-in .25s ease-out; }
@keyframes cp-in { from { opacity: 0; transform: translateY(6px); } }

.cp-dot { animation: cp-blink 1.1s infinite ease-in-out; }
@keyframes cp-blink {
  0%, 80%, 100% { opacity: .25; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-2px); }
}

@media (prefers-reduced-motion: reduce) {
  .cp-chip, .cp-chip .cp-chev, .cp-input { transition: none; }
  .cp-msg, .cp-dot { animation: none; }
}
`;

export default function CopilotChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  // keep the newest message in view (scrolls the list only, never the page)
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function send(question: string) {
    if (!question.trim() || loading) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const r = await copilotAsk(question);
      setMessages((m) => [...m, { role: "assistant", text: r.output, model: r.model_name, fallback: r.fallback }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: e instanceof Error ? e.message : "Something went wrong." }]);
    } finally {
      setLoading(false);
    }
  }

  const canSend = input.trim().length > 0 && !loading;

  return (
    <div className="glass flex h-[420px] flex-col rounded-2xl p-4">
      <style>{STYLES}</style>

      {/* header */}
      <div className="-mx-4 mb-3 flex items-center justify-between gap-2 border-b px-4 pb-3" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Portfolio Copilot
        </h3>
        <span
          className="rounded-full border px-2 py-0.5 text-[10.5px]"
          style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}
        >
          Grounded in your portfolio
        </span>
      </div>

      {/* conversation */}
      <div ref={listRef} role="log" aria-live="polite" className="cp-list min-h-0 flex-1 overflow-y-auto pr-1">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col">
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <span
                className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl"
                style={{ background: TINT, color: "var(--accent)" }}
              >
                <Spark size={18} />
              </span>
              <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
                Ask about the portfolio
              </p>
              <p className="mt-1 max-w-[280px] text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>
                Answers are grounded only in the scored portfolio, never invented.
              </p>
            </div>

            <div className="space-y-2 pb-1">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="cp-chip flex w-full items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5 text-left text-[13px]"
                  style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}
                >
                  <span>{s}</span>
                  <span className="cp-chev shrink-0" style={{ color: "var(--accent)" }}>
                    <Chevron />
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="cp-msg flex justify-end">
                  <div
                    className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md px-3.5 py-2 text-[13px] leading-relaxed"
                    style={{ background: "var(--accent)", color: "#0a0d14" }}
                  >
                    {m.text}
                  </div>
                </div>
              ) : (
                <div key={i} className="cp-msg flex items-start gap-2">
                  <span
                    className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
                    style={{ background: TINT, color: "var(--accent)" }}
                  >
                    <Spark size={12} />
                  </span>
                  <div
                    className="max-w-[88%] rounded-2xl rounded-tl-md border px-3.5 py-2.5 text-[13px] leading-relaxed"
                    style={{ background: "var(--bg-panel-2)", borderColor: "var(--border)", color: "var(--text)" }}
                  >
                    <RichText text={m.text} />
                    {m.model && (
                      <div
                        className="mt-2.5 flex items-center gap-1.5 border-t pt-2 text-[10.5px]"
                        style={{
                          borderColor: "var(--border)",
                          color: m.fallback ? "var(--amber)" : "var(--text-dim)",
                        }}
                      >
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "currentColor" }} />
                        {m.fallback ? "Template answer — no language model could be reached" : `Answered by ${m.model}`}
                      </div>
                    )}
                  </div>
                </div>
              )
            )}

            {loading && (
              <div className="flex items-center gap-2 pl-8 text-xs" style={{ color: "var(--text-dim)" }}>
                <span className="flex gap-1" aria-hidden="true">
                  {[0, 1, 2].map((n) => (
                    <span
                      key={n}
                      className="cp-dot h-1.5 w-1.5 rounded-full"
                      style={{ background: "var(--text-dim)", animationDelay: `${n * 140}ms` }}
                    />
                  ))}
                </span>
                Retrieving grounded facts, then asking the model…
              </div>
            )}
          </div>
        )}
      </div>

      {/* composer */}
      <div
        className="cp-input mt-3 flex items-center gap-2 rounded-xl border py-1.5 pl-3.5 pr-1.5"
        style={{ background: "var(--bg-panel-2)", borderColor: "var(--border)" }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Ask about the portfolio…"
          aria-label="Ask about the portfolio"
          className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
          style={{ color: "var(--text)" }}
        />
        <button
          onClick={() => send(input)}
          disabled={!canSend}
          aria-label="Send question"
          className="cp-send flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-opacity disabled:cursor-not-allowed"
          style={{ background: "var(--accent)", color: "#0a0d14", opacity: canSend ? 1 : 0.35 }}
        >
          <ArrowUp />
        </button>
      </div>
    </div>
  );
}