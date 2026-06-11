import { useEffect, useRef } from "react";
import type { PipelineEvent } from "../hooks/usePipelineWebSocket";

function icon(status: PipelineEvent["status"]) {
  if (status === "running") return "⏳";
  if (status === "ok") return "✓";
  if (status === "failed") return "✗";
  return "→";
}

function formatTime(timestamp?: number): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
}

interface Props {
  events: PipelineEvent[];
  connected?: boolean;
  running?: boolean;
  emptyMessage?: string;
}

export default function PipelineTerminal({
  events,
  connected,
  running,
  emptyMessage = "Run full setup to stream live progress.",
}: Props) {
  const terminalRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [events]);

  return (
    <div
      ref={terminalRef}
      className={`pipeline-terminal ${running ? "is-running" : ""}`}
      aria-live="polite"
    >
      {events.length === 0 ? (
        <div className="pipeline-line muted">{emptyMessage}</div>
      ) : (
        events.map((ev, i) => (
          <div
            key={`${ev.step}-${i}`}
            className={`pipeline-line ${ev.detail ? "detail" : ev.status}`}
          >
            <span className="pipeline-icon">{icon(ev.status)}</span>
            <span className="pipeline-time">{formatTime(ev.timestamp)}</span>
            <span>{ev.message}</span>
          </div>
        ))
      )}
      {connected && running && events.length > 0 && (
        <div className="pipeline-line muted" style={{ marginTop: 8 }}>
          Live · connected
        </div>
      )}
    </div>
  );
}
