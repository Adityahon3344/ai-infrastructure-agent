import { NavLink } from "react-router-dom";

const configurationItems = [
  { to: "/servers", label: "Servers", icon: "🖥️" },
  { to: "/connections", label: "Connections", icon: "🔑" },
  { to: "/automations", label: "Automations", icon: "⏱️" },
  { to: "/jobs", label: "Jobs & History", icon: "📋" },
  { to: "/monitoring", label: "Monitoring", icon: "📈" },
];

export default function ConfigurationNav() {
  return (
    <div className="border-b border-line bg-white sticky top-0 z-10">
      <div className="px-6 pt-4">
        <h1 className="text-base font-semibold">Configuration</h1>
        <p className="text-xs text-neutral-500 mt-0.5">
          Manage infrastructure, connections, automation, monitoring and settings.
        </p>
      </div>

      <nav className="px-6 pt-3 flex items-center gap-1 overflow-x-auto">
        {configurationItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm border-b-2 transition-colors ${
                isActive
                  ? "border-ink text-ink font-medium"
                  : "border-transparent text-neutral-500 hover:text-ink hover:border-neutral-300"
              }`
            }
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
