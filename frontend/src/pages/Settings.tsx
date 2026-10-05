import { useEffect, useState } from "react";
import { api, clearToken } from "../lib/api";
import { useNavigate } from "react-router-dom";

interface MemoryItem { id: string; scope: string; key: string; value: string; source: string; conversation_id: string | null; }
interface AuditRow { id: string; timestamp: string; user_id: string | null; action: string; resource: string; details: string; }

export default function Settings() {
  const [memory, setMemory] = useState<MemoryItem[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.get<MemoryItem[]>("/memory").then(setMemory).catch(() => {});
    api.get<AuditRow[]>("/audit").then(setAudit).catch(() => setAudit([]));
  }, []);

  async function deleteItem(id: string) {
    await api.delete(`/memory/${id}`);
    setMemory((prev) => prev.filter((m) => m.id !== id));
  }

  function logout() {
    clearToken();
    navigate("/login");
    window.location.reload();
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-lg font-semibold">Settings</h1>

      <section className="space-y-2">
        <h2 className="text-sm font-medium">Account</h2>
        <button className="btn-secondary" onClick={logout}>Sign out</button>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium">Memory</h2>
        <p className="text-xs text-neutral-500">Non-secret conversation/preference memory the agent uses for context. Secrets are never stored here.</p>
        <div className="card divide-y divide-line">
          {memory.map((m) => (
            <div key={m.id} className="flex items-center justify-between px-4 py-2 text-sm">
              <div>
                <div className="font-medium">{m.key}</div>
                <div className="text-xs text-neutral-500">{m.value} · {m.scope}</div>
              </div>
              <button className="btn-danger text-xs" onClick={() => deleteItem(m.id)}>Delete</button>
            </div>
          ))}
          {memory.length === 0 && <div className="px-4 py-6 text-center text-sm text-neutral-400">No memory stored yet.</div>}
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium">Audit log (admin only)</h2>
        <div className="card divide-y divide-line max-h-72 overflow-y-auto">
          {audit.map((a) => (
            <div key={a.id} className="px-4 py-2 text-xs">
              <span className="text-neutral-400">{new Date(a.timestamp).toLocaleString()}</span>{" "}
              <span className="font-medium">{a.action}</span> — {a.resource}
            </div>
          ))}
          {audit.length === 0 && <div className="px-4 py-6 text-center text-sm text-neutral-400">No audit entries visible.</div>}
        </div>
      </section>
    </div>
  );
}
