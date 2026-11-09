import { useEffect, useRef, useState } from "react";
import { api, streamChat } from "../lib/api";
import type { AgentData, Shared } from "../lib/types";
import { npsOf, osatOf } from "../lib/computeView";

interface Msg { role: "user" | "coach"; text: string; typing?: boolean }

/** Floating "Ask your Coach" panel (v2 look), now backed by the server-side LangGraph coach with streaming. */
export function CoachChat({ data }: { data: AgentData; shared: Shared }) {
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [loaded, setLoaded] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const firstName = (data.agent || "there").split(" ")[0];
  const nps = npsOf(data.all_rows), osat = osatOf(data.all_rows);

  useEffect(() => { const t = setTimeout(() => setVisible(true), 400); return () => clearTimeout(t); }, []);
  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight }); }, [msgs, status]);

  const greet: Msg = { role: "coach", text: `Hey ${firstName}! I've got your numbers in front of me. Ask me about your performance, or just talk — I'm here either way.` };

  useEffect(() => {
    if (!open || loaded) return;
    setLoaded(true);
    api.get<{ messages: { role: string; content: string }[] }>("/api/coach/history")
      .then((h) => setMsgs([greet, ...h.messages.map((m) => ({ role: m.role === "user" ? "user" : "coach", text: m.content }) as Msg)]))
      .catch(() => setMsgs([greet]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, loaded]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setStatus("Coach is typing...");
    setMsgs((m) => [...m, { role: "user", text }, { role: "coach", text: "", typing: true }]);
    const setLast = (fn: (t: string) => string, typing = true) =>
      setMsgs((m) => { const c = m.slice(); const last = c[c.length - 1]; c[c.length - 1] = { ...last, text: fn(last.text), typing }; return c; });
    try {
      await streamChat(text, (e) => {
        if (e.type === "token") { setStatus(""); setLast((t) => t + e.data); }
        else if (e.type === "status") setStatus(e.data);
        else if (e.type === "reset") { setLast(() => ""); setStatus("Double-checking the numbers…"); }
        else if (e.type === "done") setLast(() => e.data.text, false);
        else if (e.type === "error") setLast(() => e.data, false);
      });
    } catch (err) {
      setLast(() => (err instanceof Error ? err.message : "Sorry, something went wrong reaching the coaching service. Check your connection and try again."), false);
    } finally {
      setBusy(false);
      setStatus("");
      setMsgs((m) => m.map((x) => (x.typing ? { ...x, typing: false } : x)));
      inputRef.current?.focus();
    }
  }

  async function clear() {
    await api.del("/api/coach/history").catch(() => {});
    setMsgs([greet]);
  }

  return (
    <>
      <button id="coachChatFab" type="button" className={visible ? "rc-visible" : ""} onClick={() => setOpen((o) => !o)}>
        <span className="dot" />Ask your Coach
      </button>
      <div id="coachChatPanel" className={open ? "rc-chat-open" : ""} aria-hidden={!open}>
        <div id="coachChatHead">
          <div>
            <div className="ttl">Your AI Coach</div>
            <div className="sub">NPS {nps ?? "n/a"} · OSAT {osat ?? "n/a"}% (full period)</div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button id="coachChatClear" type="button" title="Clear conversation" onClick={clear}>⟲</button>
            <button id="coachChatClose" type="button" onClick={() => setOpen(false)}>✕</button>
          </div>
        </div>
        <div id="coachChatBody" ref={bodyRef}>
          {msgs.map((m, i) => (
            m.typing && !m.text
              ? <div key={i} className="cc-msg typing">{status || "Coach is typing..."}</div>
              : <div key={i} className={`cc-msg ${m.role}`}>{m.text}</div>
          ))}
        </div>
        <div className="cc-note">Not a confidential or private channel — for anything serious, please reach out to a real person (your manager, HR, or your EAP line).</div>
        <div id="coachChatFoot">
          <textarea id="coachChatInput" ref={inputRef} rows={1} value={input} placeholder="Ask about your numbers, or just talk..."
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <button id="coachChatSend" type="button" disabled={busy} onClick={send}>Send</button>
        </div>
      </div>
    </>
  );
}
