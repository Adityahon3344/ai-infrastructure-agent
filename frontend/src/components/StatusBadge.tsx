export default function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    online: "bg-green-50 text-green-700 border border-green-200",
    offline: "bg-neutral-100 text-neutral-600 border border-neutral-200",
    warning: "bg-amber-50 text-amber-700 border border-amber-200",
    critical: "bg-red-50 text-red-700 border border-red-200",
    unknown: "bg-neutral-100 text-neutral-500 border border-neutral-200",
    success: "bg-green-50 text-green-700 border border-green-200",
    failed: "bg-red-50 text-red-700 border border-red-200",
    running: "bg-blue-50 text-blue-700 border border-blue-200",
    queued: "bg-neutral-100 text-neutral-600 border border-neutral-200",
    waiting_for_approval: "bg-amber-50 text-amber-700 border border-amber-200",
    partial_success: "bg-amber-50 text-amber-700 border border-amber-200",
    cancelled: "bg-neutral-100 text-neutral-500 border border-neutral-200",
  };
  return <span className={`badge ${styles[status] || styles.unknown}`}>{status.replace(/_/g, " ")}</span>;
}
