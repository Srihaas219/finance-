import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, type Role } from "../lib/api";
import { useAuth } from "../lib/auth";

const DEST: Record<Role, string> = {
  data_operator: "/operator",
  reviewer: "/reviewer",
  data_consumer: "/consumer",
};

const DEMO = [
  { label: "Data Operator", email: "operator@loantrust.demo", password: "operator123" },
  { label: "Reviewer", email: "reviewer@loantrust.demo", password: "reviewer123" },
  { label: "Data Consumer", email: "consumer@loantrust.demo", password: "consumer123" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent, creds?: { email: string; password: string }) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const role = await login(creds?.email ?? email, creds?.password ?? password);
      navigate(DEST[role]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center p-6">
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-sm border border-slate-200 p-8">
        <h1 className="text-xl font-semibold">LoanTrust Copilot</h1>
        <p className="text-sm text-slate-500 mb-6">Loan Data Verification Console</p>

        <form onSubmit={(e) => submit(e)} className="space-y-3">
          <input
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
          />
          <input
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            className="w-full rounded-lg bg-slate-900 text-white py-2 text-sm font-medium disabled:opacity-50"
            disabled={busy}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-6">
          <p className="text-xs uppercase tracking-wide text-slate-400 mb-2">Demo accounts</p>
          <div className="space-y-2">
            {DEMO.map((d) => (
              <button
                key={d.email}
                data-testid={`demo-${d.email.split("@")[0]}`}
                onClick={(e) => submit(e, d)}
                disabled={busy}
                className="w-full text-left rounded-lg border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
              >
                {d.label} <span className="text-slate-400">— {d.email}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
