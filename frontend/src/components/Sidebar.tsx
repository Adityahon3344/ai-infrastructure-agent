import { NavLink } from "react-router-dom";

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 border-r border-line h-screen sticky top-0 flex flex-col bg-white">
      <div className="px-4 py-4 border-b border-line">
        <div className="font-semibold text-sm tracking-tight">AI Infrastructure Agent</div>
        <div className="text-xs text-neutral-500 mt-0.5">Control Plane</div>
      </div>

      <nav className="flex-1 py-3">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `flex items-center gap-2 px-4 py-2 text-sm ${
              isActive
                ? "bg-neutral-100 text-ink font-medium"
                : "text-neutral-600 hover:bg-neutral-50"
            }`
          }
        >
          <span>💬</span>
          <span>Chat</span>
        </NavLink>

        <NavLink
          to="/servers"
          className={({ isActive }) =>
            `flex items-center gap-2 px-4 py-2 text-sm ${
              isActive
                ? "bg-neutral-100 text-ink font-medium"
                : "text-neutral-600 hover:bg-neutral-50"
            }`
          }
        >
          <span>⚙️</span>
          <span>Configuration</span>
        </NavLink>

        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-2 px-4 py-2 text-sm ${
              isActive
                ? "bg-neutral-100 text-ink font-medium"
                : "text-neutral-600 hover:bg-neutral-50"
            }`
          }
        >
          <span>🔧</span>
          <span>Settings</span>
        </NavLink>
      </nav>
    </aside>
  );
}
