import { useState } from 'react';
import { downloadPDF } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import type { CVSessionPreview, UIAction } from '../types';

interface CvPreviewSectionProps {
  cvFile: File | null;
  sessionId: string | null;
  currentStepLabel: string | null;
  currentStage: string | null;
  uiAction: UIAction | null;
  lastStage: string | null;
  cvPreview: CVSessionPreview | null;
  cvPreviewError: string | null;
  cvPreviewLoading: boolean;
  actionNotice: string | null;
  latestCvPdfBase64: string | null;
  latestCvPdfFilename: string | null;
  latestCvPdfDownloadName: string | null;
  latestCoverLetterPdfBase64: string | null;
  latestCoverLetterPdfFilename: string | null;
  hasGeneratedPdf: boolean;
  isLoading: boolean;
  formDraft: Record<string, string>;
  onRefresh: () => void;
  onDownloadPdf: () => void;
  onScrollToStagePanel: () => void;
  onFormDraftChange: (key: string, value: string) => void;
  onSendUserAction: (actionId: string, payload?: Record<string, unknown>) => Promise<void>;
  onToggleWorkLock: (roleIndex: number) => void;
  onMoveWorkRoleUp: (roleIndex: number) => void;
  onMoveWorkRoleDown: (roleIndex: number) => void;
  describeMissing: (key: string) => { label: string; hint: string };
  requiredLabel: (key: string) => string;
}

export function CvPreviewSection({
  cvFile,
  sessionId,
  currentStepLabel,
  currentStage,
  uiAction,
  lastStage,
  cvPreview,
  cvPreviewError,
  cvPreviewLoading,
  actionNotice,
  latestCvPdfBase64,
  latestCvPdfFilename,
  latestCvPdfDownloadName,
  latestCoverLetterPdfBase64,
  latestCoverLetterPdfFilename,
  hasGeneratedPdf,
  isLoading,
  formDraft,
  onRefresh,
  onDownloadPdf,
  onScrollToStagePanel,
  onFormDraftChange,
  onSendUserAction,
  onToggleWorkLock,
  onMoveWorkRoleUp,
  onMoveWorkRoleDown,
  describeMissing,
  requiredLabel,
}: CvPreviewSectionProps) {
  const stageLabel = uiAction?.stage || lastStage || '';
  const isJobDataTableStage =
    String(uiAction?.stage || '').toUpperCase() === 'JOB_DATA_TABLE' ||
    String(lastStage || '').toLowerCase() === 'job_data_table';

  const renderActionButtons = () => {
    if (!uiAction?.actions?.length) return null;
    const actions = uiAction.actions || [];
    const fields = Array.isArray(uiAction.fields) ? uiAction.fields : [];
    const hasEditable = uiAction.kind === 'edit_form' || fields.some((f) => !!f?.editable);
    const primaryRaw = actions.filter((a) => !(a.style === 'secondary' || a.style === 'tertiary'));
    const primary = primaryRaw.length > 1 ? primaryRaw.slice(0, 1) : primaryRaw;
    const secondary = actions.filter((a) => a.style === 'secondary' || a.style === 'tertiary');

    const isLanguageSelection = String(uiAction.stage || '').toUpperCase() === 'LANGUAGE_SELECTION';
    const isCoverLetterStage = String(uiAction.stage || '').toUpperCase() === 'COVER_LETTER';
    const enabledLanguageActions = new Set(['LANGUAGE_SELECT_EN', 'LANGUAGE_SELECT_DE']);
    const languageNote = isLanguageSelection ? 'Wybrany język docelowy ustawia wariant template PDF (EN/DE). Dla PL opcja jest jeszcze niedostępna.' : null;
    const hasLocalCvPdf = !!latestCvPdfBase64;
    const hasLocalCoverPdf = !!latestCoverLetterPdfBase64;

    const renderButtons = (items: typeof actions) => (
      <div className="flex flex-wrap gap-2">
        {items.map((a) => {
          if (a.id === 'DOWNLOAD_PDF' && actions.some((x) => x.id === 'REQUEST_GENERATE_PDF')) {
            return null;
          }
          const isSecondary = a.style === 'secondary' || a.style === 'tertiary';
          const isCancel = a.id.endsWith('_CANCEL') || a.id.endsWith('_BACK');
          const payloadBase = hasEditable && !isCancel ? formDraft : undefined;
          const wizardStage = String(lastStage || '').toLowerCase();
          const isExplicitWorkRegenerate = a.id === 'WORK_TAILOR_RUN' && (wizardStage === 'work_tailor_review' || wizardStage === 'work_tailor_feedback');
          const payload = isExplicitWorkRegenerate
            ? { ...(payloadBase || {}), force_regenerate: true }
            : payloadBase;
          if (isLanguageSelection && !enabledLanguageActions.has(a.id)) {
            return null;
          }
          if (String(uiAction.stage || '').toUpperCase() === 'REVIEW_FINAL' && a.id === 'COVER_LETTER_PREVIEW') {
            return null;
          }
          if (isCoverLetterStage && (a.id === 'COVER_LETTER_FEEDBACK_APPLY' || a.id === 'COVER_LETTER_FEEDBACK_EDIT')) {
            return null;
          }
          const wantsCvDownloadViaGenerate = a.id === 'REQUEST_GENERATE_PDF' && (hasLocalCvPdf || hasGeneratedPdf);

          const label = (() => {
            if (a.id === 'REQUEST_GENERATE_PDF') return wantsCvDownloadViaGenerate ? 'Pobierz CV' : 'Generuj PDF';
            if (a.id === 'COVER_LETTER_GENERATE') return hasLocalCoverPdf ? 'Pobierz Cover Letter' : 'Generuj Cover Letter';
            return a.label;
          })();
          return (
            <Button
              key={a.id}
              variant={isSecondary ? 'secondary' : 'primary'}
              onClick={() => {
                if (a.id === 'REQUEST_GENERATE_PDF' && hasLocalCvPdf) {
                  downloadPDF(latestCvPdfBase64!, latestCvPdfDownloadName || latestCvPdfFilename || `CV_${Date.now()}.pdf`);
                  void onSendUserAction(a.id, payload);
                  return;
                }
                // Always call backend for cover-letter generate/download so we don't serve stale local PDF cache.
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
      </div>
    );

    return (
      <div className="space-y-2">
        {languageNote ? <div className="text-xs text-slate-600">{languageNote}</div> : null}
        {primary.length ? renderButtons([...primary, ...secondary]) : renderButtons(actions)}
      </div>
    );
  };

  const renderStagePanel = () => {
    if (!uiAction) return null;
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-3 space-y-3" data-testid="stage-panel" data-stage={stageLabel} data-wizard-stage={lastStage || ''}>
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-sm font-semibold text-slate-900">{uiAction.title || 'Aktualny krok'}</div>
          {uiAction.stage ? <Badge variant="accent">{uiAction.stage}</Badge> : null}
        </div>

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
                  ) : f.type === 'select' ? (
                    <select
                      value={formDraft[f.key] ?? ''}
                      onChange={(e) => onFormDraftChange(f.key, e.target.value)}
                      disabled={isLoading}
                      className="mt-2 w-full rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                    >
                      {(Array.isArray(f.options) ? f.options : []).map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
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
                    if (f.key === 'job_data_table_json') {
                      const formatCvDate = (rawValue: string): string => {
                        const value = String(rawValue || '').trim();
                        if (!value) return '-';
                        const dateTime = value.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})/);
                        if (dateTime) return `${dateTime[1]} ${dateTime[2]}`;
                        const dateOnly = value.match(/^(\d{4}-\d{2}-\d{2})/);
                        if (dateOnly) return dateOnly[1];
                        return value;
                      };

                      let rows: Array<Record<string, string>> = [];
                      try {
                        const parsed = JSON.parse(String(f.value || '[]'));
                        if (Array.isArray(parsed)) {
                          rows = parsed
                            .filter((r) => r && typeof r === 'object')
                            .map((r) => ({
                              position_name: String((r as Record<string, unknown>).position_name || ''),
                              company_name: String((r as Record<string, unknown>).company_name || ''),
                              cv_generated_at: String((r as Record<string, unknown>).cv_generated_at || ''),
                              updated_at: String((r as Record<string, unknown>).updated_at || ''),
                              company_address: String((r as Record<string, unknown>).company_address || ''),
                              company_email: String((r as Record<string, unknown>).company_email || ''),
                              company_phone: String((r as Record<string, unknown>).company_phone || ''),
                            }));
                        }
                      } catch {
                        rows = [];
                      }

                      return (
                        <div className="mt-2 overflow-x-auto">
                          <table className="min-w-full border-collapse text-sm text-slate-900" data-testid="job-data-html-table">
                            <thead>
                              <tr className="bg-slate-50">
                                <th className="border border-slate-200 px-2 py-1 text-left">Data CV</th>
                                <th className="border border-slate-200 px-2 py-1 text-left">Nazwa stanowiska</th>
                                <th className="border border-slate-200 px-2 py-1 text-left">Nazwa firmy</th>
                                <th className="border border-slate-200 px-2 py-1 text-left">Adres firmy</th>
                                <th className="border border-slate-200 px-2 py-1 text-left">Email do firmy</th>
                                <th className="border border-slate-200 px-2 py-1 text-left">Telefon do firmy</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(rows.length ? rows : [{ position_name: '', company_name: '', company_address: '', company_email: '', company_phone: '', cv_generated_at: '', updated_at: '' }]).map((row, idx) => (
                                <tr key={idx}>
                                  <td className="border border-slate-200 px-2 py-1">{formatCvDate(row.cv_generated_at || row.updated_at || '')}</td>
                                  <td className="border border-slate-200 px-2 py-1">{row.position_name}</td>
                                  <td className="border border-slate-200 px-2 py-1">{row.company_name}</td>
                                  <td className="border border-slate-200 px-2 py-1">{row.company_address}</td>
                                  <td className="border border-slate-200 px-2 py-1">{row.company_email}</td>
                                  <td className="border border-slate-200 px-2 py-1">{row.company_phone}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    }

                    const isWorkExperienceStage = String(uiAction.stage || '').toUpperCase() === 'WORK_EXPERIENCE';
                    const isWorkRolesPreview = isWorkExperienceStage && (f.key === 'roles_preview' || f.key === 'proposal_roles_preview');
                    if (!isWorkRolesPreview) {
                      return <div className="mt-1 text-sm text-slate-900 whitespace-pre-wrap break-words">{f.value || ''}</div>;
                    }

                    const upActionId = f.key === 'proposal_roles_preview' ? 'MOVE_WORK_PROPOSAL_UP' : 'MOVE_WORK_EXPERIENCE_UP';
                    const downActionId = f.key === 'proposal_roles_preview' ? 'MOVE_WORK_PROPOSAL_DOWN' : 'MOVE_WORK_EXPERIENCE_DOWN';
                    const testIdPrefix = f.key === 'proposal_roles_preview' ? 'proposal-move' : 'work-move';

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
                                    void onSendUserAction(upActionId, { position_index: roleIdx });
                                  }}
                                  data-testid={`${testIdPrefix}-up-${roleIdx}`}
                                >
                                  ↑
                                </Button>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  disabled={isLoading || roleIdx >= lines.length - 1}
                                  onClick={() => {
                                    void onSendUserAction(downActionId, { position_index: roleIdx });
                                  }}
                                  data-testid={`${testIdPrefix}-down-${roleIdx}`}
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

        {renderActionButtons()}
        {uiAction.disable_free_text ? <div className="text-xs text-slate-600">W tym kroku wiadomości są wyłączone — użyj akcji powyżej.</div> : null}
      </div>
    );
  };

  return (
    <div className={`${!cvFile && !sessionId ? 'hidden' : ''} flex-1 min-w-[520px]`}>
      <Card className="h-full flex flex-col">
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">CV</div>
              <div className="mt-1 text-xs text-slate-600">
                {currentStepLabel ? `Aktualny krok: ${currentStepLabel}` : 'Podgląd danych CV.'}
                {currentStage ? ` (${currentStage})` : ''}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {actionNotice ? <span className="text-xs text-indigo-700">{actionNotice}</span> : null}
              {latestCvPdfBase64 && !(uiAction?.actions || []).some((a) => a.id === 'REQUEST_GENERATE_PDF' || a.id === 'DOWNLOAD_PDF') ? (
                <Button size="sm" variant="secondary" onClick={onDownloadPdf} data-testid="download-pdf">
                  Pobierz PDF
                </Button>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {sessionId && uiAction ? renderStagePanel() : null}
          {isJobDataTableStage ? null : !sessionId ? (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak aktywnej sesji.</div>
          ) : cvPreviewError ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Nie udało się pobrać danych sesji: {cvPreviewError}</div>
          ) : cvPreviewLoading && !cvPreview ? (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Ładowanie…</div>
          ) : cvPreview ? (
              <div className="space-y-3">
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="text-xs font-semibold text-slate-600">Gotowość</div>
                  {(() => {
                    const r = cvPreview.readiness || {};
                    const confirmed = (r.confirmed_flags || {}) as Record<string, boolean>;
                    const canGenerate = !!r.can_generate;
                    return (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {canGenerate ? <Badge variant="success">Gotowe do PDF</Badge> : <Badge variant="warning">Nie gotowe</Badge>}
                        {confirmed?.contact_confirmed ? <Badge variant="success">Kontakt potwierdzony</Badge> : <Badge variant="warning">Kontakt niepotwierdzony</Badge>}
                        {confirmed?.education_confirmed ? <Badge variant="success">Edukacja potwierdzona</Badge> : <Badge variant="warning">Edukacja niepotwierdzona</Badge>}
                      </div>
                    );
                  })()}
                </div>

                <details className="rounded-lg border border-slate-200 bg-white p-3" open>
                  <summary className="cursor-pointer text-sm font-semibold text-slate-900">Kontakt</summary>
                  <div className="mt-2 text-sm text-slate-900 whitespace-pre-wrap break-words">
                    {(() => {
                      const d = cvPreview.cv_data || {};
                      const ci = (d.contact_information || {}) as Record<string, string>;
                      const name = ci.full_name ?? (d.full_name as string) ?? '';
                      const email = ci.email ?? (d.email as string) ?? '';
                      const phone = ci.phone ?? (d.phone as string) ?? '';
                      const addr = Array.isArray(d.address_lines) ? (d.address_lines as string[]).join('\n') : ((d.address as string) ?? '');
                      const parts = [
                        name ? `Imię i nazwisko: ${name}` : null,
                        email ? `Email: ${email}` : null,
                        phone ? `Telefon: ${phone}` : null,
                        addr ? `Adres: ${addr}` : null,
                      ].filter(Boolean);
                      return parts.length ? parts.join('\n') : '(brak)';
                    })()}
                  </div>
                </details>

                <details className="rounded-lg border border-slate-200 bg-white p-3">
                  <summary className="cursor-pointer text-sm font-semibold text-slate-900">Doświadczenie</summary>
                  <div className="mt-2 space-y-2 text-sm text-slate-900">
                    {Array.isArray(cvPreview.cv_data?.work_experience) && cvPreview.cv_data.work_experience.length ? (
                      (cvPreview.cv_data.work_experience as Array<Record<string, unknown>>).slice(0, 12).map((r, i) => (
                        <div key={i} className="rounded-md border border-slate-200 bg-slate-50 p-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="font-semibold">
                              {String(r.title || r.position || '').trim() || '(bez tytułu)'}{' '}
                              {String(r.company || r.employer || '').trim() ? `— ${String(r.company || r.employer)}` : ''}
                              {(() => {
                                const loc = String(r.location || r.city || r.place || '').trim();
                                return loc ? `, ${loc}` : '';
                              })()}
                            </div>
                            {(() => {
                              const locks = (cvPreview?.metadata?.work_role_locks || {}) as Record<string, boolean>;
                              const isLocked = !!locks?.[String(i)];
                              return (
                                <div className="flex items-center gap-1">
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() => onMoveWorkRoleUp(i)}
                                    disabled={isLoading || i === 0}
                                    data-testid={`work-role-up-${i}`}
                                  >
                                    ↑
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    onClick={() => onMoveWorkRoleDown(i)}
                                    disabled={isLoading || i === ((cvPreview.cv_data?.work_experience as Array<unknown> | undefined)?.length || 0) - 1}
                                    data-testid={`work-role-down-${i}`}
                                  >
                                    ↓
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant={isLocked ? 'secondary' : 'primary'}
                                    onClick={() => onToggleWorkLock(i)}
                                    disabled={isLoading}
                                    data-testid={`work-role-lock-${i}`}
                                  >
                                    {isLocked ? 'Unlock' : 'Lock'}
                                  </Button>
                                </div>
                              );
                            })()}
                          </div>
                          <div className="text-xs text-slate-600">{String(r.date_range || '').trim()}</div>
                          {Array.isArray(r.bullets) && r.bullets.length ? (
                            <ul className="mt-2 list-disc space-y-1 pl-5">
                              {(r.bullets as unknown[]).slice(0, 6).map((b, bi) => (
                                <li key={bi}>{String(b)}</li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <div>(brak)</div>
                    )}
                  </div>
                </details>

                <details className="rounded-lg border border-slate-200 bg-white p-3">
                  <summary className="cursor-pointer text-sm font-semibold text-slate-900">Edukacja</summary>
                  <div className="mt-2 space-y-2 text-sm text-slate-900">
                    {Array.isArray(cvPreview.cv_data?.education) && cvPreview.cv_data.education.length ? (
                      (cvPreview.cv_data.education as Array<Record<string, unknown>>).map((e, i) => (
                        <div key={i} className="rounded-md border border-slate-200 bg-slate-50 p-2">
                          <div className="font-semibold">{String(e.title || '').trim() || '(bez tytułu)'}</div>
                          <div className="text-xs text-slate-600">
                            {[e.institution || e.school, e.date_range]
                              .filter(Boolean)
                              .map((x) => String(x))
                              .join(' — ')}
                          </div>
                          {e.details ? <div className="mt-2 whitespace-pre-wrap">{String(e.details)}</div> : null}
                        </div>
                      ))
                    ) : (
                      <div>(brak)</div>
                    )}
                  </div>
                </details>

                <details className="rounded-lg border border-slate-200 bg-white p-3">
                  <summary className="cursor-pointer text-sm font-semibold text-slate-900">Umiejętności</summary>
                  <div className="mt-2 text-sm text-slate-900 whitespace-pre-wrap break-words">
                    {(() => {
                      const d = cvPreview.cv_data || {};
                      const it = Array.isArray(d.it_ai_skills) ? (d.it_ai_skills as string[]) : [];
                      const ops = Array.isArray(d.technical_operational_skills) ? (d.technical_operational_skills as string[]) : [];
                      const parts = [
                        it.length ? `IT & AI: ${it.join(', ')}` : null,
                        ops.length ? `Techniczne & operacyjne: ${ops.join(', ')}` : null,
                      ].filter(Boolean);
                      return parts.length ? parts.join('\n') : '(brak)';
                    })()}
                  </div>
                </details>
              </div>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak danych.</div>
          )}
        </div>
      </Card>
    </div>
  );
}
