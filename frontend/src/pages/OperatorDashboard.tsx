import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError, api, type UploadSummary } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function OperatorDashboard() {
  const { name, logout } = useAuth();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const servicerRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<UploadSummary | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const summary = useQuery({ queryKey: ["operator-summary"], queryFn: () => api.summary("data_operator") });
  const uploads = useQuery({ queryKey: ["uploads"], queryFn: () => api.listUploads() });
  const attention = useQuery({ queryKey: ["attention-loans"], queryFn: () => api.listAttentionLoans() });
  const details = useQuery({
    queryKey: ["upload", selectedId],
    queryFn: () => api.getUpload(selectedId as string),
    enabled: !!selectedId,
  });

  const [validateMsg, setValidateMsg] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadCsv(file),
    onSuccess: (data) => {
      setLast(data);
      setError(null);
      if (fileRef.current) fileRef.current.value = "";
      qc.invalidateQueries({ queryKey: ["uploads"] });
      qc.invalidateQueries({ queryKey: ["operator-summary"] });
      qc.invalidateQueries({ queryKey: ["attention-loans"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Upload failed"),
  });

  const servicerUpload = useMutation({
    mutationFn: (file: File) => api.uploadCsv(file, "servicer_update"),
    onSuccess: (data) => {
      setLast(data);
      setError(null);
      if (servicerRef.current) servicerRef.current.value = "";
      qc.invalidateQueries({ queryKey: ["uploads"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Servicer upload failed"),
  });

  const validate = useMutation({
    mutationFn: (sourceFileId: string) => api.validate(sourceFileId),
    onSuccess: (r) => {
      const t = r.totals as Record<string, unknown>;
      const bySev = (t.by_severity ?? {}) as Record<string, number>;
      setValidateMsg(
        `Validated ${r.loans_evaluated} loans (ruleset ${r.ruleset_version}): ` +
          `${bySev.high ?? 0} high · ${bySev.medium ?? 0} medium · ${bySev.low ?? 0} low`,
      );
      qc.invalidateQueries({ queryKey: ["operator-summary"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Validation failed"),
  });

  const s = summary.data as Record<string, unknown> | undefined;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold">Data Operator Dashboard</h1>
            <p className="text-xs text-slate-500">LoanTrust Copilot · {name}</p>
          </div>
          <button onClick={logout} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
            Sign out
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Stat cards */}
        <div className="grid grid-cols-4 gap-4">
          {[
            ["Uploads", s?.uploads, ""],
            ["Records imported", s?.records_imported, ""],
            ["Needs attention", s?.needs_attention, "text-amber-700"],
            ["Open exceptions", s?.corrections_needed, "text-red-700"],
          ].map(([label, val, cls]) => (
            <div key={label as string} className="rounded-lg bg-white border border-slate-200 p-4">
              <p className="text-xs uppercase tracking-wide text-slate-400">{label as string}</p>
              <p className={`text-2xl font-semibold mt-1 ${cls as string}`}>{val === undefined ? "—" : String(val)}</p>
            </div>
          ))}
        </div>

        {/* Upload */}
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="font-semibold mb-1">Upload loan tape</h2>
          <p className="text-sm text-slate-500 mb-4">CSV with the canonical loan columns. Raw rows are preserved immutably.</p>
          <div className="flex items-center gap-3">
            <input ref={fileRef} type="file" accept=".csv,text/csv" className="text-sm" />
            <button
              onClick={() => {
                const f = fileRef.current?.files?.[0];
                if (f) upload.mutate(f);
                else setError("Choose a CSV file first.");
              }}
              disabled={upload.isPending}
              className="rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              {upload.isPending ? "Uploading…" : "Upload & ingest"}
            </button>
          </div>
          <div className="mt-3 flex items-center gap-3 border-t border-slate-100 pt-3">
            <span className="text-xs text-slate-500">Second source (servicer feed):</span>
            <input ref={servicerRef} type="file" accept=".csv,text/csv" className="text-xs" />
            <button
              onClick={() => {
                const f = servicerRef.current?.files?.[0];
                if (f) servicerUpload.mutate(f);
                else setError("Choose a servicer CSV first.");
              }}
              disabled={servicerUpload.isPending}
              className="rounded border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-50"
            >
              {servicerUpload.isPending ? "Uploading…" : "Upload servicer feed"}
            </button>
          </div>
          {error && <p className="text-sm text-red-600 mt-3">{error}</p>}

          {last && (
            <div className={`mt-4 rounded-lg border p-4 ${last.duplicate ? "border-amber-300 bg-amber-50" : "border-emerald-300 bg-emerald-50"}`}>
              {last.duplicate ? (
                <p className="text-sm text-amber-800">
                  Duplicate content — reused existing upload <code>{last.original_upload_id}</code>. Raw evidence not re-stored.
                </p>
              ) : (
                <p className="text-sm text-emerald-800">
                  Imported <b>{last.imported_count}</b> / {last.row_count} rows · failed <b>{last.failed_count}</b>
                </p>
              )}
              <p className="text-xs text-slate-500 mt-1">file sha-256: <code>{last.file_hash.slice(0, 16)}…</code></p>
              {!last.duplicate && (
                <button onClick={() => validate.mutate(last.id)} disabled={validate.isPending}
                  className="mt-3 rounded-lg bg-indigo-600 text-white px-3 py-1.5 text-sm disabled:opacity-50">
                  {validate.isPending ? "Validating…" : "Run validation"}
                </button>
              )}
              {validateMsg && <p className="text-sm text-indigo-700 mt-2">{validateMsg}</p>}
              {last.failed_samples.length > 0 && (
                <ul className="mt-2 text-xs text-red-700 list-disc pl-5">
                  {last.failed_samples.map((f) => (
                    <li key={f.row_number}>row {f.row_number}: {f.reason}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Records needing normalization attention */}
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="font-semibold mb-1">Records needing attention</h2>
          <p className="text-sm text-slate-500 mb-4">Rows with fields that failed to parse or were flagged during normalization.</p>
          {attention.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {attention.isError && <p className="text-sm text-red-600">Failed to load.</p>}
          {attention.data && attention.data.items.length === 0 && (
            <p className="text-sm text-emerald-700">No normalization issues — all records are clean.</p>
          )}
          {attention.data && attention.data.items.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-400 text-xs uppercase">
                  <th className="py-2">Loan ID</th>
                  <th>Borrower</th>
                  <th>Issue fields</th>
                </tr>
              </thead>
              <tbody>
                {attention.data.items.map((l) => (
                  <tr key={l.id} className="border-t border-slate-100">
                    <td className="py-2">{l.loan_id ?? <span className="text-red-600 italic">missing</span>}</td>
                    <td className="text-slate-500">{l.borrower_id ?? "—"}</td>
                    <td>
                      {l.issue_fields.map((f) => (
                        <span key={f} className="inline-block mr-1 mb-1 rounded bg-amber-100 text-amber-800 px-1.5 py-0.5 text-xs">
                          {f}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Import history */}
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="font-semibold mb-4">Import history</h2>
          {uploads.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {uploads.isError && <p className="text-sm text-red-600">Failed to load import history.</p>}
          {uploads.data && uploads.data.items.length === 0 && (
            <p className="text-sm text-slate-500">No uploads yet.</p>
          )}
          {uploads.data && uploads.data.items.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-400 text-xs uppercase">
                  <th className="py-2">File</th>
                  <th>Rows</th>
                  <th>Imported</th>
                  <th>Failed</th>
                  <th>When</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {uploads.data.items.map((u) => (
                  <tr key={u.id} className="border-t border-slate-100">
                    <td className="py-2">
                      {u.filename} {u.duplicate && <span className="text-amber-600 text-xs">(dup)</span>}
                    </td>
                    <td>{u.row_count}</td>
                    <td>{u.imported_count}</td>
                    <td className={u.failed_count ? "text-red-600" : ""}>{u.failed_count}</td>
                    <td className="text-slate-500">{new Date(u.uploaded_at).toLocaleString()}</td>
                    <td>
                      <button
                        onClick={() => setSelectedId(selectedId === u.id ? null : u.id)}
                        className="text-slate-600 underline text-xs"
                      >
                        {selectedId === u.id ? "Hide" : "Details"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {selectedId && (
            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
              {details.isLoading && <p className="text-sm text-slate-500">Loading details…</p>}
              {details.isError && <p className="text-sm text-red-600">Failed to load upload details.</p>}
              {details.data && (
                <div className="text-sm">
                  <p className="font-medium">{details.data.filename}</p>
                  <p className="text-slate-600">
                    {details.data.imported_count}/{details.data.row_count} imported ·{" "}
                    {details.data.failed_count} failed · {details.data.byte_size} bytes
                  </p>
                  <p className="text-xs text-slate-500 mt-1">sha-256: <code>{details.data.file_hash}</code></p>
                  {details.data.failed_samples.length > 0 && (
                    <ul className="mt-2 text-xs text-red-700 list-disc pl-5">
                      {details.data.failed_samples.map((f) => (
                        <li key={f.row_number}>row {f.row_number}: {f.reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
