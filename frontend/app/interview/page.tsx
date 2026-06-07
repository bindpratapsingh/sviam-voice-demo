"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function InterviewInner() {
  const params = useSearchParams();
  const router = useRouter();
  const room = params.get("room");
  const id = params.get("id");
  const callRef = useRef<any>(null);
  const [status, setStatus] = useState<"connecting" | "connected" | "error">("connecting");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!room || !id) {
      router.push("/");
      return;
    }
    let call: any;
    let cancelled = false;
    (async () => {
      try {
        const Daily = (await import("@daily-co/daily-js")).default;
        call = Daily.createCallObject({ subscribeToTracksAutomatically: true });
        callRef.current = call;
        call.on("joined-meeting", () => !cancelled && setStatus("connected"));
        call.on("left-meeting", () => router.push(`/result/${id}`));
        call.on("error", (e: any) => {
          setStatus("error");
          setMsg(e?.errorMsg || "Connection error");
        });
        await call.join({ url: room, startVideoOff: true, startAudioOff: false });
      } catch (e: any) {
        if (!cancelled) {
          setStatus("error");
          setMsg(e?.message || "Could not join the call. Allow mic access and use Chrome/Edge.");
        }
      }
    })();
    return () => {
      cancelled = true;
      try { call?.destroy(); } catch {}
    };
  }, [room, id, router]);

  function end() {
    if (callRef.current) callRef.current.leave();
    else router.push(`/result/${id}`);
  }

  return (
    <div className="wrap">
      <div className="card" style={{ textAlign: "center" }}>
        <h1>Interview in progress</h1>
        {status === "connecting" && <p className="sub">Connecting… allow microphone access when prompted.</p>}
        {status === "connected" && (
          <div className="live" style={{ justifyContent: "center", margin: "18px 0" }}>
            <span className="dot" /> Connected — Aria is listening. Just talk. Interrupt her any time.
          </div>
        )}
        {status === "error" && <p className="err">{msg}</p>}
        <button onClick={end} className="ghost" style={{ maxWidth: 240, margin: "24px auto 0" }}>
          End interview & see verdict
        </button>
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
