import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { login as apiLogin, api } from "../api";

const AuthContext = createContext(null);

const getInitialUser = () => {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem("cctv_user") : null;
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getInitialUser);
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return typeof window !== "undefined" && Boolean(localStorage.getItem("cctv_token"));
  });
  const [isLoading, setIsLoading] = useState(true);

  // On mount, check if user is already logged in
  useEffect(() => {
    let mounted = true;

    const checkAuth = async () => {
      const token = localStorage.getItem("cctv_token");
      if (!token) {
        if (mounted) {
          setIsLoading(false);
          setIsAuthenticated(false);
          setUser(null);
        }
        return;
      }

      try {
        // Try to fetch current user from backend with safety timeout
        const response = await api.get("/auth/me");
        if (mounted) {
          setUser(response.data);
          localStorage.setItem("cctv_user", JSON.stringify(response.data));
          setIsAuthenticated(true);
        }
      } catch (err) {
        // Token is invalid, expired, or backend unreachable
        if (mounted) {
          if (err.response?.status === 401 || err.response?.status === 403) {
            localStorage.removeItem("cctv_token");
            localStorage.removeItem("cctv_user");
            setIsAuthenticated(false);
            setUser(null);
          }
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    // Safety fallback: if anything hangs, guarantee loading unblocks after 3s
    const safetyTimer = setTimeout(() => {
      if (mounted) setIsLoading(false);
    }, 3000);

    checkAuth().finally(() => {
      clearTimeout(safetyTimer);
    });

    return () => {
      mounted = false;
      clearTimeout(safetyTimer);
    };
  }, []);

  const login = useCallback(async (username, pass) => {
    const data = await apiLogin(username, pass);
    const resolvedUser = data.user || {
      username: data.username || username,
      role: data.role || (username.toLowerCase() === "admin" ? "admin" : "user"),
    };
    localStorage.setItem("cctv_token", data.access_token);
    localStorage.setItem("cctv_user", JSON.stringify(resolvedUser));
    setUser(resolvedUser);
    setIsAuthenticated(true);
    return resolvedUser;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("cctv_token");
    localStorage.removeItem("cctv_user");
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  const token = typeof window !== "undefined" ? localStorage.getItem("cctv_token") : null;
  const tokenPayload = token ? (() => {
    try {
      const base64Url = token.split(".")[1];
      if (!base64Url) return null;
      const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
      return JSON.parse(atob(base64));
    } catch {
      return null;
    }
  })() : null;

  const username = user?.username || tokenPayload?.sub || (token ? "admin" : null);
  const role = user?.role || tokenPayload?.role || (username === "admin" ? "admin" : null);
  const isAdmin = Boolean(
    role === "admin" ||
    role === "administrator" ||
    username === "admin" ||
    user?.username === "admin" ||
    tokenPayload?.sub === "admin"
  );

  return (
    <AuthContext.Provider value={{ user, username, role, isAdmin, isAuthenticated, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
