import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setToken, type Role } from "./api";

interface AuthState {
  token: string | null;
  role: Role | null;
  name: string | null;
  login: (email: string, password: string) => Promise<Role>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(getToken());
  const [role, setRole] = useState<Role | null>(
    (localStorage.getItem("loantrust.role") as Role | null) ?? null,
  );
  const [name, setName] = useState<string | null>(localStorage.getItem("loantrust.name"));

  const value = useMemo<AuthState>(
    () => ({
      token,
      role,
      name,
      async login(email, password) {
        const res = await api.login(email, password);
        setToken(res.access_token);
        localStorage.setItem("loantrust.role", res.role);
        localStorage.setItem("loantrust.name", res.name);
        setTok(res.access_token);
        setRole(res.role);
        setName(res.name);
        return res.role;
      },
      logout() {
        clearToken();
        localStorage.removeItem("loantrust.role");
        localStorage.removeItem("loantrust.name");
        setTok(null);
        setRole(null);
        setName(null);
      },
    }),
    [token, role, name],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
