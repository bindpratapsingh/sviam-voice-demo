"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { createSession } from "../lib/api";

const LANGS: [string, string][] = [
  ["en-US", "English (US)"],
  ["en-IN", "English (India)"],
  ["hi-IN", "Hindi"],
  ["te-IN", "Telugu"],
  ["ta-IN", "Tamil"],
];
const STRICT: [string, string][] = [
  ["friendly", "Friendly — encouraging, hints when stuck"],
  ["standard", "Standard — balanced, professional"],
  ["tough", "Tough — direct, demanding, no hints"],
  ["adversarial", "Adversarial — challenges everything"],
];

export default function Home() {
  const [language, setLanguage] = useState("en-US");
  const [strictness, setStrictness] = useState("standard");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const router = useRouter();

  async function start() {
    setLoading(true);
    setErr("");
    try {
      const { session_id, room_url } = await createSession(language, strictness);
      router.push(`/interview?room=${encodeURIComponent(room_url)}&id=${session_id}`);
    } catch (e: any) {
      setErr(e?.message || "Could not start the interview.");
      setLoading(false);
    }
  }

  return (
    <div className="wrap">
      <div className="card">
        <h1>SViam — AI Voice Interviewer</h1>
        <p className="sub">Pick a language and an interviewer style, then connect and talk. Aria runs a short technical interview and gives you a verdict at the end.</p>

        <label>Language</label>
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <label>Interviewer strictness</label>
        <select value={strictness} onChange={(e) => setStrictness(e.target.value)}>
          {STRICT.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <button onClick={start} disabled={loading}>
          {loading ? "Starting…" : "Connect & start interview"}
        </button>
        {err && <div className="err">{err}</div>}
        <p className="pill" style={{ marginTop: 18 }}>
          Tip: use Chrome/Edge with a mic. The first connect after a quiet period may take ~1 minute (free server waking up).
        </p>
      </div>
    </div>
  );
}
