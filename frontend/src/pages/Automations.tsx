import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface Automation {
  id: string; name: string; prompt: string; cron_expression: string; enabled: boolean;
  last_run_at: string | null; last_job_id: string | null;
}

export default function Automations() {
  const [items, setItems] = useState<Automation[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", prompt: "", cron_expression: "0 2 * * *" });

  async function load() { setItems(await api.get<Automation[]>("/automations")); }
  useEffect(() => { load(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    await api.post("/automations", { ...form, target_server_ids: [] });
    setShowForm(false);
    setForm({ name: "", prompt: "", cron_expression: "0 2 * * *" });
    load();
  }
  async function toggle(id: string) { await api.post(`/automations/${id}/toggle`); load(); }
  async function remove(id: string) { await api.delete(`/automations/${id}`); load(); }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Automations</h1>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>+ New automation</button>
      </div>

      {showForm && (
        <form onSubmit={create} className="card p-4 space-y-3">
          <input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <input className="input" placeholder='Prompt, e.g. "check disk usage on all production servers"' value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} required />
          <input className="input" placeholder="Cron expression (min hour day month dow)" value={form.cron_expression} onChange={(e) => setForm({ ...form, cron_expression: e.target.value })} required />
          <p className="text-xs text-neutral-500">Example: "0 2 * * *" runs every day at 2:00 AM.</p>
          <div className="flex gap-2">
            <button className="btn-primary" type="submit">Create</button>
            <button className="btn-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
            <tr><th className="text-left px-4 py-2">Name</th><th className="text-left px-4 py-2">Prompt</th><th className="text-left px-4 py-2">Schedule</th><th className="text-left px-4 py-2">Last run</th><th className="text-left px-4 py-2">Actions</th></tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id} className="border-t border-line">
                <td className="px-4 py-2 font-medium">{a.name}</td>
                <td className="px-4 py-2 max-w-xs truncate">{a.prompt}</td>
                <td className="px-4 py-2 font-mono text-xs">{a.cron_expression}</td>
                <td className="px-4 py-2 text-xs text-neutral-500">{a.last_run_at ? new Date(a.last_run_at).toLocaleString() : "Never"}</td>
                <td className="px-4 py-2 space-x-2">
                  <button className="btn-secondary text-xs" onClick={() => toggle(a.id)}>{a.enabled ? "Disable" : "Enable"}</button>
                  <button className="btn-danger text-xs" onClick={() => remove(a.id)}>Delete</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={5} className="px-4 py-8 text-center text-neutral-400 text-sm">No automations yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
