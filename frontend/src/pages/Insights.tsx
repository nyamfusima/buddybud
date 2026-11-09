import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BarChart, LineChart } from "../components/charts";
import { ErrorBox, Footer, Header, Loading, Screen } from "../components/Chrome";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { palette, useTheme } from "../lib/theme";
import { npsClass } from "./Team";

interface Curve { band: string; n: number; nps: number | null; osat: number | null; detractor_rate: number }
interface TlRow { tl: string; om: string; agents: number; n: number; nps: number | null; osat: number | null; expected_nps: number; residual: number | null;
  new_starter_share: number; people_share: number | null; top_category: string | null; flag: string }
interface NewTeam { tl: string; om: string; agents: number; new_share: number; median_go_live: string; leaves_trough_on: string; days_left_in_trough: number; nps_30d: number | null; n_30d: number }
interface Risk { agent_id: number; name: string; tl: string; risk: number; band: string; drivers: string[]; method: string }
interface Esc { months: { month: string; surveys: number; client: number; management: number; agent: number }[];
  categories: { category: string; owner: string; count: number; nps_impact_pts: number }[]; owner_totals: Record<string, number>; process_total?: number }
interface Summary {
  from: string; to: string; date_min: string; date_max: string;
  headline: { n: number; nps: number | null; osat: number | null; active_agents: number; leavers: number; involuntary_share: number | null; nps_target: number };
  tenure_curve: Curve[]; tl_outliers: TlRow[]; new_teams: NewTeam[]; attrition_risk: Risk[]; escalations: Esc;
}
interface Forecast {
  history: { month: string; actual_nps: number | null; expected_nps: number; n: number; new_starter_share: number }[];
  baseline: { month: string; expected_nps: number | null; headcount: number; new_starter_share: number }[];
  with_plan: { month: string; expected_nps: number | null; headcount: number; new_starter_share: number }[];
  monthly_hazards: Record<string, number>;
}

const OWNER_LABEL: Record<string, string> = { client: "Client-owned", management: "Management-owned", agent: "Agent-influenceable" };

export function InsightsPage() {
  const { user } = useAuth();
  const { theme } = useTheme();
  const pal = palette(theme);
  const nav = useNavigate();
  const [s, setS] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  const [waves, setWaves] = useState<{ go_live: string; count: number }[]>([]);
  const [fc, setFc] = useState<Forecast | null>(null);
  const [fcErr, setFcErr] = useState("");

  useEffect(() => { api.get<Summary>("/api/insights/summary").then(setS).catch((e) => setErr(e.message)); }, []);
  useEffect(() => {
    if (!s) return;
    if (!waves.length) {
      const d = new Date(s.date_max); d.setUTCMonth(d.getUTCMonth() + 1); d.setUTCDate(1);
      setWaves([{ go_live: d.toISOString().slice(0, 10), count: 30 }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s]);
  function runForecast() {
    setFcErr("");
    api.post<Forecast>("/api/insights/hiring-forecast", { planned: waves.filter((w) => w.go_live && w.count > 0), months: 6 })
      .then(setFc).catch((e) => setFcErr(e.message));
  }
  useEffect(() => { if (waves.length && !fc) runForecast(); /* first run */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waves.length]);

  return (
    <>
      <Header title="Insights" sub={`${user?.role === "admin" ? "Whole site" : user?.scope_name + "'s group"} · ${user?.client_label ?? ""}`} />
      {err ? <ErrorBox msg={err} /> : !s ? <Loading label="Crunching the numbers…" /> : (
        <Screen><main>
          <p className="hello">Why the target is being missed — and where to act</p>
          <p className="hello-sub">{s.from} to {s.to} · tenure-adjusted views compare each team to what its tenure mix alone would predict</p>

          <div className="kpi-row">
            <div className="kpi"><div className={`kpi-val ${npsClass(s.headline.nps, s.headline.nps_target)}`}>{s.headline.nps ?? "–"}</div><div className="kpi-lbl">NPS (target {s.headline.nps_target})</div></div>
            <div className="kpi"><div className="kpi-val">{s.headline.osat === null ? "–" : s.headline.osat + "%"}</div><div className="kpi-lbl">OSAT</div></div>
            <div className="kpi"><div className="kpi-val">{s.headline.n.toLocaleString()}</div><div className="kpi-lbl">Surveys</div></div>
            <div className="kpi"><div className="kpi-val">{s.headline.active_agents}</div><div className="kpi-lbl">Active agents</div></div>
            <div className="kpi"><div className="kpi-val">{s.headline.involuntary_share === null ? "–" : s.headline.involuntary_share + "%"}</div><div className="kpi-lbl">Leavers involuntary</div></div>
          </div>

          <div className="section-title">Tenure is the dominant driver</div>
          <div className="grid-2">
            <div className="card"><div className="chart-title">NPS by live-call tenure (whole site)</div>
              <div className="chart-wrap"><BarChart labels={s.tenure_curve.map((c) => c.band)} showValues
                series={[{ label: "NPS", data: s.tenure_curve.map((c) => c.nps), color: pal.om }]} yTitle="NPS" /></div></div>
            <div className="card"><div className="chart-title">Detractor rate by tenure (%)</div>
              <div className="chart-wrap"><BarChart labels={s.tenure_curve.map((c) => c.band)} showValues
                series={[{ label: "Detractor rate %", data: s.tenure_curve.map((c) => c.detractor_rate), color: pal.process }]} /></div></div>
          </div>

          {s.new_teams.length > 0 && (<>
            <div className="section-title">New-team watchlist — inside the 90-day trough</div>
            <div className="wins-grid">
              {s.new_teams.map((t) => (
                <div className="pacing-card" key={t.tl} style={{ margin: 0 }}>
                  <span className="pacing-icon">⚠️</span>
                  <span className="pacing-text"><b>{t.tl}</b> ({t.om}) — {t.agents} agents, {t.new_share}% new, went live around {t.median_go_live}.
                    {" "}Last 30 days NPS {t.nps_30d ?? "–"} on {t.n_30d} surveys. <b>{t.days_left_in_trough} days</b> until they're out of the trough ({t.leaves_trough_on}). Give them dedicated ramp-up coaching now.</span>
                </div>
              ))}
            </div>
          </>)}

          <div className="section-title">Team leaders vs what tenure predicts</div>
          <div className="small-note" style={{ margin: "-4px 0 10px" }}>Expected NPS = each team's survey mix by tenure band × the site's NPS for that band. The gap (actual − expected) is the coaching and management signal that tenure can't explain.</div>
          <div className="table-scroll">
            <table className="det-table">
              <thead><tr><th>Team leader</th><th>OM</th><th>Agents</th><th>Surveys</th><th>NPS</th><th>Expected</th><th>Gap</th><th>New-starter share</th><th>People share</th><th>Top driver</th></tr></thead>
              <tbody>{s.tl_outliers.map((r) => (
                <tr key={r.tl}>
                  <td><b>{r.tl}</b></td><td>{r.om}</td><td>{r.agents}</td><td>{r.n}</td>
                  <td><span className={`num ${npsClass(r.nps, s.headline.nps_target)}`}>{r.nps ?? "–"}</span></td>
                  <td>{r.expected_nps}</td>
                  <td><span className={`mini-chip gap-${r.flag}`}>{r.residual === null ? "–" : (r.residual > 0 ? "+" : "") + r.residual}</span></td>
                  <td>{r.new_starter_share}%</td><td>{r.people_share === null ? "–" : r.people_share + "%"}</td>
                  <td>{r.top_category ? <span className="cat-chip">{r.top_category}</span> : "–"}</td>
                </tr>))}</tbody>
            </table>
          </div>

          {(user?.role === "om" || user?.role === "admin") && (<>
            <div className="section-title">Hiring-wave forecaster</div>
            <div className="card">
              <p className="small-note" style={{ marginTop: 0 }}>Plan a hiring wave and see the NPS dip it causes before it happens. Uses the site's own tenure curve and monthly attrition by tenure band. The history line shows how well tenure mix alone explained past months.</p>
              <div className="wave-rows">
                {waves.map((w, i) => (
                  <div className="wave-row" key={i}>
                    <label>Go-live</label><input className="field-input" type="date" value={w.go_live} onChange={(e) => setWaves(waves.map((x, j) => (j === i ? { ...x, go_live: e.target.value } : x)))} />
                    <label>Agents</label><input className="field-input" type="number" min={0} max={500} value={w.count} style={{ width: 90 }} onChange={(e) => setWaves(waves.map((x, j) => (j === i ? { ...x, count: Number(e.target.value) } : x)))} />
                    <button className="btn ghost" onClick={() => setWaves(waves.filter((_, j) => j !== i))}>Remove</button>
                  </div>
                ))}
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn ghost" onClick={() => setWaves([...waves, { go_live: s.date_max, count: 10 }])}>+ Add wave</button>
                  <button className="btn" onClick={runForecast}>Run forecast</button>
                </div>
                {fcErr && <div className="banner below">{fcErr}</div>}
              </div>
              {fc && (<>
                <div className="chart-title" style={{ marginTop: 16 }}>Projected NPS from tenure mix — next 6 months</div>
                <div className="chart-wrap" style={{ height: 260 }}>
                  <LineChart labels={fc.baseline.map((b) => b.month)} yTitle="Expected NPS"
                    refLine={{ value: s.headline.nps_target, label: `Target ${s.headline.nps_target}` }}
                    series={[{ label: "No new hiring", data: fc.baseline.map((b) => b.expected_nps), color: pal.om },
                             { label: "With planned waves", data: fc.with_plan.map((b) => b.expected_nps), color: pal.red, dashed: true }]} />
                </div>
                <div className="chart-title" style={{ marginTop: 16 }}>Back-test: actual NPS vs tenure-mix expectation</div>
                <div className="chart-wrap" style={{ height: 240 }}>
                  <LineChart labels={fc.history.map((h) => h.month)}
                    series={[{ label: "Actual", data: fc.history.map((h) => h.actual_nps), color: pal.people },
                             { label: "Expected from tenure mix", data: fc.history.map((h) => h.expected_nps), color: pal.amber, dashed: true }]} />
                </div>
              </>)}
            </div>
          </>)}

          <div className="section-title">Process detractors — who owns the fix</div>
          <div className="grid-2">
            <div className="card"><div className="chart-title">Process detractors by owner, per month</div>
              <div className="chart-wrap" style={{ height: 260 }}>
                <BarChart stacked labels={s.escalations.months.map((m) => m.month)}
                  series={[{ label: OWNER_LABEL.client, data: s.escalations.months.map((m) => m.client), color: pal.process },
                           { label: OWNER_LABEL.management, data: s.escalations.months.map((m) => m.management), color: pal.amber },
                           { label: OWNER_LABEL.agent, data: s.escalations.months.map((m) => m.agent), color: pal.people }]} />
              </div></div>
            <div className="card"><div className="chart-title">Client escalation list — quantified ask</div>
              <div className="table-scroll" style={{ maxHeight: 262 }}>
                <table className="det-table"><thead><tr><th>Category</th><th>Owner</th><th>Detractors</th><th>NPS pts</th></tr></thead>
                  <tbody>{s.escalations.categories.slice(0, 14).map((c) => (
                    <tr key={c.category}><td>{c.category}</td><td>{OWNER_LABEL[c.owner]}</td><td>{c.count}</td><td>+{c.nps_impact_pts}</td></tr>))}</tbody></table>
              </div>
              <p className="small-note">NPS pts = how much site NPS would rise if those detractors had been passives instead.</p>
            </div>
          </div>

          <div className="section-title">Attrition early warning</div>
          <div className="table-scroll" style={{ maxHeight: 420 }}>
            <table className="det-table clickable"><thead><tr><th>Agent</th><th>TL</th><th>Risk</th><th>What's driving it</th></tr></thead>
              <tbody>{s.attrition_risk.length ? s.attrition_risk.map((r) => (
                <tr key={r.agent_id} onClick={() => nav(`/team/agent/${r.agent_id}`)}>
                  <td><b>{r.name}</b></td><td>{r.tl}</td>
                  <td><span className={`mini-chip risk-${r.band}`}>{Math.round(r.risk * 100)}%</span></td>
                  <td>{r.drivers.join(", ") || <span className="small-note">no single driver</span>}</td>
                </tr>)) : <tr><td colSpan={4} className="small-note" style={{ padding: 14 }}>No scores yet — an admin can run the model from the Admin page.</td></tr>}</tbody></table>
          </div>
          <p className="small-note">Use this to start supportive conversations early. It is decision support, never grounds for disciplinary action.</p>
        </main></Screen>
      )}
      <Footer />
    </>
  );
}
