import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, getToken, type VerifiedItem } from "../lib/api";
import { useAuth } from "../lib/auth";

const CHAIN_STEPS = [
  { n: 1, key: "source_file",        label: "Source file",                color: "bg-slate-700",   desc: (t: TraceData) => t.source_file ? `${String(t.source_file.filename)} · sha256 ${String(t.source_file.file_hash).slice(0, 12)}…` : "—" },
  { n: 2, key: "raw_record",         label: "Raw Record (immutable)",      color: "bg-slate-600",   desc: (t: TraceData) => t.raw_record ? `row ${String(t.raw_record.row_number)} · hash ${String(t.raw_record.row_hash).slice(0, 12)}…` : "—" },
  { n: 3, key: "field_provenance",   label: "Normalization & Provenance",  color: "bg-blue-600",    desc: (t: TraceData) => `${t.field_provenance.length} fields canonical` },
  { n: 4, key: "validation_results", label: "Validation",                  color: "bg-amber-600",   desc: (t: TraceData) => `${t.validation_results.length} rules evaluated` },
  { n: 5, key: "exceptions",         label: "Exceptions",                  color: "bg-orange-600",  desc: (t: TraceData) => t.exceptions.length ? `${t.exceptions.length} exception${t.exceptions.length > 1 ? "s" : ""}: ${t.exceptions.map((e) => String(e.rule_id)).join(", ")}` : "none — clean record" },
  { n: 6, key: "ai_recommendations", label: "AI Recommendations (advisory)", color: "bg-indigo-600", desc: (t: TraceData) => `${t.ai_recommendations.length} AI interaction${t.ai_recommendations.length !== 1 ? "s" : ""}` },
  { n: 7, key: "review_decisions",   label: "Human Review Decisions",      color: "bg-violet-600",  desc: (t: TraceData) => t.review_decisions.length ? `${t.review_decisions.length} decision${t.review_decisions.length > 1 ? "s" : ""}` : "no decisions recorded" },
  { n: 8, key: "verified_versions",  label: "Verified Version (immutable)", color: "bg-emerald-600", desc: (t: TraceData) => t.verified_versions.map((v) => `v${String(v.version)} · hash ${String(v.record_hash).slice(0, 12)}…`).join("; ") || "—" },
];

type TraceData = {
  loan_id: string | null;
  source_file: Record<string, unknown> | null;
  raw_record: Record<string, unknown> | null;
  field_provenance: Array<Record<string, string>>;
  validation_results: Array<Record<string, unknown>>;
  exceptions: Array<Record<string, unknown>>;
  ai_recommendations: Array<Record<string, unknown>>;
  review_decisions: Array<Record<string, unknown>>;
  verified_versions: Array<Record<string, unknown>>;
};

export default function ConsumerDashboard() {
  const { name, logout } = useAuth();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<VerifiedItem | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);

  const summary = useQuery({ queryKey: ["consumer-summary"], queryFn: () => api.summary("data_consumer") });
  const verified = useQuery({ queryKey: ["verified", q], queryFn: () => api.listVerified(q || undefined) });
  const detail = useQuery({
    queryKey: ["verified-detail", selected?.id],
    queryFn: () => api.getVerified(selected!.id),
    enabled: !!selected,
  });
  const trace = useQuery({
    queryKey: ["trace", selected?.loan_pk],
    queryFn: () => api.trace(selected!.loan_pk),
    enabled: !!selected && traceOpen,
  });

  async function download(format: string) {
    const res = await fetch(api.exportUrl(format), { headers: { Authorization: `Bearer ${getToken()}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `verified_loans.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const s = summary.data as Record<string, unknown> | undefined;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Data Consumer</h1>
            <p className="text-xs text-slate-500">LoanTrust Copilot · {name} · read-only access</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => download("csv")} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
              Export CSV
            </button>
            <button onClick={() => download("json")} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
              Export JSON
            </button>
            <button onClick={logout} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-xl bg-white border border-slate-200 p-5 shadow-sm">
            <p className="text-xs uppercase tracking-widest text-slate-400 mb-1">Verified loans</p>
            <p className="text-3xl font-bold text-slate-900">{s?.verified_loans === undefined ? "—" : String(s.verified_loans)}</p>
          </div>
          <div className="rounded-xl bg-white border border-slate-200 p-5 shadow-sm">
            <p className="text-xs uppercase tracking-widest text-slate-400 mb-1">Data quality</p>
            <p className="text-3xl font-bold text-slate-900">{s?.quality_score == null ? "—" : `${String(s.quality_score)}%`}</p>
          </div>
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-5 shadow-sm">
            <p className="text-xs uppercase tracking-widest text-emerald-600 mb-1">Integrity</p>
            <p className="text-sm font-semibold text-emerald-800">SHA-256 · Immutable · Versioned</p>
            <p className="text-[10px] text-emerald-600 mt-1">Every verified record is cryptographically hashed</p>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-6">
          {/* List panel */}
          <section className="col-span-5">
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="p-4 border-b border-slate-100">
                <h2 className="text-sm font-semibold text-slate-700 mb-2">Verified Records</h2>
                <input
                  className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm w-full"
                  placeholder="search loan id or hash…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              {verified.isLoading && <p className="text-sm text-slate-500 p-4">Loading…</p>}
              {verified.data && verified.data.items.length === 0 && (
                <p className="text-sm text-slate-500 p-4">No verified records yet.</p>
              )}
              <ul className="divide-y divide-slate-100 max-h-[62vh] overflow-auto">
                {verified.data?.items.map((v) => (
                  <li key={v.id}>
                    <button
                      data-testid="verified-item"
                      onClick={() => { setSelected(v); setTraceOpen(false); }}
                      className={`w-full text-left px-4 py-3 transition-colors ${selected?.id === v.id ? "bg-emerald-50 border-l-2 border-emerald-500" : "hover:bg-slate-50 border-l-2 border-transparent"}`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className="inline-block rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5">VERIFIED</span>
                          <span className="text-xs font-mono text-slate-500">v{v.version}</span>
                        </div>
                        {v.ai_used && (
                          <span className="text-[10px] rounded bg-indigo-100 text-indigo-700 px-1.5 py-0.5">AI used</span>
                        )}
                      </div>
                      <p className="text-sm font-semibold text-slate-800">{v.loan_id ?? "—"}</p>
                      <p className="text-[10px] font-mono text-slate-400 mt-0.5">{v.record_hash.slice(0, 28)}…</p>
                    </button>
                  </li>
                ))}
              </ul>
              {verified.data && (
                <p className="text-[10px] text-slate-400 px-4 py-2 border-t border-slate-100">{verified.data.total} verified records</p>
              )}
            </div>
          </section>

          {/* Detail panel */}
          <section className="col-span-7">
            {!selected && (
              <div className="rounded-xl border border-dashed border-slate-300 bg-white p-16 text-center shadow-sm">
                <p className="text-slate-400 text-sm">Select a verified record</p>
                <p className="text-xs text-slate-300 mt-1">Snapshot, hash, traceability chain, and export will appear here</p>
              </div>
            )}

            {selected && detail.data && (
              <div className="space-y-4">
                {/* Verified header */}
                <div className="rounded-xl border border-emerald-200 bg-white shadow-sm overflow-hidden">
                  <div className="bg-emerald-600 px-5 py-3 flex items-center gap-3">
                    <span className="text-white font-bold text-lg">VERIFIED</span>
                    <div className="flex items-center gap-2 ml-auto">
                      <span className="rounded-full bg-emerald-500 text-white text-xs font-bold px-2.5 py-0.5">
                        Version {detail.data.version}
                        {detail.data.supersedes_version ? ` (supersedes v${detail.data.supersedes_version})` : ""}
                      </span>
                      {detail.data.ai_used && (
                        <span className="rounded-full bg-indigo-600 text-white text-xs px-2.5 py-0.5">AI used</span>
                      )}
                    </div>
                  </div>
                  <div className="p-5">
                    <div className="flex items-baseline gap-3 mb-3">
                      <h2 className="text-xl font-bold text-slate-900">{detail.data.loan_id}</h2>
                    </div>

                    <div className="space-y-2">
                      <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2">
                        <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">record hash:</p>
                        <p className="text-xs font-mono break-all text-slate-700">{detail.data.record_hash}</p>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Verified by</p>
                          <p className="text-xs font-mono text-slate-700">{detail.data.reviewer_id}</p>
                        </div>
                        <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2">
                          <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Verified at</p>
                          <p className="text-xs text-slate-700">{new Date(detail.data.verified_at).toLocaleString()}</p>
                        </div>
                      </div>
                    </div>

                    {/* Snapshot */}
                    <div className="mt-4">
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-2">Canonical snapshot</p>
                      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
                        {Object.entries(detail.data.snapshot).slice(0, 16).map(([k, v]) => (
                          <div key={k} className="flex items-baseline gap-2">
                            <span className="text-slate-400 shrink-0 w-28 truncate">{k}</span>
                            <span className="font-mono text-slate-700">{v == null ? "—" : String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <button
                      onClick={() => setTraceOpen((o) => !o)}
                      className="mt-4 rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50 font-medium w-full"
                    >
                      {traceOpen ? "Hide traceability" : "Inspect traceability"}
                    </button>
                  </div>
                </div>

                {/* Traceability chain */}
                {traceOpen && (
                  <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                      <h3 className="font-semibold text-slate-900">Raw → Verified lineage</h3>
                      <span className="text-xs text-slate-400">· complete data chain · read-only</span>
                    </div>

                    {trace.isLoading && <p className="text-sm text-slate-500">Loading traceability chain…</p>}

                    {trace.data && (
                      <div className="relative">
                        <div className="absolute left-4 top-3 bottom-3 w-0.5 bg-slate-200" />
                        <ol className="space-y-4">
                          {CHAIN_STEPS.map((step) => {
                            const td = trace.data as TraceData;
                            const desc = step.desc(td);
                            return (
                              <li key={step.key} className="flex items-start gap-4">
                                <div className={`relative z-10 shrink-0 h-8 w-8 rounded-full ${step.color} flex items-center justify-center text-white text-xs font-bold shadow`}>
                                  {step.n}
                                </div>
                                <div className="flex-1 pt-1">
                                  <p className="text-sm font-semibold text-slate-800">{step.label}</p>
                                  <p className="text-xs font-mono text-slate-500 break-all">{desc}</p>
                                </div>
                              </li>
                            );
                          })}
                        </ol>
                        <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-200 p-3">
                          <p className="text-xs text-emerald-800 font-medium">
                            Data integrity guarantee
                          </p>
                          <p className="text-[11px] text-emerald-600 mt-0.5">
                            Every step from raw ingestion to verified output is recorded. Raw data is immutable.
                            AI recommendations are advisory — human review is the authoritative decision.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
