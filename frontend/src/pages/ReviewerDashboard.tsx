import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type ExceptionItem, type NLRuleResult, type QueueSummary } from "../lib/api";
import { useAuth } from "../lib/auth";

const SEV_CLS: Record<string, string> = {
  high: "bg-red-100 text-red-800 border-red-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-slate-100 text-slate-700 border-slate-200",
};
const SEV_PILL: Record<string, string> = {
  high: "bg-red-100 text-red-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};
const STATUS_PILL: Record<string, string> = {
  open: "bg-blue-100 text-blue-800",
  in_review: "bg-indigo-100 text-indigo-800",
  ignored: "bg-slate-100 text-slate-500",
  resolved: "bg-emerald-100 text-emerald-800",
};

function Pill({ text, cls }: { text: string; cls?: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls ?? "bg-slate-100 text-slate-700"}`}>
      {text}
    </span>
  );
}

function SourceComparison({ output }: { output: Record<string, unknown> }) {
  const vals = output.values as Array<Record<string, unknown>> | undefined;
  if (!Array.isArray(vals) || vals.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-2">Source comparison</p>
      <div className="grid grid-cols-2 gap-3">
        {vals.map((v, i) => (
          <div key={i} className="rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-[10px] uppercase text-slate-400 font-medium">{String(v.source)}</p>
            <p className="font-mono font-semibold text-slate-900 mt-1 text-sm">{String(v.value ?? "—")}</p>
            {v.last_updated_at != null && (
              <p className="text-[10px] text-slate-400 mt-1">updated {String(v.last_updated_at)}</p>
            )}
          </div>
        ))}
      </div>
      {output.recommendation != null && (
        <p className="text-xs text-indigo-700 mt-2 italic">AI recommends: {String(output.recommendation)}</p>
      )}
    </div>
  );
}

function SectionHeader({ label, sub }: { label: string; sub?: string }) {
  return (
    <div className="flex items-baseline gap-2 mb-3">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">{label}</h3>
      {sub && <span className="text-xs text-slate-400">{sub}</span>}
    </div>
  );
}

export default function ReviewerDashboard() {
  const { name, logout } = useAuth();
  const qc = useQueryClient();
  const [filters, setFilters] = useState({ severity: "", type: "", status: "open", q: "" });
  const [selected, setSelected] = useState<ExceptionItem | null>(null);
  const [queueSummary, setQueueSummary] = useState<QueueSummary | null>(null);
  const [nlInput, setNlInput] = useState("");
  const [nlResult, setNlResult] = useState<NLRuleResult | null>(null);
  const [showNlPanel, setShowNlPanel] = useState(false);

  const aiSummary = useMutation({
    mutationFn: () => api.summarizeQueue(),
    onSuccess: (s) => setQueueSummary(s),
  });

  const nlRule = useMutation({
    mutationFn: (nl: string) => api.generateNlRule(nl),
    onSuccess: (r) => { setNlResult(r); setNlInput(""); },
  });

  const summary = useQuery({ queryKey: ["summary"], queryFn: () => api.summaryData() });
  const queue = useQuery({
    queryKey: ["exceptions", filters],
    queryFn: () =>
      api.listExceptions(
        Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) as Record<string, string>,
      ),
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ["exceptions"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
    if (selected) qc.invalidateQueries({ queryKey: ["exception-detail", selected.id] });
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Reviewer Workbench</h1>
            <p className="text-xs text-slate-500">LoanTrust Copilot · {name}</p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            {summary.data && (
              <div className="flex items-center gap-3">
                <span className="rounded-lg bg-blue-50 border border-blue-200 px-3 py-1 text-blue-800 text-xs font-medium">
                  {summary.data.open_exceptions} open exceptions
                </span>
                {summary.data.data_quality_score != null && (
                  <span className="rounded-lg bg-slate-100 px-3 py-1 text-slate-700 text-xs">
                    quality {summary.data.data_quality_score}%
                  </span>
                )}
              </div>
            )}
            <button
              data-testid="summarize-queue"
              disabled={aiSummary.isPending}
              onClick={() => aiSummary.mutate()}
              className="rounded-lg border border-indigo-300 bg-indigo-50 text-indigo-800 px-3 py-1.5 text-sm hover:bg-indigo-100 disabled:opacity-50 font-medium"
            >
              {aiSummary.isPending ? "Summarizing…" : "AI: summarize queue"}
            </button>
            <button
              onClick={() => setShowNlPanel((p) => !p)}
              className="rounded-lg border border-violet-300 bg-violet-50 text-violet-800 px-3 py-1.5 text-sm hover:bg-violet-100 font-medium"
            >
              AI: generate rule
            </button>
            <button onClick={logout} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
              Sign out
            </button>
          </div>
        </div>
      </header>

      {queueSummary && (
        <div className="max-w-7xl mx-auto px-6 pt-4">
          <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4">
            <div className="flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Pill text="AI batch summary" cls="bg-indigo-100 text-indigo-800" />
                  <Pill text={`priority: ${queueSummary.priority}`} cls={SEV_PILL[queueSummary.priority]} />
                  <span className="text-[10px] text-slate-400 font-mono ml-1">advisory · log {queueSummary.ai_audit_log_id.slice(0, 8)}</span>
                </div>
                <p className="text-sm text-slate-800 font-medium">{queueSummary.narrative}</p>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
                  <span>{queueSummary.stats.total} open</span>
                  <span>·</span>
                  <span>{queueSummary.stats.affected_loans} loans affected</span>
                  <span>·</span>
                  <span>{queueSummary.stats.source_conflicts} source conflicts</span>
                  {Object.entries(queueSummary.stats.by_severity).map(([sev, n]) => (
                    <span key={sev}><Pill text={`${n} ${sev}`} cls={SEV_PILL[sev]} /></span>
                  ))}
                </div>
                {queueSummary.stats.top_rules.length > 0 && (
                  <p className="text-xs text-slate-500 mt-1">
                    Top rules: {queueSummary.stats.top_rules.slice(0, 3).map(([r, n]) => `${r} (${n})`).join(", ")}
                  </p>
                )}
              </div>
              <button onClick={() => setQueueSummary(null)} className="text-xs text-slate-400 hover:text-slate-600">dismiss</button>
            </div>
          </div>
        </div>
      )}

      {/* NL Rule Generation panel */}
      {showNlPanel && (
        <div className="max-w-7xl mx-auto px-6 pt-4">
          <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Pill text="AI: generate rule skeleton" cls="bg-violet-100 text-violet-800" />
                <Pill text="advisory only" cls="bg-violet-50 text-violet-600" />
              </div>
              <button onClick={() => { setShowNlPanel(false); setNlResult(null); }}
                className="text-xs text-slate-400 hover:text-slate-600">dismiss</button>
            </div>
            <p className="text-xs text-slate-500 mb-3">
              Describe a validation rule in plain English. The AI generates an advisory rule skeleton —
              review it carefully before adding to <code>validation_rules.json</code>.
            </p>
            <div className="flex gap-2">
              <input
                className="flex-1 border border-violet-300 rounded-lg px-3 py-2 text-sm bg-white"
                placeholder='e.g. "flag loans where interest rate exceeds 30%"'
                value={nlInput}
                onChange={(e) => setNlInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && nlInput.trim()) nlRule.mutate(nlInput.trim()); }}
              />
              <button
                disabled={!nlInput.trim() || nlRule.isPending}
                onClick={() => nlRule.mutate(nlInput.trim())}
                className="rounded-lg bg-violet-600 text-white px-4 py-2 text-sm font-medium disabled:opacity-50 hover:bg-violet-700"
              >
                {nlRule.isPending ? "Generating…" : "Generate"}
              </button>
            </div>

            {nlResult && (
              <div className="mt-4 rounded-lg border border-violet-200 bg-white p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Pill text="rule skeleton" cls="bg-violet-100 text-violet-800" />
                  {nlResult.degraded && <Pill text="degraded" cls="bg-red-100 text-red-700" />}
                  <span className="text-[10px] font-mono text-slate-400 ml-auto">log {nlResult.ai_audit_log_id.slice(0, 8)}</span>
                </div>
                <p className="text-sm text-slate-700 mb-3">{nlResult.output.explanation}</p>
                <div className="space-y-2">
                  {nlResult.output.generated_rules.map((rule, i) => (
                    <div key={i} className="rounded-lg bg-slate-50 border border-slate-200 p-3 font-mono text-xs text-slate-800">
                      <pre className="whitespace-pre-wrap">{JSON.stringify(rule, null, 2)}</pre>
                    </div>
                  ))}
                </div>
                {nlResult.output.note && (
                  <p className="text-[11px] text-amber-700 mt-2 italic">{nlResult.output.note}</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-12 gap-6">
        {/* Queue panel */}
        <section className="col-span-4">
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="p-4 border-b border-slate-100">
              <h2 className="text-sm font-semibold text-slate-700 mb-3">Exception Queue</h2>
              <div className="flex flex-col gap-2">
                <div className="flex gap-2">
                  <select
                    className="border border-slate-300 rounded-lg px-2 py-1.5 text-xs flex-1 bg-white"
                    value={filters.severity}
                    onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
                  >
                    <option value="">All severity</option>
                    <option>high</option><option>medium</option><option>low</option>
                  </select>
                  <select
                    className="border border-slate-300 rounded-lg px-2 py-1.5 text-xs flex-1 bg-white"
                    value={filters.status}
                    onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                  >
                    <option value="">All status</option>
                    <option value="open">open</option>
                    <option value="in_review">in review</option>
                    <option value="ignored">ignored</option>
                    <option value="resolved">resolved</option>
                  </select>
                </div>
                <input
                  className="border border-slate-300 rounded-lg px-2 py-1.5 text-xs w-full"
                  placeholder="search loan / borrower id…"
                  value={filters.q}
                  onChange={(e) => setFilters({ ...filters, q: e.target.value })}
                />
              </div>
            </div>

            {queue.isLoading && <p className="text-xs text-slate-500 p-4">Loading…</p>}
            {queue.data && queue.data.items.length === 0 && (
              <p className="text-xs text-slate-500 p-4">No exceptions match the current filters.</p>
            )}

            <ul className="divide-y divide-slate-100 max-h-[68vh] overflow-auto">
              {queue.data?.items.map((e) => (
                <li key={e.id}>
                  <button
                    data-testid="exception-item"
                    onClick={() => setSelected(e)}
                    className={`w-full text-left px-4 py-3 transition-colors ${selected?.id === e.id ? "bg-indigo-50 border-l-2 border-indigo-500" : "hover:bg-slate-50 border-l-2 border-transparent"}`}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      <Pill text={e.severity.toUpperCase()} cls={SEV_PILL[e.severity]} />
                      <Pill text={e.status} cls={STATUS_PILL[e.status]} />
                    </div>
                    <p className="text-xs font-semibold text-slate-800 leading-snug">{e.exception_type.replace(/_/g, " ")}</p>
                    <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                      {e.loan_id ?? "(no loan id)"} {e.field ? `· ${e.field}` : ""}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
            {queue.data && (
              <p className="text-[10px] text-slate-400 px-4 py-2 border-t border-slate-100">{queue.data.total} total</p>
            )}
          </div>
        </section>

        {/* Detail panel */}
        <section className="col-span-8">
          {selected ? (
            <ExceptionDetail key={selected.id} exception={selected} onChange={refresh} />
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-16 text-center">
              <p className="text-slate-400 text-sm">Select an exception from the queue</p>
              <p className="text-xs text-slate-300 mt-1">Evidence, AI assistance, and decision tools will appear here</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function ExceptionDetail({ exception, onChange }: { exception: ExceptionItem; onChange: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const loan = useQuery({ queryKey: ["loan", exception.loan_pk], queryFn: () => api.getLoan(exception.loan_pk) });
  const recs = useQuery({ queryKey: ["ai", exception.loan_pk], queryFn: () => api.listAi(exception.loan_pk) });
  const history = useQuery({ queryKey: ["history", exception.loan_pk], queryFn: () => api.loanHistory(exception.loan_pk) });
  const [ver, setVer] = useState(exception.version);
  const [editVal, setEditVal] = useState("");
  const [comment, setComment] = useState("");

  function run<T>(p: Promise<T>, ok?: string) {
    setErr(null); setMsg(null);
    return p
      .then((r) => {
        if (ok) setMsg(ok);
        onChange();
        loan.refetch();
        recs.refetch();
        history.refetch();
        return r;
      })
      .catch((e) => {
        setErr(e instanceof ApiError ? `${e.status}: ${e.message}` : "failed");
        throw e;
      });
  }

  const ai = useMutation({
    mutationFn: (kind: string) => api.requestAi(exception.id, kind),
    onSuccess: () => { recs.refetch(); onChange(); },
    onError: (e) => setErr(e instanceof ApiError ? e.message : "AI failed"),
  });

  const prov = (loan.data?.field_provenance ?? []).find((p) => p.field === exception.field);
  const canonicalVal = prov?.canonical_value ?? loan.data?.[exception.field ?? ""] ?? null;
  const thisRecs = recs.data?.filter((r) => r.exception_id === exception.id) ?? [];
  const isSourceConflict = exception.exception_type === "source_conflict";

  return (
    <div className="space-y-4">
      {/* ── EXCEPTION ─────────────────────────────────────── */}
      <div className={`rounded-xl border-l-4 border border-slate-200 bg-white p-5 ${SEV_CLS[exception.severity]?.split(" ")[0].replace("bg-", "border-l-").replace("-100", "-400") ?? "border-l-slate-400"}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Pill text={exception.severity.toUpperCase()} cls={SEV_PILL[exception.severity]} />
            <Pill text={exception.status} cls={STATUS_PILL[exception.status]} />
            {exception.field && (
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-mono text-slate-600">{exception.field}</span>
            )}
          </div>
          <span className="text-[10px] text-slate-400 shrink-0">{new Date(exception.opened_at).toLocaleString()}</span>
        </div>

        <h2 className="mt-2 text-base font-bold text-slate-900">{exception.exception_type.replace(/_/g, " ")}</h2>
        <p className="text-xs text-slate-500 font-mono">{exception.rule_id}</p>

        {/* WHY DID THIS FAIL */}
        <div className="mt-4">
          <SectionHeader label="Why did this fail?" />
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
            <p className="text-sm text-slate-700">{exception.message}</p>
          </div>
        </div>

        {/* LOAN IDENTITY */}
        <div className="mt-3 flex gap-6 text-sm">
          <div>
            <span className="text-[10px] uppercase tracking-wide text-slate-400 block">Loan ID</span>
            <span className="font-mono font-medium">{exception.loan_id ?? "—"}</span>
          </div>
          {exception.field && canonicalVal != null && (
            <div>
              <span className="text-[10px] uppercase tracking-wide text-slate-400 block">Canonical Value</span>
              <span className="font-mono font-medium text-slate-900">{String(canonicalVal)}</span>
            </div>
          )}
          {exception.observed_value != null && (
            <div>
              <span className="text-[10px] uppercase tracking-wide text-slate-400 block">Observed Value</span>
              <span className="font-mono font-medium text-amber-700">{exception.observed_value}</span>
            </div>
          )}
        </div>
      </div>

      {/* ── SOURCE EVIDENCE / PROVENANCE ──────────────────── */}
      {prov && (
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <SectionHeader label="Source Evidence & Provenance" />
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">Raw source value</p>
              <p className="font-mono font-semibold text-slate-800 break-all">{String(prov.raw_value ?? "—")}</p>
              <p className="text-[10px] text-slate-400 mt-1">{prov.source_column}</p>
            </div>
            <div className="flex items-center justify-center text-slate-300 text-xl">→</div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">Canonical value</p>
              <p className="font-mono font-semibold text-slate-900 break-all">{String(prov.canonical_value ?? "—")}</p>
              <span className={`inline-block mt-1 rounded text-[10px] px-1.5 py-0.5 font-medium ${prov.status === "ok" ? "bg-emerald-100 text-emerald-700" : prov.status === "failed" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
                {prov.status}
              </span>
            </div>
          </div>
          {prov.transformation && (
            <p className="mt-2 text-[11px] text-slate-400 font-mono">transformation: {prov.transformation}</p>
          )}
        </div>
      )}

      {/* ── AI COPILOT ────────────────────────────────────── */}
      <div className="rounded-xl border border-indigo-200 bg-white p-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-indigo-900">AI Assistant</h3>
            <Pill text="advisory only" cls="bg-indigo-50 text-indigo-600" />
          </div>
          <div className="flex flex-wrap gap-2">
            {(isSourceConflict
              ? ["explain", "resolve_conflict", "classify_severity", "reviewer_note"]
              : ["explain", "suggest_correction", "classify_severity", "reviewer_note"]
            ).map((k) => (
              <button
                key={k}
                disabled={ai.isPending}
                onClick={() => ai.mutate(k)}
                className="rounded-lg border border-indigo-300 bg-indigo-50 text-indigo-800 px-2.5 py-1 text-xs font-medium hover:bg-indigo-100 disabled:opacity-50"
              >
                {k === "suggest_correction" ? "suggest"
                  : k === "resolve_conflict" ? "compare sources"
                  : k === "classify_severity" ? "classify severity"
                  : k}
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs text-slate-400 mb-3">
          AI suggestions are shown separately. Only your human decision is recorded as authoritative.
        </p>

        {ai.isPending && (
          <div className="rounded-lg bg-indigo-50 border border-indigo-200 p-3 text-sm text-indigo-700 animate-pulse">
            Requesting AI analysis…
          </div>
        )}

        {thisRecs.length === 0 && !ai.isPending && (
          <p className="text-xs text-slate-400 italic">No AI output yet. Click a button above to request analysis.</p>
        )}

        <div className="space-y-3 mt-2">
          {thisRecs.map((r) => (
            <div key={r.id} className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <Pill text={r.kind} cls="bg-indigo-100 text-indigo-800" />
                {r.degraded && <Pill text="degraded mode" cls="bg-red-100 text-red-700" />}
                {r.applied && <Pill text={`applied · ${r.disposition}`} cls="bg-emerald-100 text-emerald-700" />}
                <span className="text-[10px] text-slate-400 font-mono ml-auto">
                  mock · log {r.ai_audit_log_id.slice(0, 8)}
                </span>
              </div>

              {/* Severity classification — special display */}
              {r.kind === "classify_severity" && r.output.suggested_severity != null && (
                <div className="mb-2 flex items-center gap-3">
                  <span className="text-xs text-slate-500">Deterministic:</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${SEV_PILL[String(r.output.deterministic_severity)] ?? "bg-slate-100 text-slate-700"}`}>
                    {String(r.output.deterministic_severity).toUpperCase()}
                  </span>
                  <span className="text-slate-300">·</span>
                  <span className="text-xs text-slate-500">AI suggests:</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${SEV_PILL[String(r.output.suggested_severity)] ?? "bg-slate-100 text-slate-700"}`}>
                    {String(r.output.suggested_severity).toUpperCase()}
                  </span>
                  {r.output.agrees_with_engine ? (
                    <span className="text-xs text-emerald-600 font-medium">✓ agree</span>
                  ) : (
                    <span className="text-xs text-amber-600 font-medium">⚠ disagree</span>
                  )}
                  <span className="text-[10px] text-slate-400 ml-auto font-mono">advisory · deterministic is authoritative</span>
                </div>
              )}

              <p className="text-sm text-slate-800 leading-relaxed">
                {String(r.output.explanation ?? r.output.rationale ?? r.output.note ?? r.output.message ?? r.output.rationale ?? "")}
              </p>

              {/* Source conflict: side-by-side comparison */}
              <SourceComparison output={r.output} />

              {/* Confidence */}
              {r.output.confidence != null && (
                <p className="text-[11px] text-slate-500 mt-1">confidence: {String(r.output.confidence)}</p>
              )}

              {/* Accept / Reject suggestion */}
              {r.suggested_field && r.suggested_value != null && !r.applied && (
                <div className="mt-3 flex items-center gap-3 pt-2 border-t border-indigo-100">
                  <span className="text-xs text-slate-600">
                    Suggested: <span className="font-mono font-medium text-slate-900">{r.suggested_field} = {r.suggested_value}</span>
                  </span>
                  <div className="flex gap-2 ml-auto">
                    <button
                      onClick={() => run(api.applyAi(r.id, "accepted"), "Applied AI suggestion")}
                      className="rounded-lg bg-emerald-600 text-white px-3 py-1 text-xs font-medium hover:bg-emerald-700"
                    >
                      Accept AI suggestion
                    </button>
                    <button
                      onClick={() => run(api.applyAi(r.id, "rejected"), "AI suggestion rejected")}
                      className="rounded-lg border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── HUMAN DECISION ────────────────────────────────── */}
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <SectionHeader label="Reviewer decision" sub="Human review is required — AI cannot decide" />

        <div className="space-y-4">
          {/* Exception status actions */}
          <div>
            <p className="text-xs text-slate-500 mb-2">Exception status</p>
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={() => run(api.reviewException(exception.id, "start_review", ver).then((r) => setVer(r.version)), "Started review")}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
              >
                Start review
              </button>
              <button
                onClick={() => run(api.reviewException(exception.id, "ignore", ver).then((r) => setVer(r.version)), "Ignored exception")}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
              >
                Ignore exception
              </button>
            </div>
          </div>

          {/* Field edit */}
          {exception.field && (
            <div>
              <p className="text-xs text-slate-500 mb-2">Edit field value</p>
              <div className="flex items-center gap-2">
                <input
                  className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm flex-1 font-mono"
                  placeholder={`New value for ${exception.field}…`}
                  value={editVal}
                  onChange={(e) => setEditVal(e.target.value)}
                />
                <button
                  disabled={!editVal}
                  onClick={() => run(api.editField(exception.loan_pk, exception.field!, editVal), "Field edited & re-validated")}
                  className="rounded-lg bg-slate-800 text-white px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-slate-900"
                >
                  Apply edit
                </button>
              </div>
            </div>
          )}

          {/* Comment */}
          <div>
            <p className="text-xs text-slate-500 mb-2">Add comment</p>
            <div className="flex items-center gap-2">
              <input
                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm flex-1"
                placeholder="Reviewer comment…"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <button
                disabled={!comment}
                onClick={() => run(api.addComment(exception.loan_pk, comment, exception.id), "Comment added").then(() => setComment(""))}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-slate-50"
              >
                Add comment
              </button>
            </div>
          </div>

          {/* Loan decision */}
          <div className="border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500 mb-2">Loan decision</p>
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={() => run(api.loanDecision(exception.loan_pk, "approve"), "Loan approved")}
                className="rounded-lg bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-700"
              >
                Approve loan
              </button>
              <button
                onClick={() => run(api.loanDecision(exception.loan_pk, "reject"), "Loan rejected")}
                className="rounded-lg bg-red-600 text-white px-4 py-2 text-sm font-medium hover:bg-red-700"
              >
                Reject loan
              </button>
              <button
                onClick={() => run(api.loanDecision(exception.loan_pk, "request_correction"), "Correction requested")}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
              >
                Request correction
              </button>
              <button
                onClick={() => run(api.verify(exception.loan_pk).then((v) => setMsg(`Verified v${v.version} · hash ${v.record_hash.slice(0, 12)}…`)))}
                className="rounded-lg bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-700"
              >
                Verify loan
              </button>
            </div>
          </div>

          {err && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{err}</div>
          )}
          {msg && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-sm text-emerald-700 font-medium">{msg}</div>
          )}
        </div>
      </div>

      {/* ── HISTORY / AUDIT ───────────────────────────────── */}
      {history.data && history.data.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <SectionHeader label="Review history" sub={`${history.data.length} entries`} />
          <ol className="space-y-2">
            {history.data.map((h) => (
              <li key={h.id} className="flex items-start gap-3 text-sm">
                <span className="shrink-0 mt-0.5 h-2 w-2 rounded-full bg-slate-300 ring-4 ring-white" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-800">{h.action.replace(/_/g, " ")}</span>
                    {h.field && <span className="font-mono text-xs text-slate-500">{h.field}</span>}
                    {h.new_value && (
                      <span className="text-xs text-slate-500">→ <code>{h.new_value}</code></span>
                    )}
                  </div>
                  {h.comment && <p className="text-xs text-slate-500 italic mt-0.5">"{h.comment}"</p>}
                  <p className="text-[10px] text-slate-400">{h.reviewer_id} · {new Date(h.created_at).toLocaleString()}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
