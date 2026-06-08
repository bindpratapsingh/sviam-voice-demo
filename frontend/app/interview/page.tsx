"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function InterviewInner() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const roomRef = useRef<any>(null);
  const joinedRef = useRef(false);
  const credsRef = useRef<{ url: string; token: string } | null>(null);
  const [status, setStatus] = useState<"ready" | "connecting" | "connected" | "error">("ready");
  const [msg, setMsg] = useState("");
  const [botPresent, setBotPresent] = useState(false);
  const [gotAudio, setGotAudio] = useState(false);
  const [soundOn, setSoundOn] = useState(false);

  useEffect(() => {
    if (!id) { router.push("/"); return; }
    const raw = typeof window !== "undefined" ? sessionStorage.getItem(`lk-${id}`) : null;
    if (!raw) { setStatus("error"); setMsg("Session expired. Go back and start a new interview."); return; }
    credsRef.current = JSON.parse(raw);
    return () => {
      document.removeEventListener("click", unlockAudio);
      try { roomRef.current?.disconnect(); } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, router]);

  // Force-play every audio element + resume LiveKit playback. Safe to call repeatedly.
  async function unlockAudio() {
    try { await roomRef.current?.startAudio(); } catch {}
    document.querySelectorAll("audio").forEach((a) => {
      a.muted = false;
      a.play?.().catch(() => {});
    });
    if (roomRef.current?.canPlaybackAudio !== false) setSoundOn(true);
  }

  function attachAudio(track: any) {
    try {
      const el = track.attach();
      el.autoplay = true;
      el.muted = false;
      el.play?.().catch(() => {});
      document.body.appendChild(el);
      setGotAudio(true);
    } catch (e) { console.error("attach failed", e); }
  }

  async function start() {
    const creds = credsRef.current;
    if (!creds) return;
    setStatus("connecting");

    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach((t) => t.stop());
    } catch (e) {
      console.error("mic error", e);
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
        if (track.kind === Track.Kind.Audio || track.kind === "audio") { attachAudio(track); unlockAudio(); }
      });
      room.on(RoomEvent.ParticipantConnected, () => setBotPresent(true));
      room.on(RoomEvent.Disconnected, () => { if (joinedRef.current) router.push(`/result/${id}`); });
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => setSoundOn(!!room.canPlaybackAudio));

      await room.connect(creds.url, creds.token);
      joinedRef.current = true;
      room.remoteParticipants.forEach((p: any) => {
        setBotPresent(true);
        p.trackPublications.forEach((pub: any) => { if (pub.track && pub.kind === "audio") attachAudio(pub.track); });
      });
      await room.localParticipant.setMicrophoneEnabled(true);
      await unlockAudio();
      // Any tap anywhere also force-unlocks audio (covers browser autoplay blocks).
      document.addEventListener("click", unlockAudio);
      setStatus("connected");
    } catch (e: any) {
      console.error("join failed", e);
      setStatus("error");
      setMsg("Could not join the interview: " + (e?.message || String(e)));
    }
  }

  function end() {
    if (joinedRef.current && roomRef.current) roomRef.current.disconnect();
    else router.push(`/result/${id}`);
  }

  const yn = (b: boolean) => (b ? "✓" : "…");
  return (
    <div className="wrap">
      <div className="card" style={{ textAlign: "center" }}>
        <h1>Interview</h1>

        {status === "ready" && (
          <>
            <p className="sub">Put on headphones, then start.</p>
            <button onClick={start} style={{ maxWidth: 280, margin: "8px auto 0" }}>▶ Start interview</button>
          </>
        )}
        {status === "connecting" && <p className="sub">Connecting to Aria… allow the microphone.</p>}
        {status === "connected" && (
          <>
            {!soundOn && (
              <button onClick={unlockAudio} style={{ background: "var(--green)", fontSize: 18, padding: 16, margin: "0 auto 14px", maxWidth: 360 }}>
                🔊 TAP HERE TO HEAR ARIA
              </button>
            )}
            <div className="live" style={{ justifyContent: "center", margin: "14px 0" }}>
              <span className="dot" /> Connected — just talk; interrupt Aria any time.
            </div>
            <p className="pill">Aria in room: {yn(botPresent)} · Receiving her audio: {yn(gotAudio)} · Sound on: {yn(soundOn)}</p>
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
