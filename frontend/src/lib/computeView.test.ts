import { describe, expect, it } from "vitest";
import { computeView, npsOf, osatOf, pickVariant, windowsFor } from "./computeView";
import type { AgentData, Coaching, Shared } from "./types";

const shared: Shared = { date_min: "2026-01-01", date_max: "2026-11-08", overall_nps: 21, overall_osat: 58.2, nps_target: 40,
  osat_target: 65, thumb_ratio: 3, client_label: "Demo", org_name: "Demo" };
const kb: Coaching = {
  people: { Unaccommodating: [{ headline: "h", guidance: "g", quick_win: "Repeat the issue back first." }] },
  process: { Billing: [{ carehub_area: "CareHub → Billing", what_it_means: "w", customer_tip: "Explain the bill line by line." }] },
  default_process: [{ carehub_area: "", what_it_means: "", customer_tip: "default" }], general_process_closer: "closer",
};
const data: AgentData = {
  agent_id: 1, agent: "Kyle Adams", tl: "TL", om: "OM", tenure: "365+ days", team_nps: 20, hist_avg_monthly_n: 20, is_bottom_quartile: false,
  all_rows: [{ date: "2026-11-02", nps: 10, osat: 5 }, { date: "2026-11-03", nps: 9, osat: 5 }, { date: "2026-11-04", nps: 3, osat: 2 },
    { date: "2026-11-05", nps: 8, osat: 4 }, { date: "2026-10-01", nps: 0, osat: 1 }],
  detractors: [{ sid: "a", date: "2026-11-04", nps: 3, bucket: "People", category: "Unaccommodating", comment: "rude" },
    { sid: "b", date: "2026-10-01", nps: 0, bucket: "Process", category: "Billing", comment: "bill" }],
  win_candidates: [{ date: "2026-11-02", nps: 10, comment: "Brilliant, sorted in one call", score: 5 }], vuln: [],
};

describe("v2 metric parity", () => {
  it("computes NPS and OSAT like the backend", () => {
    expect(npsOf([{ nps: 10 }, { nps: 9 }, { nps: 9 }, { nps: 8 }, { nps: 6 }, { nps: 0 }])).toBe(16.7);
    expect(osatOf([{ osat: 5 }, { osat: 5 }, { osat: 4 }, { osat: 3 }])).toBe(50);
  });
  it("picks a stable template variant", () => {
    expect(pickVariant(["a", "b", "c"], "Kyle|Billing")).toBe(pickVariant(["a", "b", "c"], "Kyle|Billing"));
  });
  it("uses month-to-date after day 7", () => {
    expect(windowsFor(shared).DEFAULT_FROM).toBe("2026-11-01");
    expect(windowsFor({ ...shared, date_max: "2026-11-05" }).DEFAULT_FROM).toBe("2026-10-30");
  });
  it("builds the dashboard view for a range", () => {
    const v = computeView(data, "2026-11-01", "2026-11-08", shared, kb);
    expect(v.n).toBe(4);
    expect(v.nps).toBe(25);
    expect(v.bannerState).toBe("below");
    expect(v.categories[0].category).toBe("Unaccommodating");
    expect(v.actionPlan[0]).toBe("Repeat the issue back first.");
    expect(v.currentRatio).toBe(2);
    expect(v.wins).toHaveLength(1);
  });
});
