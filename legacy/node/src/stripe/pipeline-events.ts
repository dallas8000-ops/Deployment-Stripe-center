/** Structured pipeline events — shared by Electron GUI and future Django Channels WS. */

export type PipelineEventStatus = "running" | "ok" | "failed" | "detail";

export interface PipelineEvent {
  step: string;
  status: PipelineEventStatus;
  message: string;
  /** Indent line in terminal UI (sub-step). */
  detail?: boolean;
  score?: number;
}

export type PipelineEventHandler = (event: PipelineEvent) => void;

export function emitEvent(handler: PipelineEventHandler | undefined, event: PipelineEvent): void {
  handler?.(event);
}

/** Channel message shape for Django WebSocket consumers (1:1 port). */
export interface PipelineWsMessage {
  type: "pipeline.event";
  runId?: string;
  event: PipelineEvent;
}

export function toWsMessage(event: PipelineEvent, runId?: string): PipelineWsMessage {
  return { type: "pipeline.event", runId, event };
}
