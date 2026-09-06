// REST API client and WebSocket connection hook.

import { useState, useEffect, useCallback, useRef } from 'react';
import type { WsMessage } from './types';

const API_BASE = 'http://localhost:8000/api';
const WS_URL = 'ws://localhost:8000/api/ws';

export async function startScrape(maxProducts: number, urls: string[]) {
  const res = await fetch(`${API_BASE}/scrape/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max_products: maxProducts, urls }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start scrape' }));
    throw new Error(err.detail || 'Failed to start scrape');
  }
  return res.json();
}

export async function stopScrape() {
  const res = await fetch(`${API_BASE}/scrape/stop`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to stop scrape');
  return res.json();
}

export async function getStatus() {
  const res = await fetch(`${API_BASE}/scrape/status`);
  if (!res.ok) throw new Error('Failed to get status');
  return res.json();
}

export async function getProducts(page = 1, perPage = 50, search = '', sortBy = 'scraped_at', sortDir = 'desc', runId?: string) {
  const params = new URLSearchParams({
    page: page.toString(),
    per_page: perPage.toString(),
    search,
    sort_by: sortBy,
    sort_dir: sortDir,
  });
  if (runId && runId !== 'all') {
    params.append('run_id', runId);
  }
  const res = await fetch(`${API_BASE}/products?${params}`);
  if (!res.ok) throw new Error('Failed to get products');
  return res.json();
}

export function downloadCsv(runId?: string) {
  const url = `${API_BASE}/export/csv${runId && runId !== 'all' ? `?run_id=${encodeURIComponent(runId)}` : ''}`;
  window.open(url, '_blank');
}

export function downloadAiCsv(runId?: string) {
  const url = `${API_BASE}/export/ai-csv${runId && runId !== 'all' ? `?run_id=${encodeURIComponent(runId)}` : ''}`;
  window.open(url, '_blank');
}

export async function clearDatabase() {
  const res = await fetch(`${API_BASE}/products/clear`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to clear database' }));
    throw new Error(err.detail || 'Failed to clear database');
  }
  return res.json();
}

export async function getProductCount() {
  const res = await fetch(`${API_BASE}/products/count`);
  if (!res.ok) throw new Error('Failed to get product count');
  return res.json();
}

export async function getMetrics() {
  const res = await fetch(`${API_BASE}/metrics`);
  if (!res.ok) throw new Error('Failed to get metrics');
  return res.json();
}

export async function getRuns() {
  const res = await fetch(`${API_BASE}/runs`);
  if (!res.ok) throw new Error('Failed to get runs');
  return res.json();
}

export async function startAiExtraction(runId?: string) {
  const url = `${API_BASE}/ai/extract${runId && runId !== 'all' ? `?run_id=${encodeURIComponent(runId)}` : ''}`;
  const res = await fetch(url, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to start AI extraction');
  return res.json();
}

export async function getAiStatus() {
  const res = await fetch(`${API_BASE}/ai/status`);
  if (!res.ok) throw new Error('Failed to get AI status');
  return res.json();
}

export function useWebSocket() {
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('Disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    setConnectionStatus('Connecting...');
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setIsConnected(true);
      setConnectionStatus('Connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLastMessage(data);
      } catch (err) {
        console.error('Failed to parse WS message', err);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      setConnectionStatus('Disconnected');
      wsRef.current = null;
      reconnectTimeoutRef.current = window.setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { lastMessage, isConnected, connectionStatus };
}
