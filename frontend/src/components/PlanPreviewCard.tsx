import RiskBadge from "./RiskBadge";
import type { PlanPreview } from "../lib/types";

export default function PlanPreviewCard({ plan }: { plan: PlanPreview }) {
  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-medium text-sm">Plan Preview</div>
        <RiskBadge level={plan.risk_level} />
      </div>
      <p className="text-sm text-neutral-700">{plan.summary}</p>

      <div>
        <div className="text-xs font-medium text-neutral-500 mb-1">Targets ({plan.targets.length})</div>
        <div className="flex flex-wrap gap-1.5">
          {plan.targets.map((t) => (
            <span key={t.id} className="badge bg-neutral-100 text-neutral-700 border border-line">{t.name}</span>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs font-medium text-neutral-500 mb-1">Steps</div>
        <ol className="text-sm text-neutral-700 list-decimal list-inside space-y-0.5">
          {plan.steps.map((s, i) => (
            <li key={i}>{s.description}</li>
          ))}
        </ol>
      </div>

      <div>
        <div className="text-xs font-medium text-neutral-500 mb-1">Expected changes</div>
        <ul className="text-sm text-neutral-700 list-disc list-inside space-y-0.5">
          {plan.expected_changes.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
        {plan.no_changes_note && <p className="text-xs text-neutral-500 mt-1">{plan.no_changes_note}</p>}
      </div>

      {plan.risk_reasons.length > 0 && (
        <div>
          <div className="text-xs font-medium text-neutral-500 mb-1">Risk rationale</div>
          <ul className="text-xs text-neutral-500 list-disc list-inside">
            {plan.risk_reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
