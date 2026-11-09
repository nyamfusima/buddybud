import { useEffect, useMemo, useState } from "react";
import { DashboardScreen, ChoiceScreen, LandingScreen, LeaderboardScreen } from "../components/AgentScreens";
import { CoachChat } from "../components/CoachChat";
import { ErrorBox, Footer, Header, Loading, Screen } from "../components/Chrome";
import { api } from "../lib/api";
import { windowsFor } from "../lib/computeView";
import type { DashboardBundle, Leaderboard } from "../lib/types";

type ScreenId = "choice" | "landing" | "leaderboard" | "dash";

/** The agent experience: choice → overview → full dashboard, plus leaderboard and the coach chat. */
export function AgentHome() {
  const [bundle, setBundle] = useState<DashboardBundle | null>(null);
  const [lb, setLb] = useState<Leaderboard | null>(null);
  const [err, setErr] = useState("");
  const [screen, setScreen] = useState<ScreenId>("choice");
  const [range, setRangeState] = useState<[string, string] | null>(null);

  useEffect(() => {
    api.get<DashboardBundle>("/api/me/dashboard").then(setBundle).catch((e) => setErr(e.message));
    api.get<Leaderboard>("/api/leaderboard").then(setLb).catch(() => {});
  }, []);

  const W = useMemo(() => (bundle ? windowsFor(bundle.shared) : null), [bundle]);
  useEffect(() => { if (W && !range) setRangeState([W.DEFAULT_FROM, W.DEFAULT_TO]); }, [W, range]);

  const title = bundle ? bundle.data.agent : "Your Performance & Coach";
  const sub = bundle ? `${bundle.data.tl} team · ${bundle.data.om}'s group` : "";

  return (
    <>
      <Header title={title} sub={sub} />
      {err ? <ErrorBox msg={err} /> : !bundle || !W || !range ? <Loading label="Loading your numbers…" /> : (
        <>
          {screen === "choice" && <Screen key="choice"><ChoiceScreen onOverview={() => setScreen("landing")} onLeaderboard={() => setScreen("leaderboard")} /></Screen>}
          {screen === "landing" && <Screen key="landing">
            <LandingScreen bundle={bundle} W={W} from={range[0]} to={range[1]} setRange={(f, t) => setRangeState([f, t])}
              onBack={() => setScreen("choice")} onDash={() => setScreen("dash")} /></Screen>}
          {screen === "leaderboard" && <Screen key="lb"><LeaderboardScreen lb={lb} onBack={() => setScreen("choice")} /></Screen>}
          {screen === "dash" && <Screen key="dash">
            <DashboardScreen bundle={bundle} W={W} from={range[0]} to={range[1]} setRange={(f, t) => setRangeState([f, t])}
              onBack={() => setScreen("landing")} /></Screen>}
          <CoachChat data={bundle.data} shared={bundle.shared} />
        </>
      )}
      <Footer text={`Ellio CX · ${bundle?.shared.client_label ?? ""} Agent Coach · this page only ever shows your own data.`} />
    </>
  );
}
