/* Line-for-line port of the v2 dashboard logic (computeView, npsOf, osatOf, pickVariant, monthPacingMsg).
   Keep it in step with backend/app/services/metrics.py so the UI and the AI coach always agree. */
import type { AgentData, Coaching, Detractor, PeopleTpl, ProcessTpl, Shared, SurveyRow, Vuln, Win } from "./types";

export function addDaysISO(dateStr: string, days: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

export interface Windows {
  DMIN: string; DMAX: string; MTD_FROM: string; USE_MTD_DEFAULT: boolean; DEFAULT_FROM: string; DEFAULT_TO: string;
}

/** Early in the month MTD is too thin, so default to a rolling 7 days; after day 7, month-to-date. */
export function windowsFor(shared: Shared): Windows {
  const DMAX = shared.date_max;
  const MTD_FROM = DMAX.slice(0, 7) + "-01";
  const USE_MTD_DEFAULT = Number(DMAX.slice(8, 10)) > 7;
  return { DMIN: shared.date_min, DMAX, MTD_FROM, USE_MTD_DEFAULT,
    DEFAULT_FROM: USE_MTD_DEFAULT ? MTD_FROM : addDaysISO(DMAX, -6), DEFAULT_TO: DMAX };
}

export function npsOf(rows: { nps: number | null }[]): number | null {
  const v = rows.map((r) => r.nps).filter((x): x is number => x !== null && x !== undefined);
  if (!v.length) return null;
  const p = v.filter((x) => x >= 9).length, d = v.filter((x) => x <= 6).length;
  return Math.round(((p - d) / v.length) * 1000) / 10;
}

export function osatOf(rows: { osat: number | null }[]): number | null {
  const v = rows.map((r) => r.osat).filter((x): x is number => x !== null && x !== undefined);
  if (!v.length) return null;
  return Math.round((v.filter((x) => x === 5).length / v.length) * 1000) / 10;
}

/* Deterministic variant picker: the same agent always sees the same phrasing for a category,
   different agents see different phrasing. */
export function stableHash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}
export function pickVariant<T>(list: T[] | undefined, seed: string): T | undefined {
  if (!Array.isArray(list) || !list.length) return undefined;
  if (list.length === 1) return list[0];
  return list[stableHash(seed) % list.length];
}

export type Category =
  | ({ bucket: "People"; category: string; count: number; pct: number } & PeopleTpl)
  | ({ bucket: "Process"; category: string; count: number; pct: number } & ProcessTpl);

export interface View {
  n: number; nps: number | null; osat: number | null;
  promotersN: number; detractorsN: number; passivesN: number;
  peopleTotal: number; processTotal: number; detTotal: number;
  categories: Category[]; npsMet: boolean; osatMet: boolean;
  bannerState: "none" | "met" | "partial" | "below"; bannerMsg: string;
  currentRatio: number | null; thumbMsg: string; diagnosis: string; actionPlan: string[];
  wins: Win[]; vulnInRange: Vuln[]; detsInRange: Detractor[]; hasProcess: boolean;
}

export function computeView(data: AgentData, from: string, to: string, SHARED: Shared, KB: Coaching): View {
  const rangeCheck = (d: string) => d >= from && d <= to;
  const rows: SurveyRow[] = data.all_rows.filter((r) => rangeCheck(r.date));
  const n = rows.length;
  const nps = npsOf(rows), osat = osatOf(rows);
  const promotersN = rows.filter((r) => r.nps !== null && r.nps >= 9).length;
  const detractorsN = rows.filter((r) => r.nps !== null && r.nps <= 6).length;
  const passivesN = rows.filter((r) => r.nps !== null && r.nps >= 7 && r.nps <= 8).length;

  const detsInRange = data.detractors.filter((d) => rangeCheck(d.date));
  const peopleCats: Record<string, number> = {}, processCats: Record<string, number> = {};
  detsInRange.forEach((d) => {
    if (d.bucket === "People" && d.category) peopleCats[d.category] = (peopleCats[d.category] || 0) + 1;
    else if (d.bucket === "Process" && d.category) processCats[d.category] = (processCats[d.category] || 0) + 1;
  });
  const peopleTotal = Object.values(peopleCats).reduce((a, b) => a + b, 0);
  const processTotal = Object.values(processCats).reduce((a, b) => a + b, 0);
  const detTotal = peopleTotal + processTotal;

  const categories: Category[] = [];
  Object.entries(peopleCats).forEach(([cat, cnt]) => {
    const pct = detTotal ? Math.round((cnt / detTotal) * 1000) / 10 : 0;
    const tpl = pickVariant(KB.people[cat], data.agent + "|" + cat) || {
      headline: "Flagged People-side opportunity",
      guidance: "Review recent cases in this category with your Team Leader.",
      quick_win: "Ask your TL for a recent example to review together.",
    };
    categories.push({ bucket: "People", category: cat, count: cnt, pct, ...tpl });
  });
  Object.entries(processCats).forEach(([cat, cnt]) => {
    const pct = detTotal ? Math.round((cnt / detTotal) * 1000) / 10 : 0;
    const tpl = pickVariant(KB.process[cat], data.agent + "|" + cat) || pickVariant(KB.default_process, data.agent + "|" + cat) ||
      { carehub_area: "", what_it_means: "", customer_tip: "" };
    categories.push({ bucket: "Process", category: cat, count: cnt, pct, ...tpl });
  });
  categories.sort((a, b) => b.count - a.count);

  const T = SHARED;
  const npsMet = nps !== null && nps >= T.nps_target;
  const osatMet = osat !== null && osat >= T.osat_target;
  const npsGap = nps !== null ? Math.round((T.nps_target - nps) * 10) / 10 : 0;
  const osatGap = osat !== null ? Math.round((T.osat_target - osat) * 10) / 10 : 0;
  let bannerState: View["bannerState"], bannerMsg: string;
  if (nps === null) { bannerState = "none"; bannerMsg = "Not enough surveys yet to call this one — keep going."; }
  else if (npsMet && osatMet) { bannerState = "met"; bannerMsg = `Both targets hit — NPS ${nps} vs ${T.nps_target}, OSAT ${osat}% vs ${T.osat_target}%. Solid. Keep doing what you're doing and don't let it slip.`; }
  else if (npsMet) { bannerState = "partial"; bannerMsg = `NPS target's hit (${nps} vs ${T.nps_target}) — nice. OSAT's still ${Math.abs(osatGap)} pts off ${T.osat_target}%, so that's the next thing to tighten up.`; }
  else if (osatMet) { bannerState = "partial"; bannerMsg = `OSAT target's hit (${osat}% vs ${T.osat_target}%) — good sign people are leaving happy. NPS is ${Math.abs(npsGap)} pts off ${T.nps_target}, so let's close that gap.`; }
  else { bannerState = "below"; bannerMsg = `Not there yet — NPS is ${Math.abs(npsGap)} pts off the ${T.nps_target} target, OSAT ${Math.abs(osatGap)} pts off ${T.osat_target}%. Nothing here that can't be turned around — see below.`; }

  const pn = promotersN, dn = detractorsN;
  const currentRatio = dn > 0 ? Math.round((pn / dn) * 10) / 10 : null;
  let thumbMsg: string;
  if (dn === 0 && pn > 0) thumbMsg = `Zero detractors against ${pn} promoters right now — that's exactly the shape you want, keep it up.`;
  else if (currentRatio !== null && currentRatio >= T.thumb_ratio) thumbMsg = `You're running about ${currentRatio} promoters for every detractor — at or above the ~${T.thumb_ratio}:1 ratio that tracks to the ${T.nps_target} NPS target. That's the engine behind your NPS — keep feeding it.`;
  else if (currentRatio !== null) thumbMsg = `Right now you're at roughly ${currentRatio} promoters for every detractor (${pn} promoters, ${dn} detractors). The thumb rule to track to the ${T.nps_target} target is about ${T.thumb_ratio} promoters for every 1 detractor — so either turning a few more calls into 9s and 10s, or taking your top opportunity category down a notch, gets you there faster than chasing one alone.`;
  else thumbMsg = "Not enough data yet to call a ratio — it'll sharpen up as more surveys come in.";

  const parts: string[] = [];
  if (nps !== null && data.team_nps !== null && data.team_nps !== undefined) {
    const delta = Math.round((nps - data.team_nps) * 10) / 10;
    parts.push(`Your NPS is ${nps} on ${n} surveys — ${Math.abs(delta)} pts ${delta >= 0 ? "above" : "below"} your ${data.om} team average of ${data.team_nps}.`);
  }
  if (nps !== null && T.overall_nps !== null) {
    const delta2 = Math.round((nps - T.overall_nps) * 10) / 10;
    parts.push(`That's ${Math.abs(delta2)} pts ${delta2 >= 0 ? "above" : "below"} the site-wide average of ${T.overall_nps}.`);
  }
  if (categories.length) {
    const top = categories[0];
    parts.push(`Your biggest driver is ${top.category} (${top.bucket}-side, ${top.count} case${top.count !== 1 ? "s" : ""}, ${top.pct}% of your classified cases) — more than anything else on your list.`);
  }
  if (categories.length > 1) { const s = categories[1]; parts.push(`${s.category} (${s.count} cases, ${s.pct}%) comes in second.`); }
  const diagnosis = parts.length ? parts.join(" ") : "Not enough classified detractor cases yet to call a clear pattern — worth keeping an eye on as more surveys land.";

  const tip = (c: Category) => (c.bucket === "People" ? c.quick_win : c.customer_tip);
  const actionPlan: string[] = [];
  if (categories.length) actionPlan.push(tip(categories[0]));
  if (categories.length > 1) actionPlan.push(tip(categories[1]));
  const topPeopleCat = categories.find((c) => c.bucket === "People");
  const topProcessCat = categories.find((c) => c.bucket === "Process");
  if (topPeopleCat && topProcessCat) {
    actionPlan.push(`Bring two things to your next 1:1 with your TL: a real example of ${topPeopleCat.category} (People) and one of ${topProcessCat.category} (Process) — talking both through beats reading about them, and you'll get sharper coaching on each.`);
  } else if (topPeopleCat) {
    actionPlan.push(`Bring a real example of ${topPeopleCat.category} to your next 1:1 with your TL — talking it through beats reading about it.`);
  } else if (topProcessCat) {
    actionPlan.push(`Bring a real example of ${topProcessCat.category} to your next 1:1 with your TL so you can get specific coaching on handling it well.`);
  } else {
    actionPlan.push("Bring one real example to your next 1:1 with your TL — talking it through beats reading about it.");
  }
  if (topProcessCat) {
    actionPlan.push(`When there's genuinely nothing more you can do on a ${topProcessCat.category} call, that's still yours to handle well — explain it plainly, give the one-line reason, and make the rest of the process as easy as possible for the customer rather than just ending the call there.`);
  }

  const wins = (data.win_candidates || []).filter((w) => rangeCheck(w.date))
    .sort((a, b) => b.score - a.score || b.comment.length - a.comment.length).slice(0, 3);
  const vulnInRange = (data.vuln || []).filter((v) => rangeCheck(v.date));
  const hasProcess = categories.some((c) => c.bucket === "Process");

  return { n, nps, osat, promotersN, detractorsN, passivesN, peopleTotal, processTotal, detTotal, categories, npsMet, osatMet,
    bannerState, bannerMsg, currentRatio, thumbMsg, diagnosis, actionPlan: actionPlan.filter(Boolean), wins, vulnInRange, detsInRange, hasProcess };
}

export function landingMotivation(view: View, SHARED: Shared, onDefault: boolean, useMtd: boolean): string {
  let motivation: string;
  if (view.nps === null) {
    motivation = "Not enough surveys yet to call it either way — give it a bit more time and check back in.";
  } else if (view.bannerState === "met") {
    motivation = `Congrats — you're hitting both targets! NPS ${view.nps} vs ${SHARED.nps_target}, OSAT ${view.osat}% vs ${SHARED.osat_target}%. ` +
      (view.categories.length ? `Keep working on ${view.categories[0].category} to push even further.` : `Keep doing exactly what you're doing.`);
  } else if (view.bannerState === "partial") {
    motivation = `Good signs — you've got one target locked in. ` +
      (view.categories.length ? `A bit more focus on ${view.categories[0].category} gets you the rest of the way.` : `Keep pushing on the gap above.`);
  } else {
    motivation = `Not at target yet, but nothing here that can't be turned around. ` +
      (view.categories.length ? `Start with ${view.categories[0].category} — that's your single biggest opportunity right now.` : `Let's go take a closer look.`);
  }
  if (onDefault && view.n > 0 && view.n < 8) {
    motivation += useMtd
      ? ` (Early days — just ${view.n} survey${view.n !== 1 ? "s" : ""} so far this month, so this will move around until there's more to go on.)`
      : ` (Light week — just ${view.n} survey${view.n !== 1 ? "s" : ""} in the last 7 days, so this will move around until there's more to go on.)`;
  }
  return motivation;
}

/* Live month-end pacing coach — only when viewing the current, in-progress month. Returns trusted HTML (<b> only). */
function daysInMonth(y: number, m: number) { return new Date(y, m, 0).getDate(); }
export function monthPacingMsg(data: AgentData, view: View, from: string, to: string, W: Windows, SHARED: Shared): string | null {
  if (!(from === W.MTD_FROM && to === W.DMAX)) return null;
  const [y, m, dayNow] = W.DMAX.split("-").map(Number);
  const daysLeft = daysInMonth(y, m) - dayNow;
  const monthName = new Date(y, m - 1, 1).toLocaleString("en-GB", { month: "long" });
  const histAvg = data.hist_avg_monthly_n;
  const T = SHARED.nps_target;
  if (histAvg === null || histAvg === undefined) {
    return `Not enough history yet to project your ${monthName} pace — check back once you've got a full month or two on record.`;
  }
  if (daysLeft <= 0) return null;
  const s = (k: number) => (k !== 1 ? "s" : "");
  if (view.nps !== null && view.nps >= T) {
    return `You're on track for ${monthName} — NPS ${view.nps} already clears the ${T} target, with ${daysLeft} day${s(daysLeft)} left and roughly ${Math.round(histAvg)} surveys a month for you typically. Keep doing what you're doing.`;
  }
  const remaining = Math.max(0, Math.round(histAvg - view.n));
  if (remaining === 0) {
    return `You're usually at full volume by this point in the month (~${Math.round(histAvg)} surveys/month historically), so there may not be a lot more ${monthName} data still to come — this month's result is close to where it'll land.`;
  }
  const projectedTotal = view.n + remaining;
  const pxNeeded = Math.max(0, Math.ceil((T / 100) * projectedTotal - view.promotersN + view.detractorsN));
  if (pxNeeded > remaining) {
    return `${daysLeft} day${s(daysLeft)} left in ${monthName}. Based on your usual pace (~${Math.round(histAvg)} surveys/month, about ${remaining} left to come), the ${T} target looks out of reach this month even with a perfect run — focus on finishing as strong as you can and carrying it into next month.`;
  }
  return `${daysLeft} day${s(daysLeft)} left in ${monthName}. Based on your usual ~${Math.round(histAvg)} surveys a month (about ${remaining} more expected), you need roughly <b>${pxNeeded} more promoter${s(pxNeeded)}</b> — and no new detractors — out of your remaining ~${remaining} surveys to hit the ${T} NPS target by month end.`;
}
