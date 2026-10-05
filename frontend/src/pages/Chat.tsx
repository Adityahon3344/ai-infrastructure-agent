import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import ApprovalCard from "../components/ApprovalCard";
import PlanPreviewCard from "../components/PlanPreviewCard";
import ServerPicker from "../components/ServerPicker";
import LiveExecutionPanel from "../components/LiveExecutionPanel";
import type { ChatResponse } from "../lib/types";

interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}

const SUGGESTIONS = [
  "Install nginx on my server",
  "Check disk usage on all production servers",
  "Restart nginx on web-01",
  "Show all my servers",
];

export default function Chat() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length]);

  async function send(message: string, selectedServerIds?: string[]) {
    if (!message.trim()) return;
    setBusy(true);
    setTurns((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    try {
      const res = await api.post<ChatResponse>("/chat", {
        conversation_id: conversationId,
        message,
        selected_server_ids: selectedServerIds,
      });
      setConversationId(res.conversation_id);
      setTurns((prev) => [...prev, { role: "assistant", content: res.message, response: res }]);
    } catch (err: any) {
      setTurns((prev) => [...prev, { role: "assistant", content: `Error: ${err.message}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-screen">
      <header className="border-b border-line px-6 py-4 flex items-center justify-between">
        <div>
          <div className="font-semibold text-sm">AI Infrastructure Agent</div>
          <div className="text-xs text-neutral-500">Describe what you want to automate — I'll plan it, validate it, and ask before anything risky.</div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4 max-w-3xl w-full mx-auto">
        {turns.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-neutral-500">Try one of these:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn-secondary text-xs" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={t.role === "user" ? "bg-ink text-white rounded-lg px-4 py-2 text-sm max-w-lg" : "w-full max-w-xl space-y-3"}>
              {t.role === "user" ? (
                t.content
              ) : (
                <>
                  <div className="text-sm whitespace-pre-line">{t.content}</div>
                  {t.response?.server_options && t.response.server_options.length > 0 && t.response.needs_server_selection && (
                    <ServerPicker options={t.response.server_options} onSelect={(ids) => send(t.content, ids)} />
                  )}
                  {t.response?.needs_server_selection && t.response.server_options.length === 0 && (
                    <ServerPicker options={[]} onSelect={() => {}} />
                  )}
                  {t.response?.plan_preview && <PlanPreviewCard plan={t.response.plan_preview} />}
                  {t.response?.approval && (
                    <ApprovalCard approval={t.response.approval} onDecided={() => {}} />
                  )}
                  {t.response?.job_id && !t.response.approval && (
                    <LiveExecutionPanel jobId={t.response.job_id} />
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-line px-6 py-4">
        <form
          className="max-w-3xl mx-auto flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            className="input"
            placeholder="What do you want to automate?"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
          />
          <button className="btn-primary" disabled={busy || !input.trim()}>Send</button>
        </form>
      </div>
    </div>
  );
}
