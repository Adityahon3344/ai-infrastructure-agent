import { useEffect, useState } from "react";
import { api } from "../lib/api";
import StatusBadge from "../components/StatusBadge";
import type { Server } from "../lib/types";

interface Metric { timestamp: string; cpu_percent: number | null; ram_percent: number | null; disk_percent: number | null; }

export default function Monitoring() {
  const [servers, setServers] = useState<Server[]>([]);
  const [metrics, setMetrics] = useState<Record<string, Metric>>({});

  async function load() {
    const list = await api.get<Server[]>("/servers");
    setServers(list);
    const entries = await Promise.all(
      list.map(async (s) => {
        try {
          const m = await api.get<Metric[]>(`/servers/${s.id}/metrics`);
          return [s.id, m[0]] as const;
        } catch { return [s.id, undefined] as const; }
      })
    );
    setMetrics(Object.fromEntries(entries.filter(([, v]) => v)) as Record<string, Metric>);
  }
  useEffect(() => { load(); }, []);

  async function sampleNow(id: string) { await api.post(`/servers/${id}/metrics/sample`); load(); }

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-lg font-semibold">Monitoring</h1>
      <div className="grid grid-cols-3 gap-4">
        {servers.map((s) => {
          const m = metrics[s.id];
          return (
            <div key={s.id} className="card p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-medium text-sm">{s.name}</div>
                <StatusBadge status={s.status} />
              </div>
              {m ? (
                <div className="text-xs text-neutral-600 space-y-1">
                  <div>CPU: {m.cpu_percent?.toFixed(1)}%</div>
                  <div>RAM: {m.ram_percent?.toFixed(1)}%</div>
                  <div>Disk: {m.disk_percent?.toFixed(1)}%</div>
                  <div className="text-neutral-400">as of {new Date(m.timestamp).toLocaleTimeString()}</div>
                </div>
              ) : (
                <div className="text-xs text-neutral-400">No samples yet</div>
              )}
              <button className="btn-secondary text-xs w-full" onClick={() => sampleNow(s.id)}>Sample now</button>
            </div>
          );
        })}
        {servers.length === 0 && <div className="text-sm text-neutral-400">No servers to monitor yet.</div>}
      </div>
    </div>
  );
}
