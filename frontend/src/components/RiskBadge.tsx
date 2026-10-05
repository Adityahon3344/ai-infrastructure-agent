export default function RiskBadge({ level }: { level: string }) {
  const styles: Record<string, string> = {
    low: "bg-green-50 text-green-700 border border-green-200",
    medium: "bg-amber-50 text-amber-700 border border-amber-200",
    high: "bg-red-50 text-red-700 border border-red-200",
  };
  return <span className={`badge ${styles[level] || styles.low}`}>{level.toUpperCase()} RISK</span>;
}
