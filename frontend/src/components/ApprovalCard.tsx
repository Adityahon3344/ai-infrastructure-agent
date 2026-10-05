import { useState } from "react";
import { api } from "../lib/api";
import RiskBadge from "./RiskBadge";
import type { Approval } from "../lib/types";

export default function ApprovalCard({ approval, onDecided }: { approval: Approval; onDecided: (approved: boolean) => void }) {
  const [busy, setBusy] = useState(false);
  const [decided, setDecided] = useState<null | "approved" | "rejected">(null);

  async function decide(approve: boolean) {
    setBusy(true);
    try {
      await api.post(`/approvals/${approval.id}/${approve ? "approve" : "reject"}`, { note: "" });
      setDecided(approve ? "approved" : "rejected");
      onDecided(approve);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card p-4 space-y-3 border-amber-200 bg-amber-50/40">
      <div className="flex items-center justify-between">
        <div className="font-medium text-sm">Approval required</div>
        <RiskBadge level={approval.risk_level} />
      </div>
      <div className="text-sm space-y-1">
        <div><span className="text-neutral-500">Action:</span> {approval.action_summary}</div>
        <div><span className="text-neutral-500">Target:</span> {approval.target_summary}</div>
        <div><span className="text-neutral-500">Impact:</span> {approval.impact}</div>
      </div>
      {approval.expected_changes.length > 0 && (
        <ul className="text-sm list-disc list-inside text-neutral-700">
          {approval.expected_changes.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )}
      {decided ? (
        <div className="text-sm font-medium">{decided === "approved" ? "Approved — executing…" : "Rejected."}</div>
      ) : (
        <div className="flex gap-2">
          <button className="btn-secondary" disabled={busy} onClick={() => decide(false)}>Cancel</button>
          <button className="btn-primary" disabled={busy} onClick={() => decide(true)}>Approve & Execute</button>
        </div>
      )}
    </div>
  );
}
