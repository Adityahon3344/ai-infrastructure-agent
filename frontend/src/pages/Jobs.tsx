import { useEffect, useState } from "react";
import { api } from "../lib/api";
import StatusBadge from "../components/StatusBadge";
import RiskBadge from "../components/RiskBadge";
import LiveExecutionPanel from "../components/LiveExecutionPanel";
import type { Job } from "../lib/types";

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Job | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  async function load() {
    const q = statusFilter ? `?status=${statusFilter}` : "";
    setJobs(await api.get<Job[]>(`/jobs${q}`));
  }
  useEffect(() => { load(); }, [statusFilter]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Jobs & History</h1>
        <select className="input w-48" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="partial_success">Partial success</option>
          <option value="waiting_for_approval">Waiting for approval</option>
          <option value="running">Running</option>
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
              <tr><th className="text-left px-4 py-2">Prompt</th><th className="text-left px-4 py-2">Status</th><th className="text-left px-4 py-2">Risk</th><th className="text-left px-4 py-2">When</th></tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-t border-line cursor-pointer hover:bg-neutral-50" onClick={() => setSelected(j)}>
                  <td className="px-4 py-2 max-w-xs truncate">{j.prompt}</td>
                  <td className="px-4 py-2"><StatusBadge status={j.status} /></td>
                  <td className="px-4 py-2"><RiskBadge level={j.risk_level} /></td>
                  <td className="px-4 py-2 text-xs text-neutral-500">{new Date(j.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {jobs.length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-neutral-400 text-sm">No jobs yet.</td></tr>}
            </tbody>
          </table>
        </div>

        <div>
          {selected ? (
            <div className="space-y-3">
              <div className="card p-4 text-sm space-y-1">
                <div className="font-medium">{selected.prompt}</div>
                <div className="text-neutral-500">Status: <StatusBadge status={selected.status} /></div>
                <div className="text-neutral-500">Targets: {selected.target_server_ids.length}</div>
                {selected.error && <div className="text-red-600 text-xs">{selected.error}</div>}
              </div>
              <LiveExecutionPanel jobId={selected.id} />
            </div>
          ) : (
            <div className="card p-8 text-center text-neutral-400 text-sm">Select a job to see its live/replayed execution log.</div>
          )}
        </div>
      </div>
    </div>
  );
}
