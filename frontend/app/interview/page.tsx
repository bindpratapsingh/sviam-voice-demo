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
  // Live diagnostics shown on screen:
  const [botPresent, setBotPresent] = useState(false);
  const [gotAudio, setGotAudio] = useState(false);
  const [soundOn, setSoundOn] = useState(false);

  useEffect(() => {
    if (!id) {
      router.push("/");
      return;
    }
    const raw = typeof window !== "undefined" ? sessionStorage.getItem(`lk-${id}`) : null;
    if (!raw) {
      setStatus("error");
      setMsg("Session expired. Go back and start a new interview.");
      return;
    }
    credsRef.current = JSON.parse(raw);
    return () => { try { roomRef.current?.disconnect(); } catch {} };
  }, [id, router]);

  function attachAudio(track: any) {
    try {
      const el = track.attach();
      el.autoplay = true;
      (el as HTMLMediaElement).play?.().then(() => setSoundOn(true)).catch(() => {});
      document.body.appendChild(el);
      setGotAudio(true);
      console.log("[lk] attached remote audio track");
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

      room.on(RoomEvent.TrackSubscribed, (track: any, _pub: any, participant: any) => {
        console.log("[lk] TrackSubscribed", track.kind, "from", participant?.identity);
        if (track.kind === Track.Kind.Audio || track.kind === "audio") attachAudio(track);
      });
      room.on(RoomEvent.ParticipantConnected, (p: any) => {
        console.log("[lk] ParticipantConnected", p?.identity);
        setBotPresent(true);
      });
      room.on(RoomEvent.Disconnected, () => { if (joinedRef.current) router.push(`/result/${id}`); });
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        setSoundOn(!!room.canPlaybackAudio);
        console.log("[lk] canPlaybackAudio", room.canPlaybackAudio);
      });

      await room.connect(creds.url, creds.token);
      joinedRef.current = true;
      console.log("[lk] connected; remote participants:", room.remoteParticipants.size);

      // Pick up anything already in the room (bot may have joined first).
      room.remoteParticipants.forEach((p: any) => {
        setBotPresent(true);
        p.trackPublications.forEach((pub: any) => { if (pub.track && pub.kind === "audio") attachAudio(pub.track); });
      });

      try { await room.startAudio(); setSoundOn(true); } catch { /* needs the button */ }
      await room.localParticipant.setMicrophoneEnabled(true);
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
  async function enableSound() {
    try { await roomRef.current?.startAudio(); setSoundOn(true); } catch {}
  }

  const yn = (b: boolean) => (b ? "✓" : "…");
  return (
    <div className="wrap">
      <div className="card" style={{ textAlign: "center" }}>
        <h1>Interview</h1>

        {status === "ready" && (
          <>
            <p className="sub">Put on headphones (so Aria doesn't echo into your mic), then start.</p>
            <button onClick={start} style={{ maxWidth: 280, margin: "8px auto 0" }}>▶ Start interview</button>
          </>
        )}
        {status === "connecting" && <p className="sub">Connecting to Aria… allow the microphone.</p>}
        {status === "connected" && (
          <>
            <div className="live" style={{ justifyContent: "center", margin: "14px 0" }}>
              <span className="dot" /> Connected — just talk; interrupt Aria any time.
            </div>
            <p className="pill">Aria in room: {yn(botPresent)} &nbsp;·&nbsp; Receiving her audio: {yn(gotAudio)} &nbsp;·&nbsp; Sound on: {yn(soundOn)}</p>
            <button onClick={enableSound} style={{ maxWidth: 300, margin: "10px auto 0" }}>🔊 Enable / unmute Aria's voice</button>
            <button onClick={end} className="ghost" style={{ maxWidth: 240, margin: "10px auto 0" }}>End interview & see verdict</button>
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
