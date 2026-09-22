"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { readScan, type Scan } from "@/lib/scanned.ts";

/**
 * Reading printed codes back on the print line.
 *
 * Current labels carry the token where only a reader that exposes the symbol's
 * raw codewords can see it, so they are scanned with the device's camera. A
 * handheld scanner types text, which for these labels is the public URL alone;
 * it still works for labels printed in the original URL format. Either way the
 * scanned value is turned into a token, posted, and dropped. It is never put
 * into state, into a URL, or onto the screen.
 *
 * What a scan records is narrow: this printed symbol decodes, and it decodes to
 * a unit of this batch. QC and the scratch coating remain separate records --
 * the coating goes on after scanning and covers the code, so no scan can ever
 * evidence it.
 */

type ScanOutcome =
  | "RECORDED"
  | "ALREADY_SCANNED"
  | "ALREADY_RECORDED"
  | "NOT_MATCHED"
  | "NOT_APPLICABLE";

type ScanResponse = {
  outcome: ScanOutcome;
  detail?: string;
  external_reference?: string;
  units_scan_verified: number;
  units_ready: number;
  units_total: number;
};

type Entry = { key: number; outcome: ScanOutcome; text: string };

const LOG_LIMIT = 8;

function describe(result: ScanResponse): string {
  switch (result.outcome) {
    case "RECORDED":
      return `${result.external_reference} recorded`;
    case "ALREADY_SCANNED":
      return `${result.external_reference} already scanned`;
    case "ALREADY_RECORDED":
      return `${result.external_reference} was already signed off by hand, not scanned`;
    case "NOT_MATCHED":
      return "Not one of this batch's codes";
    case "NOT_APPLICABLE":
      return result.detail ?? "Cannot be recorded now";
  }
}

function tone(outcome: ScanOutcome): string {
  if (outcome === "RECORDED") return "ok";
  if (outcome === "ALREADY_SCANNED" || outcome === "ALREADY_RECORDED") return "warn";
  return "danger";
}

export function PrintScanner({
  batchId,
  scanned,
  total,
  onProgress,
}: {
  batchId: string;
  scanned: number;
  total: number;
  onProgress: (result: { units_scan_verified: number; units_ready: number }) => void;
}) {
  const [count, setCount] = useState(scanned);
  const [log, setLog] = useState<Entry[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [camera, setCamera] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const nextKey = useRef(0);

  useEffect(() => setCount(scanned), [scanned]);

  const submit = useCallback(
    async (scan: Scan) => {
      const reading = readScan(scan);
      if (reading.kind !== "token") {
        const entry: Entry =
          reading.kind === "public-only"
            ? {
                key: nextKey.current++,
                outcome: "NOT_APPLICABLE",
                text:
                  "This reader sees only the public link on the label. " +
                  "Scan current labels with the camera.",
              }
            : { key: nextKey.current++, outcome: "NOT_MATCHED", text: "Not one of our codes" };
        setLog((entries) => [entry, ...entries].slice(0, LOG_LIMIT));
        return;
      }
      const { token } = reading;

      setBusy(true);
      setError("");
      try {
        const result = await api.post<ScanResponse>("/v1/staff/print-scans", {
          batch: batchId,
          token,
        });
        setCount(result.units_scan_verified);
        onProgress(result);
        setLog((entries) =>
          [
            { key: nextKey.current++, outcome: result.outcome, text: describe(result) },
            ...entries,
          ].slice(0, LOG_LIMIT),
        );
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "The scan could not be recorded.");
      } finally {
        setBusy(false);
      }
    },
    [batchId, onProgress],
  );

  // --- camera ---------------------------------------------------------------
  const videoRef = useRef<HTMLVideoElement>(null);
  const [cameraError, setCameraError] = useState("");

  useEffect(() => {
    if (!camera) return;

    let stream: MediaStream | null = null;
    let timer: number | undefined;
    let stopped = false;
    const canvas = document.createElement("canvas");
    // One label may sit in frame for many ticks. Keyed on the raw codewords:
    // every current label has the same text.
    const seen = new Set<string>();

    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
        });
        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        // Loaded on demand: the decoder is sizeable and most visits to this
        // page never open the camera.
        const { decodeFrame, luminance } = await import("@/lib/readLabel.ts");
        if (stopped) return;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) throw new Error("no canvas");

        timer = window.setInterval(() => {
          const video = videoRef.current;
          if (!video || video.readyState < 2 || !video.videoWidth) return;
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          context.drawImage(video, 0, 0);
          const frame = context.getImageData(0, 0, canvas.width, canvas.height);
          const scan = decodeFrame(luminance(frame.data), frame.width, frame.height);
          if (!scan) return;

          const key = scan.rawBytes
            ? Array.from(scan.rawBytes, (b) => b.toString(16).padStart(2, "0")).join("")
            : scan.text;
          if (seen.has(key)) return;
          seen.add(key);
          void submit(scan);
        }, 400);
      } catch {
        setCameraError("The camera could not be opened.");
        setCamera(false);
      }
    })();

    return () => {
      stopped = true;
      if (timer) window.clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [camera, submit]);

  const remaining = Math.max(total - count, 0);

  return (
    <div className="card">
      <div className="alert info" style={{ marginTop: 0 }}>
        A scan records that the printed code reads back correctly. QC and the
        scratch coating are recorded separately below: the coating is applied
        after scanning and covers the code, so no scan can evidence it.
      </div>

      <div className="grid" style={{ marginBottom: "1rem" }}>
        <div className="stat">
          <div className="value">
            {count}
            <span className="muted" style={{ fontSize: "0.95rem" }}> / {total}</span>
          </div>
          <div className="label">scanned on the line</div>
        </div>
        <div className="stat">
          <div className="value">{remaining}</div>
          <div className="label">not yet scanned</div>
        </div>
      </div>

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          const field = inputRef.current;
          if (!field) return;
          const value = field.value;
          // Cleared before the request, so the credential is not left sitting
          // in a field on a shared factory terminal.
          field.value = "";
          void submit({ text: value });
        }}
      >
        <label>
          <span>Scan or type a code</span>
          <input
            ref={inputRef}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            placeholder="Point the handheld scanner here"
          />
        </label>
        <div className="shrink">
          <button type="submit" disabled={busy}>Record</button>
        </div>
        <div className="shrink">
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setCameraError("");
              setCamera((on) => !on);
            }}
          >
            {camera ? "Stop camera" : "Use camera"}
          </button>
        </div>
      </form>

      {cameraError && <p className="muted">{cameraError}</p>}
      {camera && (
        <video
          ref={videoRef}
          muted
          playsInline
          style={{
            width: "100%",
            maxWidth: 360,
            borderRadius: 8,
            marginTop: "0.75rem",
            background: "#000",
          }}
        />
      )}

      {error && <div className="alert error" style={{ marginTop: "1rem" }}>{error}</div>}

      {log.length > 0 && (
        <ul style={{ margin: "1rem 0 0", paddingLeft: "1.1rem" }}>
          {log.map((entry) => (
            <li key={entry.key}>
              <span className={`badge ${tone(entry.outcome)}`}>
                {entry.outcome.replace(/_/g, " ").toLowerCase()}
              </span>{" "}
              {entry.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
