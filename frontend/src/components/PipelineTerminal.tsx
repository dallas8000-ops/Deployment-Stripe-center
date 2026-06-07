import type { PipelineEvent } from "../hooks/usePipelineWebSocket";

function icon(status: PipelineEvent["status"]) {
  if (status === "running") return "⏳";
  if (status === "ok") return "✓";
  if (status === "failed") return "✗";
  return "→";
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
  return (
    <div className={`pipeline-terminal ${running ? "is-running" : ""}`} aria-live="polite">
      {events.length === 0 ? (
        <div className="pipeline-line muted">{emptyMessage}</div>
      ) : (
        events.map((ev, i) => (
          <div
            key={`${ev.step}-${i}`}
            className={`pipeline-line ${ev.detail ? "detail" : ev.status}`}
          >
            <span className="pipeline-icon">{icon(ev.status)}</span>
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
