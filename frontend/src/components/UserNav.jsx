import { NavLink } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import BrandLogo from "./BrandLogo";

export default function UserNav() {
  const { username, logout } = useAuth();

  const userLinks = [
    { to: "/user/home", label: "Home" },
    { to: "/user/people/add", label: "Add Known Person" },
    { to: "/user/people/promote", label: "Promote Unknown → Known" },
  ];

  return (
    <nav className="border-b border-gray-800 bg-gray-950 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
      <div className="flex items-center gap-6 flex-1 min-w-0">
        <NavLink to="/user/home" className="group shrink-0" title="Virtual Eye Home">
          <BrandLogo />
        </NavLink>
        <div className="flex gap-1">
          {userLinks.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `text-sm px-3 py-1.5 rounded ${
                  isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3 text-sm border-l border-gray-700 pl-4">
        <div className="flex items-center gap-2">
          <div className="text-xs">
            <p className="font-medium">{username}</p>
            <p className="text-gray-500">● USER</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="bg-gray-800 hover:bg-gray-700 rounded px-3 py-1.5"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}
