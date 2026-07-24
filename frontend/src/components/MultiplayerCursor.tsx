import React, { useEffect, useState, useRef, useCallback } from 'react';

interface MultiplayerCursorProps {
  incidentId: string;
}

const HEARTBEAT_INTERVAL_MS = 30_000; // ping every 30 s
const MAX_RECONNECT_DELAY_MS = 30_000; // cap back-off at 30 s
const BASE_RECONNECT_DELAY_MS = 1_000; // start at 1 s

export default function MultiplayerCursor({ incidentId }: MultiplayerCursorProps) {
  const [peers, setPeers] = useState<Record<string, { x: number; y: number }>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const myId = useRef<string>('');
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttemptRef = useRef<number>(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef<boolean>(false);

  const clearHeartbeat = () => {
    if (heartbeatRef.current !== null) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  };

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  useEffect(() => {
    unmountedRef.current = false;
    myId.current = `analyst_${Math.random().toString(36).substring(2, 7)}`;

    function connect() {
      if (unmountedRef.current) return;

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/incident/${incidentId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        clearHeartbeat();
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping', userId: myId.current }));
          }
        }, HEARTBEAT_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          if (data.type === 'CURSOR_MOVE') {
            setPeers(prev => ({
              ...prev,
              [data.userId]: { x: data.x, y: data.y }
            }));
          } else if (data.type === 'USER_LEFT') {
            setPeers(prev => {
              const next = { ...prev };
              delete next[data.userId];
              return next;
            });
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onerror = () => {};

      ws.onclose = () => {
        clearHeartbeat();
        if (unmountedRef.current) return;

        const attempt = reconnectAttemptRef.current;
        const delay = Math.min(
          BASE_RECONNECT_DELAY_MS * 2 ** attempt + Math.random() * 500,
          MAX_RECONNECT_DELAY_MS
        );
        reconnectAttemptRef.current = attempt + 1;

        clearReconnectTimer();
        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, delay);
      };
    }

    connect();

    const handleMouseMove = (e: MouseEvent) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'CURSOR_MOVE',
          userId: myId.current,
          x: e.clientX,
          y: e.clientY
        }));
      }
    };

    window.addEventListener('mousemove', handleMouseMove);

    return () => {
      unmountedRef.current = true;
      window.removeEventListener('mousemove', handleMouseMove);
      clearHeartbeat();
      clearReconnectTimer();
      wsRef.current?.close();
    };
  }, [incidentId]);

  return (
    <>
      {Object.entries(peers).map(([id, pos]) => (
        <div
          key={id}
          className="pointer-events-none fixed z-50 flex items-center gap-2 transition-transform duration-75"
          style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
        >
          {/* Custom SVG Cursor */}
          <svg width="18" height="24" viewBox="0 0 18 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M2 2L15.6364 10.9545L9.5 12.5L12 18.5L9.5 19.5L6.5 13.5L2 17.5V2Z" fill="#a855f7" stroke="white" strokeWidth="1.5"/>
          </svg>
          <span className="bg-purple-500 text-white text-[10px] font-bold px-2 py-0.5 rounded shadow-lg">
            {id}
          </span>
        </div>
      ))}
    </>
  );
}
