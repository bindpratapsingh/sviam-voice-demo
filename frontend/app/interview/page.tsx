"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function InterviewInner() {
  const params = useSearchParams();
  const router = useRouter();
  const room = params.get("room");
  const id = params.get("id");
  const callRef = useRef<any>(null);
  const joinedRef = useRef(false);
  const [status, setStatus] = useState<"mic" | "joining" | "connected" | "error">("mic");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!room || !id) {
      router.push("/");
      return;
    }
    let call: any;
    let cancelled = false;

    (async () => {
      // 1) Force the microphone permission prompt + verify access first.
      try {
        const s = await navigator.mediaDevices.getUserMedia({ audio: true });
        s.getTracks().forEach((t) => t.stop());
      } catch (e: any) {
        console.error("mic error", e);
        setStatus("error");
        setMsg("Microphone is blocked. Click the lock icon in the address bar → Site settings → Microphone → Allow, then reload this page.");
        return;
      }
      if (cancelled) return;

      // 2) Join the Daily room.
      try {
        setStatus("joining");
        const Daily = (await import("@daily-co/daily-js")).default;
        call = Daily.createCallObject();
        callRef.current = call;
        call.on("joined-meeting", () => {
          joinedRef.current = true;
          if (!cancelled) setStatus("connected");
        });
        call.on("error", (e: any) => {
          console.error("daily error", e);
          if (!cancelled) {
            setStatus("error");
            setMsg("Call error: " + (e?.errorMsg || JSON.stringify(e)));
          }
        });
        // Only go to the result page if we ACTUALLY joined and then left.
        call.on("left-meeting", () => {
          if (joinedRef.current) router.push(`/result/${id}`);
        });
        await call.join({ url: room, startVideoOff: true });
        await call.setLocalAudio(true);
      } catch (e: any) {
        console.error("join failed", e);
        if (!cancelled) {
          setStatus("error");
          setMsg("Could not join the interview: " + (e?.errorMsg || e?.message || String(e)));
        }
      }
    })();

    return () => {
      cancelled = true;
      try { call?.destroy(); } catch {}
    };
  }, [room, id, router]);

  function end() {
    if (joinedRef.current && callRef.current) callRef.current.leave();
    else router.push(`/result/${id}`);
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
        {status === "connected" && (
          <button onClick={end} className="ghost" style={{ maxWidth: 240, margin: "24px auto 0" }}>
            End interview & see verdict
          </button>
        )}
        {status === "error" && (
          <button onClick={() => router.push("/")} className="ghost" style={{ maxWidth: 200, margin: "20px auto 0" }}>
            Back
          </button>
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
