import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import logoDark from "../assets/logo-dark.png";
import logoLight from "../assets/logo-light.png";
import robot from "../assets/robot.png";
import { useAuth } from "../lib/auth";
import { useTheme } from "../lib/theme";

export function Logos({ className = "" }: { className?: string }) {
  return (
    <>
      <img className={`logo-for-light ${className}`} src={logoLight} alt="Ellio" />
      <img className={`logo-for-dark ${className}`} src={logoDark} alt="Ellio" />
    </>
  );
}

export function Header({ title, sub }: { title: string; sub: string }) {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const isMgr = user && user.role !== "agent";
  return (
    <header>
      <div className="brand">
        <Logos />
        <div><h1>{title}</h1><p>{sub}</p></div>
      </div>
      <div className="hdr-actions">
        {isMgr && (
          <nav className="hdr-nav">
            <NavLink to="/team" className="nav-pill">Team</NavLink>
            {(user.role === "om" || user.role === "admin") && <NavLink to="/insights" className="nav-pill">Insights</NavLink>}
            {user.role === "admin" && <NavLink to="/admin" className="nav-pill">Admin</NavLink>}
          </nav>
        )}
        <button className="theme-btn" onClick={toggle}>{theme === "dark" ? "Light mode" : "Dark mode"}</button>
        <button className="theme-btn" onClick={() => { logout(); nav("/login"); }}>Sign out</button>
      </div>
    </header>
  );
}

/** Fade-in wrapper that reproduces v2's .screen / .rc-screen-in transition. */
export function Screen({ children, id }: { children: ReactNode; id?: string }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    window.scrollTo({ top: 0 });
    const r = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(r);
  }, []);
  return <div id={id} className={"screen active" + (shown ? " rc-screen-in" : "")}>{children}</div>;
}

export function RobotCompanion() {
  const [visible, setVisible] = useState(false);
  useEffect(() => { const t = setTimeout(() => setVisible(true), 60); return () => clearTimeout(t); }, []);
  return (
    <div id="robotCompanion" aria-hidden="true" className={visible ? "rc-visible" : ""}>
      <div className="rc-float"><img className="rc-body" src={robot} alt="" /></div>
    </div>
  );
}

/** v2's neon cursor glow. */
export function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let raf = 0, x = 0, y = 0, hide: number | undefined, burst: number | undefined;
    const tick = () => { raf = 0; if (ref.current) ref.current.style.transform = `translate(${x.toFixed(0)}px,${y.toFixed(0)}px)`; };
    const onMove = (e: MouseEvent) => {
      const el = ref.current;
      if (!el) return;
      x = e.clientX; y = e.clientY;
      el.classList.add("rc-glow-active", "rc-glow-burst");
      if (!raf) raf = requestAnimationFrame(tick);
      clearTimeout(burst); burst = window.setTimeout(() => el.classList.remove("rc-glow-burst"), 180);
      clearTimeout(hide); hide = window.setTimeout(() => el.classList.remove("rc-glow-active"), 650);
    };
    document.addEventListener("mousemove", onMove, { passive: true });
    return () => { document.removeEventListener("mousemove", onMove); cancelAnimationFrame(raf); };
  }, []);
  return <div id="rcCursorGlow" ref={ref} aria-hidden="true" />;
}

export function Footer({ text }: { text?: string }) {
  return <footer>{text ?? "BuddyBud AI Coach · Ellio CX · you only ever see the data your role allows."}</footer>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="landing-wrap"><div className="landing-hero"><p className="motivation">{label}</p></div></div>;
}

export function ErrorBox({ msg }: { msg: string }) {
  return <div className="landing-wrap"><div className="banner below" style={{ marginTop: 30 }}>{msg}</div></div>;
}
