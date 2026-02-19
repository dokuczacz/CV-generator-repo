import { downloadPDF } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import type { CVSessionPreview } from '../types';

interface CvPreviewSectionProps {
  cvFile: File | null;
  sessionId: string | null;
  cvPreview: CVSessionPreview | null;
  cvPreviewError: string | null;
  cvPreviewLoading: boolean;
  showCvJson: boolean;
  copyNotice: string | null;
  actionNotice: string | null;
  latestPdfBase64: string | null;
  latestPdfFilename: string | null;
  latestPdfDownloadName: string | null;
  isLoading: boolean;
  onToggleShowCvJson: () => void;
  onCopyCvJson: () => void;
  onRefresh: () => void;
  onDownloadPdf: () => void;
  onScrollToStagePanel: () => void;
  onToggleWorkLock: (roleIndex: number) => void;
  describeMissing: (key: string) => { label: string; hint: string };
  requiredLabel: (key: string) => string;
}

export function CvPreviewSection({
  cvFile,
  sessionId,
  cvPreview,
  cvPreviewError,
  cvPreviewLoading,
  showCvJson,
  copyNotice,
  actionNotice,
  latestPdfBase64,
  latestPdfFilename,
  latestPdfDownloadName,
  isLoading,
  onToggleShowCvJson,
  onCopyCvJson,
  onRefresh,
  onDownloadPdf,
  onScrollToStagePanel,
  onToggleWorkLock,
  describeMissing,
  requiredLabel,
}: CvPreviewSectionProps) {
  return (
    <div className={`${!cvFile && !sessionId ? 'hidden' : ''} flex-1 min-w-[520px]`}>
      <Card className="h-full flex flex-col">
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">CV</div>
              <div className="mt-1 text-xs text-slate-600">Podgląd danych CV i gotowość do PDF.</div>
            </div>
            <div className="flex items-center gap-2">
              {copyNotice ? <span className="text-xs text-emerald-700">{copyNotice}</span> : null}
              {actionNotice ? <span className="text-xs text-indigo-700">{actionNotice}</span> : null}
              <Button size="sm" variant="secondary" onClick={onToggleShowCvJson}>
                {showCvJson ? 'Widok' : 'JSON'}
              </Button>
              <Button size="sm" variant="secondary" onClick={onCopyCvJson} disabled={!cvPreview}>
                Kopiuj
              </Button>
              {latestPdfBase64 ? (
                <Button size="sm" variant="secondary" onClick={onDownloadPdf} data-testid="download-pdf">
                  Pobierz PDF
                </Button>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {!sessionId ? (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak aktywnej sesji.</div>
          ) : cvPreviewError ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Nie udało się pobrać danych sesji: {cvPreviewError}</div>
          ) : cvPreviewLoading && !cvPreview ? (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Ładowanie…</div>
          ) : cvPreview ? (
            showCvJson ? (
              <pre className="overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-800">
                {JSON.stringify({ cv_data: cvPreview.cv_data, readiness: cvPreview.readiness, metadata: cvPreview.metadata }, null, 2)}
              </pre>
            ) : (
              <div className="space-y-3">
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="text-xs font-semibold text-slate-600">Gotowość</div>
                  {(() => {
                    const r = cvPreview.readiness || {};
                    const required = (r.required_present || {}) as Record<string, boolean>;
                    const confirmed = (r.confirmed_flags || {}) as Record<string, boolean>;
                    const missing: string[] = Array.isArray(r.missing) ? (r.missing as string[]) : [];
                    const items = Object.entries(required).filter(([, v]) => typeof v === 'boolean') as Array<[string, boolean]>;
                    const canGenerate = !!r.can_generate;
                    const strict = !!r.strict_template;
                    return (
                      <div className="mt-2 space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {canGenerate ? <Badge variant="success">Gotowe do PDF</Badge> : <Badge variant="warning">Nie gotowe</Badge>}
                          {strict ? <Badge>strict_template</Badge> : null}
                          {confirmed?.contact_confirmed ? <Badge variant="success">Kontakt potwierdzony</Badge> : <Badge variant="warning">Kontakt niepotwierdzony</Badge>}
                          {confirmed?.education_confirmed ? <Badge variant="success">Edukacja potwierdzona</Badge> : <Badge variant="warning">Edukacja niepotwierdzona</Badge>}
                        </div>

                        {items.length ? (
                          <div className="space-y-1 text-sm text-slate-900">
                            {items.map(([k, ok]) => (
                              <div key={k} className="flex items-center justify-between gap-3">
                                <span className="text-slate-700">{requiredLabel(k)}</span>
                                <span className={ok ? 'text-emerald-700' : 'text-rose-700'}>{ok ? 'OK' : 'Brak'}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-sm text-slate-700">(brak danych readiness)</div>
                        )}

                        {missing.length ? (
                          <div className="space-y-2">
                            <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                              Braki: {missing.map((m) => describeMissing(m).label).join(', ')}
                            </div>
                            <div className="rounded-md border border-slate-200 bg-white p-2">
                              <div className="text-xs font-semibold text-slate-700">Co zrobić</div>
                              <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-slate-700">
                                {Array.from(new Set(missing)).slice(0, 10).map((m) => {
                                  const d = describeMissing(m);
                                  return (
                                    <li key={m}>
                                      <span className="font-semibold text-slate-900">{d.label}:</span> {d.hint}
                                    </li>
                                  );
                                })}
                              </ul>
                              <div className="mt-2">
                                <Button size="sm" variant="secondary" onClick={onScrollToStagePanel}>
                                  Otwórz krok
                                </Button>
                              </div>
                            </div>
                          </div>
                        ) : null}
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
                                <Button
                                  size="sm"
                                  variant={isLocked ? 'secondary' : 'primary'}
                                  onClick={() => onToggleWorkLock(i)}
                                  disabled={isLoading}
                                  data-testid={`work-role-lock-${i}`}
                                >
                                  {isLocked ? 'Unlock' : 'Lock'}
                                </Button>
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
            )
          ) : (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak danych.</div>
          )}
        </div>
      </Card>
    </div>
  );
}
