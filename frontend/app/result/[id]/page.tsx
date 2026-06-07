"use client";
import { useEffect, useState } from "react";
import { getScorecard, adminSession, adminConfigGet, adminConfigSet } from "../../../lib/api";

function badgeClass(v: string) {
  if (v === "Selected") return "badge sel";
  if (v === "Rejected") return "badge rej";
  return "badge bord";
}

export default function ResultPage({ params }: { params: { id: string } }) {
  const id = params.id;
  const [sc, setSc] = useState<any>(null);
  const [waited, setWaited] = useState(0);
  const [showAdmin, setShowAdmin] = useState(false);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const r = await getScorecard(id);
        if (stop) return;
        if (r?.status === "ready") setSc(r);
        else {
          setWaited((w) => w + 1);
          setTimeout(poll, 3000);
        }
      } catch {
        setTimeout(poll, 3000);
      }
    }
    poll();
    return () => { stop = true; };
  }, [id]);

  return (
    <div className="wrap">
      <div className="card">
        <h1>Interview result</h1>
        {!sc && <p className="sub">Generating your scorecard… ({waited * 3}s)</p>}
        {sc && (
          <>
            <span className={badgeClass(sc.verdict)}>{sc.verdict}</span>
            <p className="sub" style={{ marginTop: 16 }}>{sc.summary}</p>
          </>
        )}

        <button className="ghost" style={{ maxWidth: 220 }} onClick={() => setShowAdmin((s) => !s)}>
          {showAdmin ? "Hide reasoning" : "Show reasoning (admin)"}
        </button>

        {showAdmin && <AdminPanel sessionId={id} />}
      </div>
    </div>
  );
}

function AdminPanel({ sessionId }: { sessionId: string }) {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState(false);
  const [data, setData] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState("");
  const [edits, setEdits] = useState<any>({});

  async function unlock() {
    setErr("");
    try {
      const d = await adminSession(password, sessionId);
      setData(d);
      setAuthed(true);
      try { setCfg(await adminConfigGet(password)); } catch {}
    } catch {
      setErr("Wrong password.");
    }
  }

  async function saveKeys() {
    setSaved("");
    try {
      await adminConfigSet(password, edits);
      setSaved("Saved. New keys apply to the next interview.");
      setCfg(await adminConfigGet(password));
      setEdits({});
    } catch {
      setSaved("Save failed.");
    }
  }

  if (!authed) {
    return (
      <div style={{ marginTop: 18 }}>
        <label>Admin password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••" />
        <button onClick={unlock} style={{ maxWidth: 200 }}>Unlock</button>
        {err && <div className="err">{err}</div>}
      </div>
    );
  }

  const sc = data?.scorecard;
  const signals = sc?.signals || {};
  return (
    <div style={{ marginTop: 18 }}>
      <h2>Verdict reasoning</h2>
      {sc ? (
        <>
          <p className="pill">Recommendation: <b>{sc.recommendation}</b> → {sc.verdict}</p>
          <p className="sub">{sc.communication}</p>
          {!!(sc.strengths || []).length && <p className="sub"><b>Strengths:</b> {(sc.strengths || []).join(", ")}</p>}
          {!!(sc.areas_to_improve || []).length && <p className="sub"><b>To improve:</b> {(sc.areas_to_improve || []).join(", ")}</p>}
        </>
      ) : <p className="sub">No scorecard yet.</p>}

      <h2>Conversation signals</h2>
      <div className="signals">
        {Object.entries(signals).map(([k, v]) => (
          <span className="chip" key={k}>{k.replace(/_/g, " ")}: {String(v)}</span>
        ))}
        {!Object.keys(signals).length && <span className="pill">none</span>}
      </div>

      <h2>Transcript</h2>
      <div>
        {(data?.turns || []).map((t: any, i: number) => (
          <div className="turn" key={i}><span className="role">{t.role}</span><div>{t.content}</div></div>
        ))}
        {!(data?.turns || []).length && <p className="pill">no turns</p>}
      </div>

      <h2>API keys (live)</h2>
      <p className="pill">Current (masked): Deepgram {cfg?.deepgram_key || "—"} · ElevenLabs {cfg?.elevenlabs_key || "—"} · Groq {cfg?.groq_key || "—"} · provider {cfg?.llm_provider}</p>
      {(["deepgram_key", "elevenlabs_key", "groq_key", "elevenlabs_voice_id"] as const).map((k) => (
        <div key={k}>
          <label>{k.replace(/_/g, " ")}</label>
          <input value={edits[k] || ""} placeholder="leave blank to keep" onChange={(e) => setEdits({ ...edits, [k]: e.target.value })} />
        </div>
      ))}
      <button onClick={saveKeys} style={{ maxWidth: 220 }}>Save keys</button>
      {saved && <div className="pill" style={{ marginTop: 10 }}>{saved}</div>}
    </div>
  );
}
