import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getAccessToken } from '../lib/tokenStore';
import type { IncomeStreamResponse, IncomeTransactionItem } from './useBankingIncome';

export interface StreamEvent<T = Record<string, unknown>> {
  id: string;
  event: string;
  data: T;
  created_at?: string;
}

export interface UsePaymentStreamOptions {
  url?: string;
  enabled?: boolean;
  onEvent?: (event: StreamEvent) => void;
  onReconnect?: () => void;
}

export function usePaymentStream({
  url = '/streams/payments',
  enabled = true,
  onEvent,
  onReconnect,
}: UsePaymentStreamOptions = {}) {
  const queryClient = useQueryClient();
  const lastEventIdRef = useRef<string | null>(null);
  const retryAttemptRef = useRef<number>(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const onEventRef = useRef(onEvent);
  const onReconnectRef = useRef(onReconnect);

  onEventRef.current = onEvent;
  onReconnectRef.current = onReconnect;

  useEffect(() => {
    isMountedRef.current = true;
    let abortController: AbortController | null = null;

    if (!enabled) {
      return () => {
        if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
      };
    }

    async function connectStream() {
      if (!isMountedRef.current) return;

      abortController = new AbortController();
      const token = getAccessToken();
      const headers: Record<string, string> = {
        Accept: 'text/event-stream',
        'Cache-Control': 'no-cache',
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      if (lastEventIdRef.current) {
        headers['Last-Event-ID'] = lastEventIdRef.current;
      }

      const apiBase = import.meta.env.VITE_API_URL
        ? String(import.meta.env.VITE_API_URL).replace(/\/$/, '')
        : '';
      const streamEndpoint = url.startsWith('http://') || url.startsWith('https://')
        ? url
        : url.startsWith('/api/v1')
        ? `${apiBase}${url}`
        : `${apiBase}/api/v1${url.startsWith('/') ? url : `/${url}`}`;

      try {
        const response = await fetch(streamEndpoint, {
          headers,
          signal: abortController.signal,
          credentials: 'include',
        });

        if (!response.ok) {
          throw new Error(`SSE stream connection failed with HTTP ${response.status}`);
        }

        if (!response.body) {
          throw new Error('SSE stream response has no readable body');
        }

        // On successful connection/reconnection, reset backoff and invoke fallback refetch
        if (retryAttemptRef.current > 0) {
          if (onReconnectRef.current) {
            onReconnectRef.current();
          } else {
            queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
            queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
          }
        }
        retryAttemptRef.current = 0;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (isMountedRef.current) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split(/\r?\n\r?\n/);
          buffer = parts.pop() || '';

          for (const block of parts) {
            if (!block.trim()) continue;

            const lines = block.split(/\r?\n/);
            let eventType = 'message';
            let eventId: string | null = null;
            const dataLines: string[] = [];

            for (const line of lines) {
              if (line.startsWith(':')) {
                // Heartbeat comment (: heartbeat), connection is alive
                continue;
              }
              if (line.startsWith('id:')) {
                eventId = line.slice(3).trim();
              } else if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();
              } else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5).trim());
              }
            }

            if (eventId) {
              lastEventIdRef.current = eventId;
            }

            if (dataLines.length > 0) {
              const rawData = dataLines.join('\n');
              try {
                const parsedData = JSON.parse(rawData);
                const streamEvt: StreamEvent = {
                  id: eventId || '',
                  event: eventType,
                  data: parsedData,
                };

                // 1. Invoke custom callback if provided
                onEventRef.current?.(streamEvt);

                // 2. Stream-driven cache update for banking income stream
                const amount = Number(parsedData?.amount || 0);
                if (amount > 0 || eventType === 'payment.captured' || eventType === 'order.paid') {
                  queryClient.setQueryData<IncomeStreamResponse>(
                    ['banking_income_stream'],
                    (oldData) => {
                      if (!oldData) return oldData;
                      const newTxn: IncomeTransactionItem = {
                        txn_id: String(parsedData?.payment_id || parsedData?.event_id || `CR_LIVE_${Date.now()}`),
                        timestamp: String(parsedData?.timestamp || new Date().toISOString()),
                        date: String((parsedData?.timestamp || new Date().toISOString()).split('T')[0]),
                        amount,
                        mode: 'UPI',
                        type: 'CREDIT',
                        narration: `Live Real-time Payment Settlement #${String(parsedData?.payment_id || parsedData?.order_id || '').slice(-6)}`,
                        category: 'Business Sales Settlement',
                        payer_identifier: 'Live Gateway Inflow',
                        masked_acc: oldData.active_consent?.masked_acc || 'XXXX-XXXX-4821',
                      };

                      const currentMonth = new Date().toISOString().slice(0, 7);
                      const updatedTrend = [...(oldData.monthly_trend || [])];
                      const monthIdx = updatedTrend.findIndex((m) => m.month === currentMonth);
                      if (monthIdx >= 0) {
                        updatedTrend[monthIdx] = {
                          ...updatedTrend[monthIdx],
                          total_income: Number((updatedTrend[monthIdx].total_income + amount).toFixed(2)),
                          transaction_count: updatedTrend[monthIdx].transaction_count + 1,
                        };
                      } else {
                        updatedTrend.push({
                          month: currentMonth,
                          total_income: amount,
                          transaction_count: 1,
                        });
                      }

                      return {
                        ...oldData,
                        total_inward_income: Number((oldData.total_inward_income + amount).toFixed(2)),
                        total_credits_count: oldData.total_credits_count + 1,
                        recent_inflows: [newTxn, ...(oldData.recent_inflows || []).slice(0, 9)],
                        monthly_trend: updatedTrend,
                      };
                    }
                  );

                  // Also invalidate invoice lists or store dashboards
                  queryClient.invalidateQueries({ queryKey: ['invoices'] });
                  queryClient.invalidateQueries({ queryKey: ['store_dashboard'] });
                  queryClient.invalidateQueries({ queryKey: ['personal_purchases'] });
                }
              } catch (parseErr) {
                console.warn('Failed to parse SSE payload', parseErr);
              }
            }
          }
        }
      } catch (err: unknown) {
        if (!isMountedRef.current || (err instanceof DOMException && err.name === 'AbortError')) {
          return;
        }
        console.warn('SSE stream disconnected, scheduling reconnect...', err);
      }

      // Exponential backoff capped at 30 seconds: 1s, 2s, 4s, 8s, 16s, 30s
      if (isMountedRef.current) {
        const backoffMs = Math.min(30000, 1000 * Math.pow(2, retryAttemptRef.current));
        retryAttemptRef.current += 1;
        retryTimeoutRef.current = setTimeout(connectStream, backoffMs);
      }
    }

    connectStream();

    return () => {
      isMountedRef.current = false;
      if (abortController) {
        abortController.abort();
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, [url, enabled, queryClient]);

  return {
    lastEventId: lastEventIdRef.current,
  };
}

