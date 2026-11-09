import { useEffect, useState, type ReactElement } from "react";
import { computeView, landingMotivation, monthPacingMsg, type View, type Windows } from "../lib/computeView";
import { palette, useTheme } from "../lib/theme";
import type { DashboardBundle, Leaderboard as LB } from "../lib/types";
import { CatChart, Gauge } from "./charts";
import { Logos } from "./Chrome";

/* ---------- shared date filter ---------- */
export function DateFilter({ from, to, W, inline, n, onApply, onReset, resetLabel }: {
  from: string; to: string; W: Windows; inline?: boolean; n: number;
  onApply: (f: string, t: string) => void; onReset: () => void; resetLabel: string;
}) {
  const [f, setF] = useState(from);
  const [t, setT] = useState(to);
  useEffect(() => { setF(from); setT(to); }, [from, to]);
  return (
    <div className={"datefilter" + (inline ? " inline" : "")}>
      <label>FROM</label><input type="date" value={f} min={W.DMIN} max={W.DMAX} onChange={(e) => setF(e.target.value)} />
      <label>TO</label><input type="date" value={t} min={W.DMIN} max={W.DMAX} onChange={(e) => setT(e.target.value)} />
      <button className="apply" onClick={() => onApply(f || W.DMIN, t || W.DMAX)}>Apply filter</button>
      <button className="reset" onClick={onReset}>{resetLabel}</button>
      <span className="df-status">{n.toLocaleString()} surveys in range</span>
    </div>
  );
}

/* ---------- choice screen ---------- */
export function ChoiceScreen({ onOverview, onLeaderboard }: { onOverview: () => void; onLeaderboard: () => void }) {
  return (
    <div className="landing-wrap">
      <div className="landing-hero">
        <Logos className="choice-logo" />
        <h2>My BuddyBud AI Coach</h2>
      </div>
      <div className="choice-grid">
        <button className="choice-btn" onClick={onOverview}>
          <div className="choice-icon">😊</div>
          <div className="choice-label">My Overview</div>
          <div className="choice-sub">Your own performance &amp; coaching</div>
        </button>
        <button className="choice-btn" onClick={onLeaderboard}>
          <div className="choice-icon">🏆</div>
          <div className="choice-label">Leaderboard</div>
          <div className="choice-sub">This site's top performers</div>
        </button>
      </div>
    </div>
  );
}

/* ---------- landing ---------- */
export function LandingScreen({ bundle, W, from, to, setRange, onBack, onDash }: {
  bundle: DashboardBundle; W: Windows; from: string; to: string; setRange: (f: string, t: string) => void;
  onBack: () => void; onDash: () => void;
}) {
  const { data, shared, coaching } = bundle;
  const view = computeView(data, from, to, shared, coaching);
  const firstName = data.agent.split(" ")[0];
  const onDefault = from === W.DEFAULT_FROM && to === W.DEFAULT_TO;
  const rangeNote = onDefault
    ? (W.USE_MTD_DEFAULT ? "Showing month to date: " : "Showing the last 7 days: ") + from + " to " + to
    : "Showing: " + from + " to " + to;
  return (
    <div className="landing-wrap">
      <button className="back-btn" onClick={onBack}>← Back</button>
      <div className="landing-hero">
        <div className="emoji">😊</div>
        <h2>Hey {firstName}!</h2>
        <p className="motivation">{landingMotivation(view, shared, onDefault, W.USE_MTD_DEFAULT)}</p>
        <p className="small-note" style={{ margin: "-14px 0 8px" }}>{rangeNote}</p>
      </div>
      <DateFilter inline from={from} to={to} W={W} n={view.n} onApply={setRange}
        onReset={() => setRange(W.DEFAULT_FROM, W.DEFAULT_TO)} resetLabel="Reset to default" />
      <div className="landing-gauges">
        <div className="gauge-card"><div className="gauge-label">NPS</div><Gauge small value={view.nps} target={shared.nps_target} /></div>
        <div className="gauge-card"><div className="gauge-label">OSAT</div><Gauge small value={view.osat} target={shared.osat_target} suffix="%" /></div>
      </div>
      <button className="go-btn" onClick={onDash}>See my full dashboard →</button>
    </div>
  );
}

/* ---------- leaderboard ---------- */
function Medal({ fill, ring }: { fill: string; ring: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M8 3 L6 9 L9.5 9 Z" fill={ring} /><path d="M16 3 L18 9 L14.5 9 Z" fill={ring} />
      <circle cx="12" cy="14" r="7.2" fill={fill} /><circle cx="12" cy="14" r="7.2" fill="none" stroke={ring} strokeWidth="1.1" />
      <path d="M12 10.2 L13.1 12.6 L15.7 12.9 L13.8 14.7 L14.3 17.3 L12 16 L9.7 17.3 L10.2 14.7 L8.3 12.9 L10.9 12.6 Z" fill={ring} opacity=".85" />
    </svg>
  );
}
function LbBadge({ rank }: { rank: number }): ReactElement {
  if (rank === 1) return <Medal fill="#F6C543" ring="#B8860B" />;
  if (rank === 2) return <Medal fill="#D7DBE0" ring="#8A8F98" />;
  if (rank === 3) return <Medal fill="#D79A63" ring="#8C5A2B" />;
  if (rank <= 5) return (<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 L14.2 8.6 L20 9.1 L15.6 12.9 L17 18.6 L12 15.4 L7 18.6 L8.4 12.9 L4 9.1 L9.8 8.6 Z" fill="var(--om-dark)" /></svg>);
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="var(--ink-faint)" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 17 L10 11 L14 15 L20 7" /><path d="M14 7 h6 v6" />
    </svg>
  );
}

export function LeaderboardScreen({ lb, onBack }: { lb: LB | null; onBack: () => void }) {
  return (
    <div className="landing-wrap" style={{ maxWidth: 820 }}>
      <button className="back-btn" onClick={onBack}>← Back</button>
      <div className="landing-hero">
        <div className="emoji">🏆</div>
        <h2>Leaderboard</h2>
        <p className="motivation">
          {lb ? `${lb.use_mtd ? "Month to date" : "Last 7 days"}: ${lb.window_from} to ${lb.window_to} · top ${lb.entries.length} of this site's agents with ${lb.min_n}+ surveys in range` : "Loading…"}
        </p>
      </div>
      <div>
        {lb?.entries.map((e) => (
          <div className="lb-row" key={e.rank}>
            <span className="lb-rank">#{e.rank}</span>
            <span className="lb-badge"><LbBadge rank={e.rank} /></span>
            <span className="lb-name">{e.display}</span>
            <span className="lb-stats">NPS <b>{e.nps}</b> &middot; OSAT {e.osat}% &middot; n={e.n}</span>
          </div>
        ))}
        {lb && !lb.entries.length && <p className="small-note">Nobody has enough surveys in this window yet.</p>}
      </div>
    </div>
  );
}

/* ---------- full dashboard (v2 renderDashboard) ---------- */
export function DashboardScreen({ bundle, W, from, to, setRange, onBack, backLabel = "← Back to overview", viewerNote }: {
  bundle: DashboardBundle; W: Windows; from: string; to: string; setRange: (f: string, t: string) => void;
  onBack: () => void; backLabel?: string; viewerNote?: string;
}) {
  const { theme } = useTheme();
  const { data, shared: S, coaching } = bundle;
  const view: View = computeView(data, from, to, S, coaching);
  const pal = palette(theme);
  const pacing = monthPacingMsg(data, view, from, to, W, S);
  const entries = (bucket: string) => Object.entries(
    view.categories.filter((c) => c.bucket === bucket).reduce<Record<string, number>>((o, c) => { o[c.category] = c.count; return o; }, {}),
  ).sort((a, b) => b[1] - a[1]);
  const peopleEntries = entries("People"), processEntries = entries("Process");
  const pPct = view.detTotal ? Math.round((view.peopleTotal / view.detTotal) * 1000) / 10 : 0;
  const qPct = view.detTotal ? Math.round((view.processTotal / view.detTotal) * 1000) / 10 : 0;
  const dets = view.detsInRange.slice().sort((a, b) => (a.date < b.date ? 1 : -1));

  return (
    <>
      <DateFilter from={from} to={to} W={W} n={view.n} onApply={setRange} onReset={() => setRange(W.DMIN, W.DMAX)} resetLabel="Reset to full period" />
      <main>
        <button className="back-btn" onClick={onBack}>{backLabel}</button>
        {viewerNote && <div className="insight" style={{ marginBottom: 16 }}>{viewerNote}</div>}
        <p className="hello">{viewerNote ? `${data.agent} — ` : "Your performance — "}{from} to {to}</p>
        <p className="hello-sub">{data.tenure || ""} tenure · {data.tl} / {data.om} · benchmarks (team/site averages) are full-period figures</p>

        <div className={`banner ${view.bannerState}`}>{view.bannerMsg}</div>

        <div className="card">
          <div className="gauge-row">
            <div className="gauge-card"><div className="gauge-label">NPS vs target ({S.nps_target})</div><Gauge value={view.nps} target={S.nps_target} /></div>
            <div className="gauge-card"><div className="gauge-label">OSAT vs target ({S.osat_target}%)</div><Gauge value={view.osat} target={S.osat_target} suffix="%" /></div>
          </div>
        </div>

        <div className="kpi-row">
          <div className="kpi"><div className="kpi-val">{view.n}</div><div className="kpi-lbl">Surveys</div></div>
          <div className="kpi"><div className="kpi-val" style={{ color: pal.green }}>{view.promotersN}</div><div className="kpi-lbl">Promoters</div></div>
          <div className="kpi"><div className="kpi-val">{view.passivesN}</div><div className="kpi-lbl">Passives</div></div>
          <div className="kpi"><div className="kpi-val" style={{ color: pal.red }}>{view.detractorsN}</div><div className="kpi-lbl">Detractors</div></div>
          <div className="kpi"><div className="kpi-val">{view.osat === null ? "–" : view.osat + "%"}</div><div className="kpi-lbl">OSAT</div></div>
        </div>

        <div className="card thumb-card">
          <div className="thumb-ratio">{view.currentRatio === null ? "–" : view.currentRatio + ":1"}</div>
          <div className="thumb-text"><b>The thumb rule:</b> aim for about <b>{S.thumb_ratio} promoters for every 1 detractor</b> to track to the {S.nps_target} NPS target. {view.thumbMsg}</div>
        </div>
        {pacing && <div className="pacing-card"><span className="pacing-icon">📅</span><span className="pacing-text" dangerouslySetInnerHTML={{ __html: pacing }} /></div>}

        <div className="section-title">Customers said this about {viewerNote ? "them" : "you"}</div>
        <div className="wins-grid">
          {view.wins.length ? view.wins.map((w, i) => (
            <div className="win-card" key={i}><div className="win-nps">NPS {w.nps} · {w.date}</div><div className="win-quote">“{w.comment}”</div></div>
          )) : <p className="small-note">No standout quotes in this range — keep racking up those 9s and 10s.</p>}
        </div>

        <div className="section-title">{viewerNote ? "AI coaching summary" : "Your AI Coach"}</div>
        <div className="coach-box">
          <div className="coach-head"><span className="dot" /><h3>What's driving {viewerNote ? "their" : "your"} numbers</h3></div>
          <p>{view.diagnosis}</p>
          <div className="coach-head"><span className="dot" /><h3>{viewerNote ? "Suggested action plan" : "Your action plan"}</h3></div>
          <ul className="action-list">{view.actionPlan.map((x, i) => <li key={i}>{x}</li>)}</ul>
          {view.hasProcess && <div className="small-note" style={{ marginTop: 10 }}>{coaching.general_process_closer}</div>}
        </div>

        <div className="section-title">{viewerNote ? "People vs Process split" : "Your People vs Process split"}</div>
        <div className="card">
          <div className="split-bar">
            {view.detTotal ? (<>
              <div className="seg people" style={{ width: `${pPct}%` }}>{pPct >= 12 ? pPct + "%" : ""}</div>
              <div className="seg process" style={{ width: `${qPct}%` }}>{qPct >= 12 ? qPct + "%" : ""}</div>
            </>) : <div className="seg" style={{ width: "100%", background: "var(--border)", color: "var(--ink-muted)" }}>No classified cases in this range</div>}
          </div>
          <div className="split-legend">
            <span><span className="dot people" />People {view.peopleTotal} ({pPct}%)</span>
            <span><span className="dot process" />Process {view.processTotal} ({qPct}%)</span>
          </div>
        </div>

        <div className="section-title">{viewerNote ? "Sub-categories" : "Your sub-categories"}</div>
        <div className="small-note" style={{ margin: "-4px 0 10px" }}>Bar labels show count and, in brackets, % of {viewerNote ? "total" : "your total"} classified cases in this range.</div>
        <div className="grid-2">
          <div className="card"><div className="chart-title">People</div><div className="chart-wrap"><CatChart entries={peopleEntries} color={pal.people} total={view.detTotal} /></div>{!peopleEntries.length && <p className="small-note">None in range.</p>}</div>
          <div className="card"><div className="chart-title">Process</div><div className="chart-wrap"><CatChart entries={processEntries} color={pal.process} total={view.detTotal} /></div>{!processEntries.length && <p className="small-note">None in range.</p>}</div>
        </div>

        <div className="section-title">Category-by-category coaching</div>
        <div className="cat-card-grid">
          {view.categories.length ? view.categories.map((c) => c.bucket === "People" ? (
            <div className="cat-card" key={c.category}>
              <div className="cat-top"><span className="cat-name">{c.category}</span><span className="cat-badge people">PEOPLE</span>
                <span className="cat-count">{c.count} case{c.count !== 1 ? "s" : ""} · {c.pct}% of {viewerNote ? "their" : "your"} cases</span></div>
              <div className="cat-headline">{c.headline}</div>
              <p>{c.guidance}</p>
              <div className="cat-win"><b>Quick win:</b> {c.quick_win}</div>
            </div>
          ) : (
            <div className="cat-card" key={c.category}>
              <div className="cat-top"><span className="cat-name">{c.category}</span><span className="cat-badge process">PROCESS</span>
                <span className="cat-count">{c.count} case{c.count !== 1 ? "s" : ""} · {c.pct}% of {viewerNote ? "their" : "your"} cases</span></div>
              {c.carehub_area && <div className="carehub-tag">{c.carehub_area}</div>}
              <p>{c.what_it_means}</p>
              <div className="cat-win"><b>What to tell the customer:</b> {c.customer_tip}</div>
            </div>
          )) : <p className="small-note">No classified People or Process opportunities in this range — nice and clean.</p>}
        </div>

        {view.vulnInRange.length > 0 && (<>
          <div className="section-title">Vulnerability &amp; safety flags</div>
          <div className="vuln-box">
            <b>Handle with extra care — {view.vulnInRange.length} case{view.vulnInRange.length !== 1 ? "s" : ""} flagged for vulnerability/safeguarding context:</b>
            <ul>{view.vulnInRange.slice(0, 10).map((v) => (
              <li key={v.sid}>Survey {v.sid} ({v.date}, NPS {v.nps}): {(v.comment || "").slice(0, 180)}{(v.comment || "").length > 180 ? "…" : ""}</li>
            ))}</ul>
            <div className="small-note" style={{ marginTop: 6 }}>Auto-flagged by keyword match (elderly/disability/safeguarding terms), not individually verified — use judgement.</div>
          </div>
        </>)}

        <div className="section-title">{viewerNote ? "Case list — this range" : "Your case list — this range"}</div>
        <div className="table-scroll" style={{ maxHeight: 480 }}>
          <table className="det-table">
            <thead><tr><th>Survey ID</th><th>Date</th><th>NPS</th><th>Category</th><th>Comment</th></tr></thead>
            <tbody>
              {dets.length ? dets.map((d) => (
                <tr key={d.sid}>
                  <td>{d.sid}</td><td>{d.date}</td><td>{d.nps}</td>
                  <td>{d.category ? <span className={`cat-chip ${d.bucket === "People" ? "people" : d.bucket === "Process" ? "process" : ""}`}>{d.category}</span> : <span className="small-note">unclassified</span>}</td>
                  <td>{d.comment}</td>
                </tr>
              )) : <tr><td colSpan={5} className="small-note" style={{ padding: 14 }}>No detractor cases in this range.</td></tr>}
            </tbody>
          </table>
        </div>
      </main>
    </>
  );
}
