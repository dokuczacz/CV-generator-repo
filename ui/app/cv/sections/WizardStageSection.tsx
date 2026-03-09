import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import type { ExecutionStrategy, Message, StepperItem, UIAction, StageUpdate, WizardStep } from '../types';

interface WizardStageSectionProps {
  sessionId: string | null;
  uiAction: UIAction | null;
  lastStage: string | null;
  lastTraceId: string | null;
  wizardStep: WizardStep;
  maxUnlockedStep: number;
  stepper: readonly StepperItem[] | null;
  isLoading: boolean;
  executionStrategy: ExecutionStrategy;
  stageUpdates: StageUpdate[];
  messages: Message[];
  onSendUserAction: (actionId: string, payload?: Record<string, unknown>) => Promise<void>;
  onExecutionStrategyChange: (value: ExecutionStrategy) => void;
  onStartFresh: () => void;
  onChangeFile: () => void;
}

export function WizardStageSection({
  sessionId,
  uiAction,
  lastStage,
  lastTraceId,
  wizardStep,
  maxUnlockedStep,
  stepper,
  isLoading,
  executionStrategy,
  stageUpdates,
  messages,
  onSendUserAction,
  onExecutionStrategyChange,
  onStartFresh,
  onChangeFile,
}: WizardStageSectionProps) {
  const stageLabel = uiAction?.stage || lastStage || '';
  return (
    <div className={`${!sessionId ? 'hidden' : ''} w-[420px] shrink-0`}>
      <Card className="h-full flex flex-col">
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">Krok</div>
              <div className="mt-1 text-xs text-slate-600">Aktualny etap kreatora i akcje.</div>
              <div className="mt-2">
                <label className="block text-[11px] font-semibold text-slate-700 mb-1">Tryb wykonania</label>
                <select
                  value={executionStrategy}
                  onChange={(e) => onExecutionStrategyChange(e.target.value as ExecutionStrategy)}
                  disabled={isLoading}
                  data-testid="execution-strategy-select-session"
                  className="w-full max-w-[240px] text-xs border border-slate-200 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                >
                  <option value="auto">Auto</option>
                  <option value="separate">Separate</option>
                  <option value="unified">Unified (1 prompt)</option>
                </select>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" onClick={onStartFresh} title="Zaczyna nową sesję dla tego samego CV">
                Nowa wersja
              </Button>
              <Button size="sm" variant="secondary" onClick={onChangeFile}>
                Zmień plik
              </Button>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {uiAction ? (
            <div className="space-y-4" data-testid="stage-nav-panel" data-stage={stageLabel} data-wizard-stage={lastStage || ''}>
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-sm font-semibold text-slate-900">{uiAction.title || 'Aktualny krok'}</div>
                {uiAction.stage ? <Badge variant="accent">{uiAction.stage}</Badge> : null}
              </div>
              {wizardStep ? (
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1">
                    {Array.from({ length: wizardStep.total }).map((_, i) => {
                      const active = i < wizardStep.current;
                      return <span key={i} className={`h-2 w-2 rounded-full ${active ? 'bg-indigo-600' : 'bg-slate-200'}`} aria-hidden="true" />;
                    })}
                  </div>
                  <div className="text-xs text-slate-600">Krok {wizardStep.current}/{wizardStep.total}</div>
                </div>
              ) : null}

              {stepper ? (
                <div className="rounded-lg border border-slate-200 bg-white p-2">
                  <div className="text-[11px] font-semibold text-slate-700">Nawigacja</div>
                  <div className="mt-2 space-y-2">
                    {stepper.map((s) => {
                      const isCurrent = wizardStep?.current === s.n;
                      const isUnlocked = s.targetWizardStage === 'job_data_table' || s.n <= (maxUnlockedStep || 0);
                      const isFutureLocked = !isUnlocked;
                      return (
                        <Button
                          key={s.n}
                          size="sm"
                          variant={isCurrent ? 'primary' : 'secondary'}
                          disabled={!isUnlocked}
                          title={isFutureLocked ? 'Krok nie jest jeszcze odblokowany.' : isCurrent ? 'Bieżący krok' : 'Przejdź do kroku'}
                          onClick={() => {
                            if (!isUnlocked) return;
                            if (s.targetWizardStage === 'job_data_table') {
                              void onSendUserAction('JOB_DATA_TABLE_OPEN');
                              return;
                            }
                            void onSendUserAction('WIZARD_GOTO_STAGE', { target_stage: s.targetWizardStage });
                          }}
                          className="w-full justify-start"
                        >
                          {s.n}. {s.label}
                        </Button>
                      );
                    })}
                  </div>
                  <div className="mt-2 text-[11px] text-slate-600">Możesz wracać do odblokowanych kroków. „Dane oferty” jest dostępne niezależnie.</div>
                </div>
              ) : null}

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                Szczegóły aktywnego kroku i akcje są wyświetlane w panelu środkowym (podgląd CV).
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700" data-testid="stage-nav-panel" data-stage="" data-wizard-stage={lastStage || ''}>
              Brak aktywnego kroku. Wgraj CV lub wyślij wiadomość.
            </div>
          )}

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
            <div className="mt-2 text-xs text-slate-600">session_id: <span className="font-mono">{sessionId || '(brak)'}</span></div>
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
