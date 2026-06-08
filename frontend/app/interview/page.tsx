"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function InterviewInner() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const roomRef = useRef<any>(null);
  const trackRef = useRef<any>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const joinedRef = useRef(false);
  const credsRef = useRef<{ url: string; token: string } | null>(null);
  const [status, setStatus] = useState<"ready" | "connecting" | "connected" | "error">("ready");
  const [msg, setMsg] = useState("");
  const [gotAudio, setGotAudio] = useState(false);
  const [diag, setDiag] = useState("");

  useEffect(() => {
    if (!id) { router.push("/"); return; }
    const raw = typeof window !== "undefined" ? sessionStorage.getItem(`lk-${id}`) : null;
    if (!raw) { setStatus("error"); setMsg("Session expired. Go back and start a new interview."); return; }
    credsRef.current = JSON.parse(raw);
    return () => { try { roomRef.current?.disconnect(); } catch {} try { ctxRef.current?.close(); } catch {} };
  }, [id, router]);

  // A short test beep — proves the output device works. Uses its OWN oscillator,
  // never touches Aria's track (so it can't hijack it from the <audio> element).
  async function beep() {
    try {
      const Ctx = (window.AudioContext || (window as any).webkitAudioContext);
      const ctx = ctxRef.current || new Ctx();
      ctxRef.current = ctx;
      await ctx.resume();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = 660;
      g.gain.value = 0.2;
      o.connect(g);
      g.connect(ctx.destination);
      o.start();
      o.stop(ctx.currentTime + 0.15);
    } catch {}
  }

  // Attach Aria's track to the real <audio> element and play it. The track is
  // NEVER routed through Web Audio, so nothing steals it.
  function attach() {
    const el = audioRef.current;
    if (el && trackRef.current) {
      try { trackRef.current.attach(el); } catch (e) { console.error("[lk] attach", e); }
    }
  }

  async function playAria() {
    let d = "";
    await beep();
    d += "beep ";
    try { await roomRef.current?.startAudio(); d += "startAudio✓ "; } catch { d += "startAudio✗ "; }
    d += "canPlay=" + roomRef.current?.canPlaybackAudio + " ";
    attach();
    const el = audioRef.current;
    if (el) {
      el.muted = false;
      el.volume = 1;
      try { await el.play(); d += "play✓ paused=" + el.paused; } catch (e: any) { d += "play✗:" + (e?.name || e); }
    } else { d += "no-element"; }
    setDiag(d);
  }

  async function start() {
    const creds = credsRef.current;
    if (!creds) return;
    setStatus("connecting");
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach((t) => t.stop());
    } catch {
      setStatus("error");
      setMsg("Microphone is blocked. Allow it via the address-bar lock icon and reload.");
      return;
    }
    try {
      const { Room, RoomEvent, Track } = await import("livekit-client");
      const room = new Room();
      roomRef.current = room;
      room.on(RoomEvent.TrackSubscribed, (track: any, _p: any, who: any) => {
        console.log("[lk] TrackSubscribed", track.kind, who?.identity);
        if (track.kind === Track.Kind.Audio || track.kind === "audio") {
          trackRef.current = track;
          setGotAudio(true);
          attach();
          audioRef.current?.play().catch(() => {});
        }
      });
      room.on(RoomEvent.Disconnected, () => { if (joinedRef.current) router.push(`/result/${id}`); });
      await room.connect(creds.url, creds.token);
      joinedRef.current = true;
      await room.localParticipant.setMicrophoneEnabled(true);
      setStatus("connected");
    } catch (e: any) {
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
            <button onClick={playAria} style={{ background: "var(--green)", fontSize: 18, padding: 16, margin: "4px auto 12px", maxWidth: 380 }}>
              🔊 TAP TO HEAR ARIA
            </button>
            <p className="pill">Aria audio received: {gotAudio ? "✓" : "…"}</p>
            {diag && <p className="pill" style={{ wordBreak: "break-all" }}>{diag}</p>}
            <div className="live" style={{ justifyContent: "center", margin: "10px 0" }}>
              <span className="dot" /> Connected — talk to Aria.
            </div>
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
