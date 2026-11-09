export type Role = "agent" | "tl" | "om" | "admin";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  scope_name: string | null;
  agent_id: number | null;
  org_id: number;
  org_name: string;
  client_label: string;
  must_change_password: boolean;
}

export interface SurveyRow { date: string; nps: number | null; osat: number | null }
export interface Detractor { sid: string; date: string; nps: number; bucket: string | null; category: string | null; comment: string }
export interface Win { date: string; nps: number; comment: string; score: number }
export interface Vuln { sid: string; date: string; nps: number | null; comment: string }

/** The per-agent object — same shape as the decrypted record in v2. */
export interface AgentData {
  agent_id: number;
  agent: string;
  tl: string;
  om: string;
  tenure: string;
  all_rows: SurveyRow[];
  detractors: Detractor[];
  win_candidates: Win[];
  vuln: Vuln[];
  team_nps: number | null;
  hist_avg_monthly_n: number | null;
  is_bottom_quartile: boolean;
}

export interface Shared {
  date_min: string;
  date_max: string;
  overall_nps: number | null;
  overall_osat: number | null;
  nps_target: number;
  osat_target: number;
  thumb_ratio: number;
  client_label: string;
  org_name: string;
}

export interface PeopleTpl { headline: string; guidance: string; quick_win: string }
export interface ProcessTpl { carehub_area: string; what_it_means: string; customer_tip: string }

export interface Coaching {
  people: Record<string, PeopleTpl[]>;
  process: Record<string, ProcessTpl[]>;
  default_process: ProcessTpl[];
  general_process_closer: string;
}

export interface DashboardBundle { data: AgentData; shared: Shared; coaching: Coaching }

export interface LeaderboardEntry { display: string; nps: number; osat: number; n: number; rank: number }
export interface Leaderboard { window_from: string; window_to: string; use_mtd: boolean; min_n: number; entries: LeaderboardEntry[] }
