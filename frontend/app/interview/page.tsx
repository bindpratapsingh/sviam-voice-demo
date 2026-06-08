"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function InterviewInner() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const roomRef = useRef<any>(null);
  const joinedRef = useRef(false);
  const credsRef = useRef<{ url: string; token: string } | null>(null);
  const [status, setStatus] = useState<"ready" | "connecting" | "connected" | "error">("ready");
  const [msg, setMsg] = useState("");
  const [gotAudio, setGotAudio] = useState(false);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!id) { router.push("/"); return; }
    const raw = typeof window !== "undefined" ? sessionStorage.getItem(`lk-${id}`) : null;
    if (!raw) { setStatus("error"); setMsg("Session expired. Go back and start a new interview."); return; }
    credsRef.current = JSON.parse(raw);
    return () => { try { roomRef.current?.disconnect(); } catch {} };
  }, [id, router]);

  // Resume LiveKit playback + force-play our audio element. Called on connect AND on every tap.
  async function playNow() {
    try { await roomRef.current?.startAudio(); } catch {}
    const el = audioRef.current;
    if (el) {
      el.muted = false;
      el.volume = 1;
      try { await el.play(); setPlaying(true); } catch (e) { console.error("[lk] play() blocked", e); setPlaying(false); }
    }
  }

  async function start() {
    const creds = credsRef.current;
    if (!creds) return;
    setStatus("connecting");
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach((t) => t.stop());
    } catch (e) {
      console.error("[lk] mic error", e);
      setStatus("error");
      setMsg("Microphone is blocked. Click the lock icon in the address bar → Site settings → Microphone → Allow, then reload.");
      return;
    }
    try {
      const { Room, RoomEvent, Track } = await import("livekit-client");
      const room = new Room();
      roomRef.current = room;
      room.on(RoomEvent.TrackSubscribed, (track: any, _pub: any, p: any) => {
        console.log("[lk] TrackSubscribed", track.kind, "from", p?.identity);
        if (track.kind === Track.Kind.Audio || track.kind === "audio") {
          setGotAudio(true);
          if (audioRef.current) { try { track.attach(audioRef.current); } catch (e) { console.error("[lk] attach", e); } }
          playNow();
        }
      });
      room.on(RoomEvent.Disconnected, () => { if (joinedRef.current) router.push(`/result/${id}`); });
      await room.connect(creds.url, creds.token);
      joinedRef.current = true;
      await room.localParticipant.setMicrophoneEnabled(true);
      await playNow();
      setStatus("connected");
    } catch (e: any) {
      console.error("[lk] join failed", e);
      setStatus("error");
      setMsg("Could not join the interview: " + (e?.message || String(e)));
    }
  }

  function end() {
    if (joinedRef.current && roomRef.current) roomRef.current.disconnect();
    else router.push(`/result/${id}`);
  }

  return (
    <div className="wrap">
      <div className="card" style={{ textAlign: "center" }}>
        <h1>Interview</h1>
        {/* Real audio sink we control + play directly. */}
        <audio ref={audioRef} autoPlay playsInline />

        {status === "ready" && (
          <>
            <p className="sub">Put on headphones, then start.</p>
            <button onClick={start} style={{ maxWidth: 280, margin: "8px auto 0" }}>▶ Start interview</button>
          </>
        )}
        {status === "connecting" && <p className="sub">Connecting to Aria…</p>}
        {status === "connected" && (
          <>
            <button
              onClick={playNow}
              style={{ background: playing ? "var(--accent)" : "var(--green)", fontSize: 18, padding: 16, margin: "4px auto 14px", maxWidth: 380 }}
            >
              🔊 {playing ? "Sound ON — tap again if you can't hear Aria" : "TAP HERE TO HEAR ARIA"}
            </button>
            <div className="live" style={{ justifyContent: "center", margin: "10px 0" }}>
              <span className="dot" /> Connected — just talk; interrupt Aria any time.
            </div>
            <p className="pill">Receiving Aria's audio: {gotAudio ? "✓" : "…"}</p>
            <button onClick={end} className="ghost" style={{ maxWidth: 240, margin: "12px auto 0" }}>End interview & see verdict</button>
          </>
        )}
        {status === "error" && (
          <>
            <p className="err">{msg}</p>
            <button onClick={() => router.push("/")} className="ghost" style={{ maxWidth: 200, margin: "20px auto 0" }}>Back</button>
          </>
        )}
      </div>
    </div>
  );
}

export default function InterviewPage() {
  return (
    <Suspense fallback={<div className="wrap"><div className="card">Loading…</div></div>}>
      <InterviewInner />
    </Suspense>
  );
}
