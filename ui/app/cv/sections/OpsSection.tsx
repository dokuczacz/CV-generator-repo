import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import type { Message, StageUpdate } from '../types';

interface OpsSectionProps {
  visible: boolean;
  lastStage: string | null;
  lastTraceId: string | null;
  stageUpdates: StageUpdate[];
  messages: Message[];
  onCopyTraceId: () => void;
}

export function OpsSection({ visible, lastStage, lastTraceId, stageUpdates, messages, onCopyTraceId }: OpsSectionProps) {
  if (!visible) return null;

  return (
    <div className="hidden xl:block w-[420px] shrink-0">
      <Card className="h-full flex flex-col overflow-hidden">
        <div className="border-b border-slate-200 p-4">
          <div className="text-sm font-semibold text-slate-900">Panel</div>
          <div className="mt-1 text-xs text-slate-600">Status, logi, historia i ustawienia.</div>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {lastStage ? (
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
              stage: <span className="font-mono">{lastStage}</span>
            </div>
          ) : null}
          {lastTraceId ? (
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700 flex items-center justify-between gap-2">
              <span>
                trace_id: <span className="font-mono">{lastTraceId}</span>
              </span>
              <Button size="sm" variant="secondary" onClick={onCopyTraceId}>
                Kopiuj
              </Button>
            </div>
          ) : null}

          {stageUpdates.length ? (
            <details className="rounded-lg border border-slate-200 bg-white p-3" open>
              <summary className="cursor-pointer text-sm font-semibold text-slate-900">Ostatnie kroki</summary>
              <div className="mt-2 space-y-1 text-xs text-slate-700">
                {stageUpdates.slice(0, 32).map((s, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <span className={`mt-0.5 inline-block h-2 w-2 rounded-full ${s.ok === false ? 'bg-rose-500' : 'bg-emerald-500'}`} />
                    <div className="flex-1">
                      <div className="font-mono">{String(s.step || '').slice(0, 60)}</div>
                      {s.mode ? <div className="text-slate-600">mode: {String(s.mode).slice(0, 24)}</div> : null}
                      {s.error ? <div className="text-rose-700">error: {String(s.error).slice(0, 140)}</div> : null}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}

          <details className="rounded-lg border border-slate-200 bg-white p-3">
            <summary className="cursor-pointer text-sm font-semibold text-slate-900">Historia</summary>
            <div className="mt-3 space-y-2">
              {messages.slice(-20).map((msg, idx) => (
                <div
                  key={idx}
                  className={`rounded-lg border p-2 text-xs ${
                    msg.role === 'user' ? 'border-indigo-200 bg-indigo-50 text-indigo-900' : 'border-slate-200 bg-slate-50 text-slate-900'
                  }`}
                >
                  <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                </div>
              ))}
            </div>
          </details>
        </div>
      </Card>
    </div>
  );
}
