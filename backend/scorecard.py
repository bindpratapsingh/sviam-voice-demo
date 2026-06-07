"""Fair interview scorecard + Selected/Rejected verdict.

Scoring judges ONLY demonstrated technical reasoning + communication — never the
interviewer's tone/strictness, asking for clarification, or taking pauses. Best-effort:
never raises (returns a safe dict on any failure)."""
import json
import re

_SYSTEM = (
    "You are an impartial technical-interview evaluator. Read the transcript and produce a "
    "SHORT, fair scorecard as JSON with EXACTLY these keys: "
    'summary (1-2 sentences), strengths (array of <=3 short strings), '
    "areas_to_improve (array of <=3 short strings), communication (1 sentence), "
    "recommendation (one of: strong_yes, yes, lean_yes, lean_no, no). "
    "Judge ONLY demonstrated technical reasoning and communication. Do NOT reward or penalize "
    "the interviewer's tone/strictness, the candidate asking for clarification, or taking pauses. "
    "Keep technical terms in English. Output ONLY the JSON object, no prose, no code fences."
)

# recommendation → human verdict shown to the candidate
_VERDICT = {
    "strong_yes": "Selected",
    "yes": "Selected",
    "lean_yes": "Borderline",
    "lean_no": "Borderline",
    "no": "Rejected",
}


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"error": "scorecard not valid JSON", "raw": text[:300]}


def generate_scorecard(transcript: list[dict], groq_key: str, model: str | None = None) -> dict:
    if not groq_key:
        return {"verdict": "Borderline", "recommendation": "lean_no",
                "summary": "Scorecard skipped (no LLM key configured)."}
    convo = "\n".join(f"{t.get('role')}: {t.get('content')}" for t in transcript if t.get("content"))
    try:
        from groq import Groq

        client = Groq(api_key=groq_key)
        resp = client.chat.completions.create(
            model=model or "llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Transcript:\n{convo}\n\nReturn the JSON scorecard."},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        sc = _parse_json(resp.choices[0].message.content)
    except Exception as e:  # noqa: BLE001
        return {"verdict": "Borderline", "recommendation": "lean_no",
                "summary": f"Scorecard generation failed: {e}"}

    sc["verdict"] = _VERDICT.get(sc.get("recommendation", ""), "Borderline")
    return sc
