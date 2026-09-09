import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading; null = anon
  const [permissions, setPermissions] = useState([]);

  const loadMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data.user);
      setPermissions(data.permissions || []);
      return data.user;
    } catch (e) {
      setUser(null);
      setPermissions([]);
      return null;
    }
  }, []);

  useEffect(() => {
    // Ritorno da Google OAuth: AuthCallback scambia prima il session_id, poi loadMe.
    if (window.location.hash?.includes("session_id=")) return;
    loadMe();
  }, [loadMe]);

  const loginWithGoogleSession = async (sessionId) => {
    const { data } = await api.post("/auth/google/session", { session_id: sessionId });
    if (data.access_token) localStorage.setItem("ie_access_token", data.access_token);
    if (data.refresh_token) localStorage.setItem("ie_refresh_token", data.refresh_token);
    await loadMe();
    return data;
  };

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    if (data.access_token) localStorage.setItem("ie_access_token", data.access_token);
    if (data.refresh_token) localStorage.setItem("ie_refresh_token", data.refresh_token);
    await loadMe();
    return data;
  };

  const logout = async (all = false) => {
    try {
      await api.post(all ? "/auth/logout-all" : "/auth/logout");
    } catch (e) {}
    localStorage.removeItem("ie_access_token");
    localStorage.removeItem("ie_refresh_token");
    setUser(null);
    setPermissions([]);
  };

  const has = (perm) => {
    if (user?.is_superadmin) return true;
    if (permissions.includes("*")) return true;
    return permissions.includes(perm);
  };
  const hasAny = (...perms) => {
    if (user?.is_superadmin) return true;
    if (permissions.includes("*")) return true;
    return perms.some((p) => permissions.includes(p));
  };

  return (
    <AuthContext.Provider value={{ user, permissions, login, loginWithGoogleSession, logout, loadMe, has, hasAny }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
