import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { DashboardScreen } from "../components/AgentScreens";
import { ErrorBox, Footer, Header, Loading, Screen } from "../components/Chrome";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { windowsFor } from "../lib/computeView";
import type { DashboardBundle } from "../lib/types";

interface Row {
  agent_id: number; name: string; tl: string; om: string; status: string; tenure: string; tenure_days: number | null; is_new: boolean;
  n: number; nps: number | null; osat: number | null; detractors: number; people: number; process: number; top_category: string | null;
  risk: { risk: number; band: string; drivers: string[] } | null;
}
interface Overview {
  from: string; to: string; date_min: string; date_max: string; scope: { role: string; name: string | null };
  totals: { agents: number; n: number; nps: number | null; osat: number | null }; targets: { nps: number; osat: number }; agents: Row[];
}

type SortKey = "name" | "tenure_days" | "n" | "nps" | "osat" | "detractors" | "people" | "risk";

export function npsClass(v: number | null, target: number) {
  if (v === null) return "";
  return v >= target ? "good" : v >= target * 0.7 ? "warn" : "bad";
}

export function TeamPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState("");
  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const [draft, setDraft] = useState<{ from: string; to: string }>({ from: "", to: "" });
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "nps", dir: 1 });
  const [q, setQ] = useState("");

  useEffect(() => {
    const qs = range.from && range.to ? `?from=${range.from}&to=${range.to}` : "";
    api.get<Overview>(`/api/team/overview${qs}`).then((d) => { setData(d); setDraft({ from: d.from, to: d.to }); }).catch((e) => setErr(e.message));
  }, [range]);

  const rows = useMemo(() => {
    if (!data) return [];
    const val = (r: Row) => (sort.key === "risk" ? r.risk?.risk ?? -1 : (r[sort.key] as number | string | null));
    return data.agents
      .filter((r) => !q || (r.name + r.tl + (r.top_category ?? "")).toLowerCase().includes(q.toLowerCase()))
      .slice()
      .sort((a, b) => {
        const va = val(a), vb = val(b);
        if (va === null) return 1;
        if (vb === null) return -1;
        return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
      });
  }, [data, sort, q]);

  const th = (key: SortKey, label: string) => (
    <th className="sortable" onClick={() => setSort((s) => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : key === "name" ? 1 : -1 }))}>
      {label}{sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
    </th>
  );

  const scopeLabel = user?.role === "admin" ? "Whole site" : user?.role === "om" ? `${user.scope_name}'s group` : `${user?.scope_name}'s team`;
  const newCount = data?.agents.filter((a) => a.is_new).length ?? 0;
  const highRisk = data?.agents.filter((a) => a.risk?.band === "high").length ?? 0;

  return (
    <>
      <Header title="Team view" sub={`${scopeLabel} · ${user?.client_label ?? ""}`} />
      {err ? <ErrorBox msg={err} /> : !data ? <Loading /> : (
        <Screen>
          <div className="datefilter">
            <label>FROM</label><input type="date" value={draft.from} min={data.date_min} max={data.date_max} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
            <label>TO</label><input type="date" value={draft.to} min={data.date_min} max={data.date_max} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
            <button className="apply" onClick={() => setRange(draft)}>Apply filter</button>
            <button className="reset" onClick={() => setRange({})}>Reset to default</button>
            <span className="df-status">{data.totals.n.toLocaleString()} surveys in range</span>
          </div>
          <main>
            <p className="hello">{scopeLabel} — {data.from} to {data.to}</p>
            <p className="hello-sub">Click any agent to open their dashboard. Sorted lowest NPS first so coaching time goes where it matters.</p>
            <div className="kpi-row">
              <div className="kpi"><div className="kpi-val">{data.totals.agents}</div><div className="kpi-lbl">Active agents</div></div>
              <div className="kpi"><div className={`kpi-val ${npsClass(data.totals.nps, data.targets.nps)}`}>{data.totals.nps ?? "–"}</div><div className="kpi-lbl">NPS (target {data.targets.nps})</div></div>
              <div className="kpi"><div className="kpi-val">{data.totals.osat === null ? "–" : data.totals.osat + "%"}</div><div className="kpi-lbl">OSAT</div></div>
              <div className="kpi"><div className="kpi-val">{newCount}</div><div className="kpi-lbl">In first 90 days</div></div>
              <div className="kpi"><div className="kpi-val" style={{ color: highRisk ? "var(--red)" : undefined }}>{highRisk}</div><div className="kpi-lbl">High attrition risk</div></div>
            </div>
            {newCount > 0 && <div className="insight" style={{ margin: "14px 0" }}>
              {newCount} agent{newCount !== 1 ? "s are" : " is"} in the 0–90 day tenure trough, where NPS typically runs well below fully-ramped agents. Expect their numbers to lag and prioritise early support over correction.
            </div>}
            <div className="section-title">Agents</div>
            <input className="field-input" placeholder="Filter by name, TL or driver…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 320, marginBottom: 10 }} />
            <div className="table-scroll">
              <table className="det-table clickable">
                <thead><tr>
                  {th("name", "Agent")}{user?.role !== "tl" && <th>TL</th>}{th("tenure_days", "Tenure")}{th("n", "Surveys")}{th("nps", "NPS")}{th("osat", "OSAT")}
                  {th("detractors", "Detractors")}{th("people", "People / Process")}<th>Top driver</th>{th("risk", "Attrition risk")}
                </tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.agent_id} onClick={() => nav(`/team/agent/${r.agent_id}`)}>
                      <td><b>{r.name}</b>{r.is_new && <span className="mini-chip new">new</span>}</td>
                      {user?.role !== "tl" && <td>{r.tl}</td>}
                      <td>{r.tenure}</td><td>{r.n}</td>
                      <td><span className={`num ${npsClass(r.nps, data.targets.nps)}`}>{r.nps ?? "–"}</span></td>
                      <td>{r.osat === null ? "–" : r.osat + "%"}</td>
                      <td>{r.detractors}</td>
                      <td>{r.people} / {r.process}</td>
                      <td>{r.top_category ? <span className="cat-chip">{r.top_category}</span> : <span className="small-note">–</span>}</td>
                      <td>{r.risk ? <span className={`mini-chip risk-${r.risk.band}`} title={r.risk.drivers.join(", ")}>{r.risk.band}</span> : <span className="small-note">–</span>}</td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={10} className="small-note" style={{ padding: 14 }}>No agents in your scope yet.</td></tr>}
                </tbody>
              </table>
            </div>
            <p className="small-note" style={{ marginTop: 10 }}>Attrition risk is an early-warning signal for a supportive check-in, not a performance judgement. Hover a badge to see what's driving it.</p>
          </main>
        </Screen>
      )}
      <Footer />
    </>
  );
}

export function AgentViewPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [bundle, setBundle] = useState<DashboardBundle | null>(null);
  const [err, setErr] = useState("");
  const [range, setRange] = useState<[string, string] | null>(null);
  useEffect(() => {
    api.get<DashboardBundle>(`/api/team/agents/${id}/dashboard`).then((b) => {
      setBundle(b);
      const W = windowsFor(b.shared);
      setRange([W.DEFAULT_FROM, W.DEFAULT_TO]);
    }).catch((e) => setErr(e.message));
  }, [id]);
  const W = bundle ? windowsFor(bundle.shared) : null;
  return (
    <>
      <Header title={bundle ? bundle.data.agent : "Agent"} sub={bundle ? `${bundle.data.tl} team · ${bundle.data.om}'s group` : ""} />
      {err ? <ErrorBox msg={err} /> : !bundle || !W || !range ? <Loading /> : (
        <Screen>
          <DashboardScreen bundle={bundle} W={W} from={range[0]} to={range[1]} setRange={(f, t) => setRange([f, t])}
            onBack={() => nav("/team")} backLabel="← Back to team"
            viewerNote={`You're viewing ${bundle.data.agent.split(" ")[0]}'s dashboard exactly as they see it. Views are logged.${bundle.data.is_bottom_quartile ? " Currently in the bottom quartile on NPS (last 90 days)." : ""}`} />
        </Screen>
      )}
      <Footer />
    </>
  );
}
