import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import logoLight from "../assets/logo-light.png";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { User } from "../lib/types";

function Gate({ title, intro, children }: { title: string; intro: ReactNode; children: ReactNode }) {
  return (
    <div className="gate-wrap">
      <div className="gate">
        <img src={logoLight} alt="Ellio" />
        <h1>{title}</h1>
        <p>{intro}</p>
        {children}
      </div>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr("");
    if (!email || !password) { setErr("Enter both your email and password."); return; }
    setBusy(true);
    try {
      const u = await login(email.trim().toLowerCase(), password);
      nav(u.role === "agent" ? "/" : "/team", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Gate title="Your Performance & Coach" intro="Sign in with your work email to see your own numbers and coaching.">
      <form onSubmit={submit}>
        <input type="email" placeholder="firstname.lastname@company.com" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="Password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Unlock my dashboard"}</button>
      </form>
      <div className="err">{err}</div>
      <div className="hint"><Link to="/forgot-password">Forgot your password?</Link></div>
    </Gate>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const r = await api.post<{ message: string }>("/api/auth/forgot-password", { email });
      setMsg(r.message);
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Something went wrong."); }
  }
  return (
    <Gate title="Reset your password" intro="Enter your work email and we'll send you a reset link.">
      {msg ? <p className="hint" style={{ fontSize: 13 }}>{msg}</p> : (
        <form onSubmit={submit}>
          <input type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <button type="submit">Send reset link</button>
        </form>
      )}
      <div className="err">{err}</div>
      <div className="hint"><Link to="/login">Back to sign in</Link></div>
    </Gate>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pw !== pw2) { setErr("Passwords don't match."); return; }
    try {
      await api.post("/api/auth/reset-password", { token: params.get("token"), new_password: pw });
      nav("/login");
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Reset failed."); }
  }
  return (
    <Gate title="Choose a new password" intro="At least 8 characters, with upper and lower case letters and a number.">
      <form onSubmit={submit}>
        <input type="password" placeholder="New password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <input type="password" placeholder="Confirm new password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
        <button type="submit">Set password</button>
      </form>
      <div className="err">{err}</div>
    </Gate>
  );
}

export function ChangePasswordPage() {
  const { user, setUser, logout } = useAuth();
  const nav = useNavigate();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pw !== pw2) { setErr("Passwords don't match."); return; }
    try {
      const u = await api.post<User>("/api/auth/change-password", { current_password: cur, new_password: pw });
      setUser(u);
      nav(u.role === "agent" ? "/" : "/team", { replace: true });
    } catch (ex) { setErr(ex instanceof Error ? ex.message : "Couldn't change password."); }
  }
  return (
    <Gate title={`Welcome${user ? ", " + user.full_name.split(" ")[0] : ""}`} intro="Before you start, choose your own password (8+ characters, upper and lower case, and a number).">
      <form onSubmit={submit}>
        <input type="password" placeholder="Temporary password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
        <input type="password" placeholder="New password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <input type="password" placeholder="Confirm new password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
        <button type="submit">Save and continue</button>
      </form>
      <div className="err">{err}</div>
      <div className="hint"><a href="#" onClick={(e) => { e.preventDefault(); logout(); }}>Sign out</a></div>
    </Gate>
  );
}
