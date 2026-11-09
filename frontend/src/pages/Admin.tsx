import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ErrorBox, Footer, Header, Loading, Screen } from "../components/Chrome";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

interface Status {
  org: { name: string; client_label: string; nps_target: number; osat_target: number; thumb_ratio: number; leaderboard_min_n: number; leaderboard_size: number; support_contact: string; crisis_resources: string };
  counts: Record<string, number>;
  llm: { provider: string; model: string };
  runs: { id: number; kind: string; filename: string; rows_ok: number; rows_bad: number; errors: { row: number; error: string }[]; at: string | null }[];
}
interface ReviewItem { survey_id: number; sid: string; date: string; nps: number; comment: string; bucket: string; category: string | null; confidence: number; source: string }
interface AdminUser { id: number; email: string; full_name: string; role: string; scope_name: string | null; is_active: boolean; last_login_at: string | null }

export function AdminPage() {
  const { user } = useAuth();
  const [st, setSt] = useState<Status | null>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [review, setReview] = useState<{ categories: Record<string, string[]>; items: ReviewItem[] } | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [org, setOrg] = useState<Status["org"] | null>(null);

  const load = useCallback(() => {
    api.get<Status>("/api/admin/status").then((s) => { setSt(s); setOrg(s.org); }).catch((e) => setErr(e.message));
    api.get<typeof review>("/api/admin/review").then(setReview).catch(() => {});
    api.get<AdminUser[]>("/api/admin/users").then(setUsers).catch(() => {});
  }, []);
  useEffect(load, [load]);

  async function run<T>(label: string, fn: () => Promise<T>, msg: (r: T) => string) {
    setBusy(label); setNote(null);
    try { const r = await fn(); setNote({ ok: true, text: msg(r) }); load(); }
    catch (e) { setNote({ ok: false, text: e instanceof Error ? e.message : "Failed" }); }
    finally { setBusy(""); }
  }

  function upload(kind: "agents" | "surveys", e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (!(form.get("file") as File)?.name) { setNote({ ok: false, text: "Choose a file first." }); return; }
    if (kind === "agents") form.set("create_logins", (e.currentTarget.elements.namedItem("create_logins") as HTMLInputElement).checked ? "true" : "false");
    run(`import-${kind}`, () => api.upload<{ rows_ok: number; rows_bad: number; logins_created?: { email: string; temp_password: string }[] }>(`/api/admin/import/${kind}`, form),
      (r) => `Imported ${r.rows_ok} rows, ${r.rows_bad} rejected.` + (r.logins_created?.length ? ` Created ${r.logins_created.length} logins (temporary passwords emailed / logged).` : ""));
  }

  return (
    <>
      <Header title="Admin" sub={`${st?.org.name ?? ""} · ${user?.client_label ?? ""}`} />
      {err ? <ErrorBox msg={err} /> : !st || !org ? <Loading /> : (
        <Screen><main>
          {note && <div className={`banner ${note.ok ? "met" : "below"}`}>{note.text}</div>}
          <div className="kpi-row">
            <div className="kpi"><div className="kpi-val">{st.counts.active_agents}</div><div className="kpi-lbl">Active agents</div></div>
            <div className="kpi"><div className="kpi-val">{st.counts.surveys.toLocaleString()}</div><div className="kpi-lbl">Surveys</div></div>
            <div className="kpi"><div className="kpi-val">{st.counts.unclassified}</div><div className="kpi-lbl">Unclassified detractors</div></div>
            <div className="kpi"><div className="kpi-val">{st.counts.needs_review}</div><div className="kpi-lbl">Awaiting review</div></div>
            <div className="kpi"><div className="kpi-val" style={{ fontSize: 14 }}>{st.llm.provider} · {st.llm.model}</div><div className="kpi-lbl">AI model</div></div>
          </div>

          <div className="section-title">Import data</div>
          <div className="grid-2">
            <form className="card" onSubmit={(e) => upload("agents", e)}>
              <div className="chart-title">1. Agent masterfile (CSV or Excel)</div>
              <p className="small-note">Columns: employee_ref, full_name, email, tl_name, om_name, start_date, go_live_date, status, leave_date, leave_type, leave_reason. Re-importing updates existing agents.</p>
              <input type="file" name="file" accept=".csv,.xlsx,.xls" className="field-input" />
              <label className="check"><input type="checkbox" name="create_logins" /> Create logins for new agents with an email</label>
              <button className="btn" disabled={!!busy}>{busy === "import-agents" ? "Importing…" : "Import agents"}</button>
            </form>
            <form className="card" onSubmit={(e) => upload("surveys", e)}>
              <div className="chart-title">2. Survey export (CSV or Excel)</div>
              <p className="small-note">Columns: sid, employee_ref (or email), date, nps (0–10), osat (1–5), comment, and optionally bucket + category if already classified. New detractors are classified automatically.</p>
              <input type="file" name="file" accept=".csv,.xlsx,.xls" className="field-input" />
              <button className="btn" disabled={!!busy}>{busy === "import-surveys" ? "Importing + classifying…" : "Import surveys"}</button>
            </form>
          </div>
          {st.runs.length > 0 && (
            <div className="table-scroll" style={{ marginTop: 12 }}>
              <table className="det-table"><thead><tr><th>When</th><th>Type</th><th>File</th><th>OK</th><th>Rejected</th><th>First errors</th></tr></thead>
                <tbody>{st.runs.map((r) => (
                  <tr key={r.id}><td>{r.at?.slice(0, 16).replace("T", " ")}</td><td>{r.kind}</td><td>{r.filename}</td><td>{r.rows_ok}</td><td>{r.rows_bad}</td>
                    <td className="small-note">{r.errors.slice(0, 3).map((e) => `row ${e.row}: ${e.error}`).join(" · ")}</td></tr>))}</tbody></table>
            </div>
          )}

          <div className="section-title">AI pipelines</div>
          <div className="card" style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn" disabled={!!busy} onClick={() => run("classify", () => api.post<{ classified: number; by_llm: number; by_keyword: number }>("/api/admin/classify"),
              (r) => `Classified ${r.classified} comments (${r.by_llm} by AI, ${r.by_keyword} by keyword fallback).`)}>{busy === "classify" ? "Classifying…" : "Classify new detractors"}</button>
            <button className="btn ghost" disabled={!!busy} onClick={() => run("reclassify", () => api.post<{ classified: number }>("/api/admin/classify?reclassify_keyword=true"),
              (r) => `Re-read ${r.classified} keyword-classified comments with AI.`)}>Re-read keyword guesses with AI</button>
            <button className="btn ghost" disabled={!!busy} onClick={() => run("attrition", () => api.post<{ train: { trained: boolean; holdout_auc?: number; reason?: string }; score: { scored: number; high: number; method: string } }>("/api/admin/models/attrition"),
              (r) => `Attrition model ${r.train.trained ? `trained (hold-out AUC ${r.train.holdout_auc ?? "n/a"})` : "not trained: " + r.train.reason}; scored ${r.score.scored} agents, ${r.score.high} high risk (${r.score.method}).`)}>{busy === "attrition" ? "Running…" : "Retrain + score attrition model"}</button>
          </div>

          <div className="section-title">Classification review queue ({review?.items.length ?? 0})</div>
          <div className="table-scroll" style={{ maxHeight: 420 }}>
            <table className="det-table"><thead><tr><th>Date</th><th>NPS</th><th>Comment</th><th>Current</th><th>Set to</th></tr></thead>
              <tbody>{review?.items.map((it) => <ReviewRow key={it.survey_id} it={it} cats={review.categories} onDone={load} />)}
                {!review?.items.length && <tr><td colSpan={5} className="small-note" style={{ padding: 14 }}>Nothing to review.</td></tr>}</tbody></table>
          </div>

          <div className="section-title">Organisation settings</div>
          <form className="card form-grid" onSubmit={(e) => { e.preventDefault(); run("org", () => api.patch("/api/admin/org", org), () => "Settings saved."); }}>
            <label>Organisation name<input className="field-input" value={org.name} onChange={(e) => setOrg({ ...org, name: e.target.value })} /></label>
            <label>Client / programme label<input className="field-input" value={org.client_label} onChange={(e) => setOrg({ ...org, client_label: e.target.value })} /></label>
            <label>NPS target<input className="field-input" type="number" value={org.nps_target} onChange={(e) => setOrg({ ...org, nps_target: Number(e.target.value) })} /></label>
            <label>OSAT target (%)<input className="field-input" type="number" value={org.osat_target} onChange={(e) => setOrg({ ...org, osat_target: Number(e.target.value) })} /></label>
            <label>Promoter : detractor thumb rule<input className="field-input" type="number" step="0.5" value={org.thumb_ratio} onChange={(e) => setOrg({ ...org, thumb_ratio: Number(e.target.value) })} /></label>
            <label>Leaderboard minimum surveys<input className="field-input" type="number" value={org.leaderboard_min_n} onChange={(e) => setOrg({ ...org, leaderboard_min_n: Number(e.target.value) })} /></label>
            <label className="wide">Who agents should contact for serious issues (used by the coach)<textarea className="field-input" rows={2} value={org.support_contact} onChange={(e) => setOrg({ ...org, support_contact: e.target.value })} /></label>
            <label className="wide">Crisis resources (shown word-for-word when the coach detects a crisis)<textarea className="field-input" rows={3} value={org.crisis_resources} onChange={(e) => setOrg({ ...org, crisis_resources: e.target.value })} /></label>
            <div className="wide"><button className="btn" disabled={!!busy}>Save settings</button></div>
          </form>

          <div className="section-title">Users ({users.length})</div>
          <NewUserForm onCreated={(msg) => { setNote({ ok: true, text: msg }); load(); }} onError={(m) => setNote({ ok: false, text: m })} />
          <div className="table-scroll" style={{ maxHeight: 460, marginTop: 12 }}>
            <table className="det-table"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Scope</th><th>Last sign-in</th><th></th></tr></thead>
              <tbody>{users.map((u) => (
                <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                  <td>{u.full_name}</td><td>{u.email}</td><td>{u.role}</td><td>{u.scope_name ?? ""}</td><td>{u.last_login_at?.slice(0, 10) ?? "never"}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button className="btn ghost sm" onClick={() => run("reset", () => api.patch<{ temp_password: string }>(`/api/admin/users/${u.id}`, { reset_password: true }),
                      (r) => `Temporary password for ${u.email}: ${r.temp_password} (they'll choose a new one at sign-in).`)}>Reset password</button>
                    {u.id !== user?.id && <button className="btn ghost sm" onClick={() => run("toggle", () => api.patch(`/api/admin/users/${u.id}`, { is_active: !u.is_active }),
                      () => `${u.email} ${u.is_active ? "deactivated" : "reactivated"}.`)}>{u.is_active ? "Deactivate" : "Reactivate"}</button>}
                  </td>
                </tr>))}</tbody></table>
          </div>
          <div style={{ marginTop: 10 }}>
            <button className="btn ghost" onClick={() => run("logins", () => api.post<{ created: unknown[] }>("/api/admin/users/agent-logins"), (r) => `Created ${r.created.length} agent logins.`)}>Create logins for all agents with an email</button>
          </div>
        </main></Screen>
      )}
      <Footer />
    </>
  );
}

function ReviewRow({ it, cats, onDone }: { it: ReviewItem; cats: Record<string, string[]>; onDone: () => void }) {
  const [val, setVal] = useState(it.bucket === "None" ? "None|" : `${it.bucket}|${it.category ?? ""}`);
  const save = () => {
    const [bucket, category] = val.split("|");
    api.post(`/api/admin/review/${it.survey_id}`, { bucket, category: category || null }).then(onDone).catch(() => {});
  };
  return (
    <tr>
      <td>{it.date}</td><td>{it.nps}</td><td>{it.comment || <span className="small-note">(blank)</span>}</td>
      <td><span className={`cat-chip ${it.bucket === "People" ? "people" : it.bucket === "Process" ? "process" : ""}`}>{it.category ?? it.bucket}</span>
        <div className="small-note">{it.source} · {Math.round(it.confidence * 100)}%</div></td>
      <td style={{ whiteSpace: "nowrap" }}>
        <select className="field-input review-select" value={val} onChange={(e) => setVal(e.target.value)}>
          <option value="None|">None / no usable cause</option>
          {Object.entries(cats).map(([b, list]) => <optgroup key={b} label={b}>{list.map((c) => <option key={c} value={`${b}|${c}`}>{c}</option>)}</optgroup>)}
        </select>
        <button className="btn sm" onClick={save}>Confirm</button>
      </td>
    </tr>
  );
}

function NewUserForm({ onCreated, onError }: { onCreated: (m: string) => void; onError: (m: string) => void }) {
  const [f, setF] = useState({ email: "", full_name: "", role: "tl", scope_name: "", agent_employee_ref: "" });
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api.post<{ temp_password: string }>("/api/admin/users", { ...f, scope_name: f.scope_name || null, agent_employee_ref: f.agent_employee_ref || null });
      onCreated(`Created ${f.email}. Temporary password: ${r.temp_password} (also emailed if SMTP is set up).`);
      setF({ email: "", full_name: "", role: "tl", scope_name: "", agent_employee_ref: "" });
    } catch (ex) { onError(ex instanceof Error ? ex.message : "Failed"); }
  }
  return (
    <form className="card form-grid" onSubmit={submit}>
      <label>Full name<input className="field-input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} required /></label>
      <label>Email<input className="field-input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required /></label>
      <label>Role<select className="field-input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
        <option value="agent">Agent</option><option value="tl">Team leader</option><option value="om">Operations manager</option><option value="admin">Admin</option></select></label>
      {(f.role === "tl" || f.role === "om") && <label>{f.role === "tl" ? "TL name" : "OM name"} as it appears in the data<input className="field-input" value={f.scope_name} onChange={(e) => setF({ ...f, scope_name: e.target.value })} required /></label>}
      {f.role === "agent" && <label>Employee ref (optional if email matches)<input className="field-input" value={f.agent_employee_ref} onChange={(e) => setF({ ...f, agent_employee_ref: e.target.value })} /></label>}
      <div className="wide"><button className="btn">Add user</button></div>
    </form>
  );
}
