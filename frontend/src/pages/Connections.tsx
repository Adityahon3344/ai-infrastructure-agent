import { useEffect, useState } from "react";
import { api } from "../lib/api";
import StatusBadge from "../components/StatusBadge";
import type { Connection } from "../lib/types";

export default function Connections() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [type, setType] = useState<"ssh" | "aws">("ssh");
  const [form, setForm] = useState<any>({ name: "", hostname: "", port: 22, username: "root", password: "", private_key: "", region: "us-east-1", aws_access_key_id: "", aws_secret_access_key: "" });
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  async function load() { setConnections(await api.get<Connection[]>("/connections")); }
  useEffect(() => { load(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const payload: any = { name: form.name, type, config: {} };
    if (type === "ssh") {
      payload.config = { hostname: form.hostname, port: Number(form.port), username: form.username };
      if (form.private_key) payload.private_key = form.private_key;
      else payload.password = form.password;
    } else {
      payload.config = { region: form.region };
      payload.aws_access_key_id = form.aws_access_key_id;
      payload.aws_secret_access_key = form.aws_secret_access_key;
    }
    await api.post("/connections", payload);
    setShowForm(false);
    load();
  }

  async function test(id: string) {
    const res = await api.post<{ success: boolean; message: string }>(`/connections/${id}/test`);
    setTestResult((prev) => ({ ...prev, [id]: res.message }));
    load();
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Connections</h1>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>+ Add Connection</button>
      </div>

      {showForm && (
        <form onSubmit={create} className="card p-4 space-y-3">
          <div className="flex gap-2">
            <button type="button" className={type === "ssh" ? "btn-primary" : "btn-secondary"} onClick={() => setType("ssh")}>SSH</button>
            <button type="button" className={type === "aws" ? "btn-primary" : "btn-secondary"} onClick={() => setType("aws")}>AWS</button>
          </div>
          <input className="input" placeholder="Connection name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          {type === "ssh" ? (
            <div className="grid grid-cols-2 gap-3">
              <input className="input" placeholder="Hostname" value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })} required />
              <input className="input" placeholder="Port" type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
              <input className="input" placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
              <input className="input" placeholder="Password (or leave blank if using key)" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <textarea className="input col-span-2" placeholder="Private key (PEM, optional)" rows={3} value={form.private_key} onChange={(e) => setForm({ ...form, private_key: e.target.value })} />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <input className="input" placeholder="Default region (e.g. us-east-1)" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
              <div />
              <input className="input" placeholder="AWS Access Key ID" value={form.aws_access_key_id} onChange={(e) => setForm({ ...form, aws_access_key_id: e.target.value })} />
              <input className="input" placeholder="AWS Secret Access Key" type="password" value={form.aws_secret_access_key} onChange={(e) => setForm({ ...form, aws_secret_access_key: e.target.value })} />
              <p className="col-span-2 text-xs text-neutral-500">Prefer IAM roles / short-lived credentials in production. Static keys are supported for convenience.</p>
            </div>
          )}
          <div className="flex gap-2">
            <button className="btn-primary" type="submit">Save</button>
            <button className="btn-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Last Tested</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {connections.map((c) => (
              <tr key={c.id} className="border-t border-line">
                <td className="px-4 py-2 font-medium">{c.name}</td>
                <td className="px-4 py-2 uppercase text-xs">{c.type}</td>
                <td className="px-4 py-2"><StatusBadge status={c.status} /></td>
                <td className="px-4 py-2 text-xs text-neutral-500">{c.last_tested_at ? new Date(c.last_tested_at).toLocaleString() : "Never"}{testResult[c.id] && <div>{testResult[c.id]}</div>}</td>
                <td className="px-4 py-2"><button className="btn-secondary text-xs" onClick={() => test(c.id)}>Test Connection</button></td>
              </tr>
            ))}
            {connections.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-neutral-400 text-sm">No connections yet. Secrets are encrypted at rest and never shown here.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
