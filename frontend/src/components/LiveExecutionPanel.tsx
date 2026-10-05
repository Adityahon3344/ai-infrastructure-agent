import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../lib/api";
import StatusBadge from "./StatusBadge";

interface JobEvent {
  type: string;
  server_id?: string | null;
  tool?: string | null;
  message: string;
  data?: Record<string, unknown>;
  timestamp: string;
}

export default function LiveExecutionPanel({ jobId }: { jobId: string }) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [finalStatus, setFinalStatus] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket(wsUrl(`/ws/jobs/${jobId}`));
    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data) as JobEvent;
      setEvents((prev) => [...prev, data]);
      if (data.type === "job_completed" || data.type === "job_failed") {
        setFinalStatus(data.type === "job_completed" ? "success" : "failed");
      }
    };
    return () => ws.close();
  }, [jobId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const icon = (type: string) => {
    if (type.includes("failed")) return "✕";
    if (type.includes("completed") || type === "verification") return "✓";
    if (type === "task_started" || type === "connecting") return "→";
    return "·";
  };

  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Live execution</div>
        {finalStatus && <StatusBadge status={finalStatus} />}
      </div>
      <div className="max-h-72 overflow-y-auto font-mono text-xs bg-neutral-50 rounded-md p-3 space-y-1 border border-line">
        {events.length === 0 && <div className="text-neutral-400">Waiting for execution to start…</div>}
        {events.map((e, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-neutral-400 w-4 shrink-0">{icon(e.type)}</span>
            <span className={e.type.includes("failed") ? "text-red-600" : "text-neutral-700"}>
              {e.server_id ? `[${e.server_id.slice(0, 8)}] ` : ""}{e.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
