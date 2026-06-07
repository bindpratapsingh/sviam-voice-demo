"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function InterviewInner() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const roomRef = useRef<any>(null);
  const joinedRef = useRef(false);
  const [status, setStatus] = useState<"mic" | "joining" | "connected" | "error">("mic");
  const [msg, setMsg] = useState("");
  const [needAudio, setNeedAudio] = useState(false);

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
    const { url, token } = JSON.parse(raw);
    let room: any;
    let cancelled = false;

    (async () => {
      // 1) Mic permission prompt + verify.
      try {
        const s = await navigator.mediaDevices.getUserMedia({ audio: true });
        s.getTracks().forEach((t) => t.stop());
      } catch (e) {
        console.error("mic error", e);
        setStatus("error");
        setMsg("Microphone is blocked. Click the lock icon in the address bar → Site settings → Microphone → Allow, then reload.");
        return;
      }
      if (cancelled) return;

      // 2) Join the LiveKit room.
      try {
        setStatus("joining");
        const { Room, RoomEvent } = await import("livekit-client");
        room = new Room();
        roomRef.current = room;

        room.on(RoomEvent.TrackSubscribed, (track: any) => {
          if (track.kind === "audio") {
            const el = track.attach();
            el.autoplay = true;
            (el as HTMLMediaElement).play?.().catch(() => {});
            document.body.appendChild(el);
          }
        });
        room.on(RoomEvent.Disconnected, () => {
          if (joinedRef.current) router.push(`/result/${id}`);
        });
        room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
          if (!room.canPlaybackAudio) setNeedAudio(true);
        });

        await room.connect(url, token);
        joinedRef.current = true;
        await room.localParticipant.setMicrophoneEnabled(true);
        try { await room.startAudio(); } catch { setNeedAudio(true); }
        setStatus("connected");
      } catch (e: any) {
        console.error("join failed", e);
        if (!cancelled) {
          setStatus("error");
          setMsg("Could not join the interview: " + (e?.message || String(e)));
        }
      }
    })();

    return () => {
      cancelled = true;
      try { room?.disconnect(); } catch {}
    };
  }, [id, router]);

  function end() {
    if (joinedRef.current && roomRef.current) roomRef.current.disconnect();
    else router.push(`/result/${id}`);
  }

  async function enableSound() {
    try { await roomRef.current?.startAudio(); setNeedAudio(false); } catch {}
  }

  return (
    <div className="wrap">
      <div className="card" style={{ textAlign: "center" }}>
        <h1>Interview</h1>
        {status === "mic" && <p className="sub">Requesting microphone… please click “Allow”.</p>}
        {status === "joining" && <p className="sub">Connecting to Aria…</p>}
        {status === "connected" && (
          <div className="live" style={{ justifyContent: "center", margin: "18px 0" }}>
            <span className="dot" /> Connected — Aria is listening. Just talk; interrupt her any time.
          </div>
        )}
        {status === "error" && <p className="err">{msg}</p>}

        {needAudio && status === "connected" && (
          <button onClick={enableSound} style={{ maxWidth: 240, margin: "0 auto 12px" }}>🔊 Enable Aria's voice</button>
        )}
        {status === "connected" && (
          <button onClick={end} className="ghost" style={{ maxWidth: 240, margin: "12px auto 0" }}>
            End interview & see verdict
          </button>
        )}
        {status === "error" && (
          <button onClick={() => router.push("/")} className="ghost" style={{ maxWidth: 200, margin: "20px auto 0" }}>Back</button>
        )}
        <p className="pill" style={{ marginTop: 16 }}>Use headphones so Aria's voice doesn't echo into your mic.</p>
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
