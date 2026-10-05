export default function ServerPicker({
  options, onSelect,
}: { options: { id: string; name: string; hostname: string; environment: string; os: string }[]; onSelect: (ids: string[]) => void }) {
  if (options.length === 0) {
    return (
      <div className="card p-4 text-sm">
        No matching servers were found.{" "}
        <a href="/servers" className="underline font-medium">Add a server</a>
      </div>
    );
  }
  return (
    <div className="card p-4 space-y-2">
      <div className="text-sm font-medium">Which server(s)?</div>
      <div className="space-y-1.5">
        {options.map((o) => (
          <button
            key={o.id}
            onClick={() => onSelect([o.id])}
            className="w-full text-left text-sm px-3 py-2 rounded-md border border-line hover:bg-neutral-50 flex justify-between"
          >
            <span className="font-medium">{o.name}</span>
            <span className="text-neutral-500">{o.hostname} · {o.environment}</span>
          </button>
        ))}
        <button
          onClick={() => onSelect(options.map((o) => o.id))}
          className="w-full text-left text-sm px-3 py-2 rounded-md border border-dashed border-line hover:bg-neutral-50 text-neutral-600"
        >
          Select all {options.length}
        </button>
      </div>
    </div>
  );
}
