import { downloadPDF } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import type { Message, StepperItem, UIAction, StageUpdate, WizardStep } from '../types';

interface WizardStageSectionProps {
  sessionId: string | null;
  uiAction: UIAction | null;
  lastStage: string | null;
  lastTraceId: string | null;
  wizardStep: WizardStep;
  stepper: readonly StepperItem[] | null;
  isLoading: boolean;
  latestCvPdfBase64: string | null;
  latestCvPdfFilename: string | null;
  latestCvPdfDownloadName: string | null;
  latestCoverLetterPdfBase64: string | null;
  latestCoverLetterPdfFilename: string | null;
  hasGeneratedPdf: boolean;
  formDraft: Record<string, string>;
  stageUpdates: StageUpdate[];
  messages: Message[];
  onFormDraftChange: (key: string, value: string) => void;
  onSendUserAction: (actionId: string, payload?: Record<string, unknown>) => Promise<void>;
  onStartFresh: () => void;
  onChangeFile: () => void;
  onRefresh?: () => Promise<void>;
  cvPreviewLoading?: boolean;
}

export function WizardStageSection({
  sessionId,
  uiAction,
  lastStage,
  lastTraceId,
  wizardStep,
  stepper,
  isLoading,
  latestCvPdfBase64,
  latestCvPdfFilename,
  latestCvPdfDownloadName,
  latestCoverLetterPdfBase64,
  latestCoverLetterPdfFilename,
  hasGeneratedPdf,
  formDraft,
  stageUpdates,
  messages,
  onFormDraftChange,
  onSendUserAction,
  onStartFresh,
  onChangeFile,
  onRefresh,
  cvPreviewLoading,
}: WizardStageSectionProps) {
  return (
    <div className={`${!sessionId ? 'hidden' : ''} w-[420px] shrink-0`}>
      <Card className="h-full flex flex-col">
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">Krok</div>
              <div className="mt-1 text-xs text-slate-600">Aktualny etap kreatora i akcje.</div>
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
            <div className="space-y-4" data-testid="stage-panel" data-stage={uiAction.stage || ''} data-wizard-stage={lastStage || ''}>
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
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {stepper.map((s) => {
                      const isCurrent = wizardStep?.current === s.n;
                      const isPast = (wizardStep?.current || 0) > s.n;
                      const isFuture = (wizardStep?.current || 0) < s.n;
                      return (
                        <Button
                          key={s.n}
                          size="sm"
                          variant={isCurrent ? 'primary' : 'secondary'}
                          disabled={!isPast}
                          title={isFuture ? 'Dokończ bieżący krok, aby przejść dalej.' : isCurrent ? 'Bieżący krok' : 'Wróć do kroku'}
                          onClick={() => {
                            if (!isPast) return;
                            void onSendUserAction('WIZARD_GOTO_STAGE', { target_stage: s.targetWizardStage });
                          }}
                        >
                          {s.n}. {s.label}
                        </Button>
                      );
                    })}
                  </div>
                  <div className="mt-2 text-[11px] text-slate-600">Możesz wracać do poprzednich kroków. Przyszłe kroki są zablokowane.</div>
                </div>
              ) : null}

              {uiAction.text ? <div className="text-sm text-slate-700 whitespace-pre-wrap">{uiAction.text}</div> : null}

              {Array.isArray(uiAction.fields) && uiAction.fields.length ? (
                <div className="space-y-2">
                  {uiAction.fields.map((f) => (
                    <div key={f.key} className="rounded-lg border border-slate-200 bg-white p-3">
                      <div className="text-xs font-semibold text-slate-600">{f.label}</div>
                      {uiAction.kind === 'edit_form' || f.editable ? (
                        f.type === 'textarea' ? (
                          <textarea
                            value={formDraft[f.key] ?? ''}
                            onChange={(e) => onFormDraftChange(f.key, e.target.value)}
                            disabled={isLoading}
                            className="mt-2 w-full resize-y rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                            rows={8}
                            placeholder={f.placeholder}
                          />
                        ) : (
                          <input
                            value={formDraft[f.key] ?? ''}
                            onChange={(e) => onFormDraftChange(f.key, e.target.value)}
                            disabled={isLoading}
                            className="mt-2 w-full rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                            placeholder={f.placeholder}
                          />
                        )
                      ) : (
                        (() => {
                          const isWorkRolesPreview = String(uiAction.stage || '').toUpperCase() === 'WORK_EXPERIENCE' && f.key === 'roles_preview';
                          if (!isWorkRolesPreview) {
                            return <div className="mt-1 text-sm text-slate-900 whitespace-pre-wrap break-words">{f.value || ''}</div>;
                          }

                          const lines = String(f.value || '')
                            .split('\n')
                            .map((line) => line.trim())
                            .filter(Boolean);

                          if (!lines.length) {
                            return <div className="mt-1 text-sm text-slate-900 whitespace-pre-wrap break-words">(none)</div>;
                          }

                          return (
                            <div className="mt-2 space-y-2">
                              {lines.map((line, idx) => {
                                const m = line.match(/^(\d+)\.\s*(.*)$/);
                                const roleIdx = m ? Math.max(0, Number(m[1]) - 1) : idx;
                                const roleText = m ? m[2] : line;
                                return (
                                  <div key={`${roleIdx}-${roleText}`} className="flex items-start justify-between gap-2 rounded border border-slate-200 bg-slate-50 p-2">
                                    <div className="text-sm text-slate-900 break-words">{`${roleIdx + 1}. ${roleText}`}</div>
                                    <div className="flex shrink-0 items-center gap-1">
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        disabled={isLoading || roleIdx <= 0}
                                        onClick={() => {
                                          void onSendUserAction('MOVE_WORK_EXPERIENCE_UP', { position_index: roleIdx });
                                        }}
                                        data-testid={`work-move-up-${roleIdx}`}
                                      >
                                        ↑
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        disabled={isLoading || roleIdx >= lines.length - 1}
                                        onClick={() => {
                                          void onSendUserAction('MOVE_WORK_EXPERIENCE_DOWN', { position_index: roleIdx });
                                        }}
                                        data-testid={`work-move-down-${roleIdx}`}
                                      >
                                        ↓
                                      </Button>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          );
                        })()
                      )}
                    </div>
                  ))}
                </div>
              ) : null}

              {uiAction.actions?.length ? (
                (() => {
                  const actions = uiAction.actions || [];
                  const fields = Array.isArray(uiAction.fields) ? uiAction.fields : [];
                  const hasEditable = uiAction.kind === 'edit_form' || fields.some((f) => !!f?.editable);
                  const keepInline = new Set(['COVER_LETTER_PREVIEW', 'COVER_LETTER_GENERATE']);
                  const primaryRaw = actions.filter((a) => !(a.style === 'secondary' || a.style === 'tertiary'));
                  const primary = primaryRaw.length > 1 ? primaryRaw.slice(0, 1) : primaryRaw;
                  const inlineSecondary = actions.filter((a) => (a.style === 'secondary' || a.style === 'tertiary') && keepInline.has(a.id));
                  const advanced = actions.filter((a) => (a.style === 'secondary' || a.style === 'tertiary') && !keepInline.has(a.id));
                  const demotedPrimary = primaryRaw.length > 1 ? primaryRaw.slice(1).map((a) => ({ ...a, style: 'secondary' as const })) : [];

                  const isLanguageSelection = String(uiAction.stage || '').toUpperCase() === 'LANGUAGE_SELECTION';
                  const isCoverLetterStage = String(uiAction.stage || '').toUpperCase() === 'COVER_LETTER';
                  const enabledLanguageActions = new Set(['LANGUAGE_SELECT_EN', 'LANGUAGE_SELECT_DE']);
                  const languageNote = isLanguageSelection ? 'Wybrany język docelowy ustawia wariant template PDF (EN/DE). Dla PL opcja jest jeszcze niedostępna.' : null;
                  const hasLocalCvPdf = !!latestCvPdfBase64;
                  const hasLocalCoverPdf = !!latestCoverLetterPdfBase64;

                  const renderButtons = (items: typeof actions, showRefreshBtn: boolean = false) => (
                    <div className="flex flex-wrap gap-2">
                      {showRefreshBtn && onRefresh && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={onRefresh}
                          loading={cvPreviewLoading}
                          disabled={!sessionId}
                          title="Odśwież podgląd CV"
                        >
                          Odśwież
                        </Button>
                      )}
                      {items.map((a) => {
                        const isSecondary = a.style === 'secondary' || a.style === 'tertiary';
                        const isCancel = a.id.endsWith('_CANCEL') || a.id.endsWith('_BACK');
                        const payload = hasEditable && !isCancel ? formDraft : undefined;
                        const isLangDisabled = isLanguageSelection && !enabledLanguageActions.has(a.id);
                        const wantsCvDownloadViaGenerate = a.id === 'REQUEST_GENERATE_PDF' && (hasLocalCvPdf || hasGeneratedPdf);

                        const label = (() => {
                          if (isLangDisabled) return `${a.label} (Coming soon)`;
                          if (a.id === 'REQUEST_GENERATE_PDF') return wantsCvDownloadViaGenerate ? 'Pobierz CV' : 'Generuj PDF';
                          return a.label;
                        })();
                        return (
                          <Button
                            key={a.id}
                            variant={isSecondary ? 'secondary' : 'primary'}
                            disabled={isLangDisabled}
                            title={isLangDisabled ? 'Coming soon — najpierw dopracuj wersję EN.' : undefined}
                            onClick={() => {
                              if (a.id === 'REQUEST_GENERATE_PDF' && hasLocalCvPdf) {
                                downloadPDF(latestCvPdfBase64!, latestCvPdfDownloadName || latestCvPdfFilename || `CV_${Date.now()}.pdf`);
                                return;
                              }
                              if (a.id === 'DOWNLOAD_PDF' && hasLocalCvPdf) {
                                downloadPDF(latestCvPdfBase64!, latestCvPdfDownloadName || latestCvPdfFilename || `CV_${Date.now()}.pdf`);
                                return;
                              }
                              void onSendUserAction(a.id, payload);
                            }}
                            loading={isLoading}
                            data-testid={`action-${a.id}`}
                          >
                            {label}
                          </Button>
                        );
                      })}
                      {showRefreshBtn && isCoverLetterStage && (hasGeneratedPdf || hasLocalCvPdf) ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            if (hasLocalCvPdf) {
                              downloadPDF(latestCvPdfBase64!, latestCvPdfDownloadName || latestCvPdfFilename || `CV_${Date.now()}.pdf`);
                              return;
                            }
                            void onSendUserAction('DOWNLOAD_PDF');
                          }}
                          disabled={isLoading}
                          data-testid="action-inline-download-cv"
                        >
                          Pobierz CV
                        </Button>
                      ) : null}
                      {showRefreshBtn && isCoverLetterStage && hasLocalCoverPdf ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            downloadPDF(latestCoverLetterPdfBase64!, latestCoverLetterPdfFilename || `CoverLetter_${Date.now()}.pdf`);
                          }}
                          disabled={isLoading}
                          data-testid="action-inline-download-cover-letter"
                        >
                          Pobierz Cover Letter
                        </Button>
                      ) : null}
                    </div>
                  );

                  return (
                    <div className="space-y-2">
                      {languageNote ? <div className="text-xs text-slate-600">{languageNote}</div> : null}
                      {primary.length ? renderButtons([...primary, ...inlineSecondary], true) : renderButtons(actions, true)}
                      {advanced.length || demotedPrimary.length ? (
                        <details className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                          <summary className="cursor-pointer text-xs font-semibold text-slate-800">Więcej akcji</summary>
                          <div className="mt-2">{renderButtons([...demotedPrimary, ...advanced])}</div>
                        </details>
                      ) : null}
                    </div>
                  );
                })()
              ) : null}

              {uiAction.disable_free_text ? <div className="text-xs text-slate-600">W tym kroku wiadomości są wyłączone — użyj akcji powyżej.</div> : null}

              <details className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <summary className="cursor-pointer text-sm font-semibold text-slate-800">Debug</summary>
                <div className="mt-2 space-y-1 text-xs text-slate-700">
                  <div>
                    stage: <span className="font-mono">{lastStage || '(brak)'}</span>
                  </div>
                  <div>
                    trace_id: <span className="font-mono">{lastTraceId || '(brak)'}</span>
                  </div>
                </div>
              </details>
            </div>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700" data-testid="stage-panel" data-stage="" data-wizard-stage={lastStage || ''}>
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
