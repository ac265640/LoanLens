import { useRef, useState } from "react";
import { uploadTape, getRun } from "../api";

type Phase = "idle" | "uploading" | "processing" | "done" | "error";

export default function UploadDropzone({ onComplete }: { onComplete: () => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [message, setMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    if (!file.name.endsWith(".csv")) {
      setPhase("error");
      setMessage("Please drop a .csv loan tape.");
      return;
    }
    try {
      setPhase("uploading");
      setProgress(0);
      const key = await uploadTape(file, setProgress);
      setPhase("processing");
      setMessage("S3 → EventBridge → Step Functions is scoring 100% of the portfolio…");

      // Must match the ingest Lambda's default run_id derivation exactly:
      // key.replace("/", "_") with a trailing ".csv" stripped.
      const runId = key.replace(/\//g, "_").replace(/\.csv$/, "");
      let attempts = 0;
      const poll = async () => {
        attempts += 1;
        try {
          const run = await getRun(runId);
          if (run.status === "COMPLETE") {
            setPhase("done");
            setMessage(
              `Scored ${run.loans_scored} loans — ${run.high_risk_count} high-risk, ${run.exception_count} exceptions flagged.`
            );
            onComplete();
            return;
          }
        } catch {
          // run not found yet — keep polling
        }
        if (attempts < 40) setTimeout(poll, 3000);
        else {
          setPhase("error");
          setMessage("Still processing in the background — check the portfolio table shortly.");
        }
      };
      setTimeout(poll, 3000);
    } catch (e) {
      setPhase("error");
      setMessage(e instanceof Error ? e.message : "Upload failed");
    }
  }

  return (
    <div
      className={`glass rounded-2xl p-6 text-center transition-all ${
        dragOver ? "glow-border" : ""
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
      />

      {phase === "idle" && (
        <button onClick={() => inputRef.current?.click()} className="w-full">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl" style={{ background: "var(--accent-glow)" }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
              <path d="M12 3v12m0-12 4 4m-4-4-4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
            Drop a new loan tape, or click to browse
          </p>
          <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
            S3 → EventBridge → Step Functions → 100% of the portfolio scored, live
          </p>
        </button>
      )}

      {(phase === "uploading" || phase === "processing") && (
        <div>
          <div className="mx-auto mb-3 h-2 w-full max-w-xs overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
            <div
              className="h-full rounded-full transition-all animate-pulse-soft"
              style={{ width: `${phase === "uploading" ? progress : 100}%`, background: "var(--accent)" }}
            />
          </div>
          <p className="text-sm" style={{ color: "var(--text)" }}>
            {phase === "uploading" ? `Uploading… ${progress}%` : message}
          </p>
        </div>
      )}

      {phase === "done" && (
        <div>
          <p className="text-sm font-medium" style={{ color: "var(--emerald)" }}>
            ✓ Pipeline complete
          </p>
          <p className="mt-1 text-xs" style={{ color: "var(--text-dim)" }}>
            {message}
          </p>
          <button
            onClick={() => setPhase("idle")}
            className="mt-3 rounded-lg px-3 py-1.5 text-xs"
            style={{ border: "1px solid var(--border)", color: "var(--text-dim)" }}
          >
            Upload another tape
          </button>
        </div>
      )}

      {phase === "error" && (
        <div>
          <p className="text-sm" style={{ color: "var(--crimson)" }}>
            {message}
          </p>
          <button
            onClick={() => setPhase("idle")}
            className="mt-3 rounded-lg px-3 py-1.5 text-xs"
            style={{ border: "1px solid var(--border)", color: "var(--text-dim)" }}
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
