import { useCallback, useEffect, useRef, useState } from "react";

export interface PipelineEvent {
  step: string;
  status: "running" | "ok" | "failed" | "detail";
  message: string;
  detail?: boolean;
  score?: number;
  timestamp?: number;
}

interface WsMessage {
  type: "pipeline.event";
  runId?: string;
  event: PipelineEvent;
}

function wsBase(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  return `${proto}//${host}`;
}

export function usePipelineWebSocket(runId: string | null) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const clear = useCallback(() => setEvents([]), []);

  useEffect(() => {
    if (!runId) return;

    const token = localStorage.getItem("access_token");
    if (!token) return;

    setEvents([]);
    const url = `${wsBase()}/ws/runs/${runId}/?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data as string) as WsMessage;
        if (data.type === "pipeline.event" && data.event) {
          const eventWithTime = {
            ...data.event,
            timestamp: data.event.timestamp || Date.now(),
          };
          setEvents((prev) => [...prev, eventWithTime]);
        }
      } catch {
        /* ignore */
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  return { events, connected, clear };
}
