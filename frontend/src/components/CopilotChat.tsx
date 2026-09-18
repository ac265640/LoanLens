import { useState } from "react";
import { copilotAsk } from "../api";

interface Message {
  role: "user" | "assistant";
  text: string;
  model?: string;
}

const SUGGESTIONS = [
  "Which loans are highest risk right now?",
  "Summarize the exceptions flagged in this portfolio.",
  "What credit bands are most vulnerable?",
];

export default function CopilotChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send(question: string) {
    if (!question.trim() || loading) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const r = await copilotAsk(question);
      setMessages((m) => [...m, { role: "assistant", text: r.output, model: r.model_name }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: e instanceof Error ? e.message : "Something went wrong." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="glass flex h-[420px] flex-col rounded-2xl p-4">
      <h3 className="mb-3 text-sm font-semibold" style={{ color: "var(--text)" }}>
        Portfolio Copilot — grounded in Bedrock
      </h3>

      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>
              Ask anything — answers are grounded only in the scored portfolio, never invented.
            </p>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="block w-full rounded-lg border px-3 py-2 text-left text-xs transition-colors hover:bg-white/[0.03]"
                style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className="max-w-[90%] rounded-xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap"
            style={{
              marginLeft: m.role === "user" ? "auto" : 0,
              background: m.role === "user" ? "var(--accent)" : "var(--bg-panel-2)",
              color: m.role === "user" ? "#0a0d14" : "var(--text)",
            }}
          >
            {m.text}
          </div>
        ))}
        {loading && (
          <div className="text-xs animate-pulse-soft" style={{ color: "var(--text-dim)" }}>
            Retrieving grounded facts, then asking Bedrock…
          </div>
        )}
      </div>

      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="Ask about the portfolio…"
          className="flex-1 rounded-lg border px-3 py-2 text-xs outline-none"
          style={{ background: "var(--bg-panel-2)", borderColor: "var(--border)", color: "var(--text)" }}
        />
        <button
          onClick={() => send(input)}
          disabled={loading}
          className="rounded-lg px-3 py-2 text-xs font-medium"
          style={{ background: "var(--accent)", color: "#0a0d14" }}
        >
          Ask
        </button>
      </div>
    </div>
  );
}
