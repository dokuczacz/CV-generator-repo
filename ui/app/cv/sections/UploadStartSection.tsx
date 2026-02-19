import type { HTMLAttributes, InputHTMLAttributes } from 'react';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

interface UploadStartSectionProps {
  resumeFailed: string | null;
  isDragActive: boolean;
  dropzoneRootProps: HTMLAttributes<HTMLDivElement>;
  dropzoneInputProps: InputHTMLAttributes<HTMLInputElement>;
  cvFile: File | null;
  isLoading: boolean;
  fastPathProfile: boolean;
  jobPostingUrl: string | null;
  jobPostingText: string | null;
  onUseLoadedCv: () => void;
  onChangeFile: () => void;
  onFastPathChange: (value: boolean) => void;
  onJobUrlChange: (value: string) => void;
  onJobPostingTextChange: (value: string) => void;
  onNewSession: () => void;
}

export function UploadStartSection({
  resumeFailed,
  isDragActive,
  dropzoneRootProps,
  dropzoneInputProps,
  cvFile,
  isLoading,
  fastPathProfile,
  jobPostingUrl,
  jobPostingText,
  onUseLoadedCv,
  onChangeFile,
  onFastPathChange,
  onJobUrlChange,
  onJobPostingTextChange,
  onNewSession,
}: UploadStartSectionProps) {
  return (
    <Card className="flex-1 flex flex-col overflow-hidden">
      <div className="p-6 border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">CV Generator</div>
            <div className="mt-1 text-xs text-slate-600">Start — wgraj CV (DOCX/PDF). Jeśli masz zapisaną sesję, wznowi się automatycznie.</div>
          </div>
          <Button size="sm" variant="danger" onClick={onNewSession} data-testid="new-session">
            Nowa sesja
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {resumeFailed ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            Nie udało się wznowić poprzedniej sesji: {resumeFailed}
          </div>
        ) : null}
        <div
          {...dropzoneRootProps}
          data-testid="cv-upload-dropzone"
          className={`border border-dashed rounded-xl p-6 text-center cursor-pointer transition flex items-center justify-center ${
            isDragActive ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'
          }`}
        >
          <input {...dropzoneInputProps} />
          <div className="space-y-2">
            <div className="text-sm font-semibold text-slate-900">{isDragActive ? 'Upuść tutaj' : 'Wgraj CV'}</div>
            <div className="text-xs text-slate-600">DOCX lub PDF</div>
          </div>
        </div>

        {cvFile ? (
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="text-xs font-semibold text-slate-700">Załadowane CV</div>
            <div className="mt-1 text-sm text-slate-900 break-words">{cvFile.name}</div>
            <div className="mt-1 text-xs text-slate-600">{(cvFile.size / 1024).toFixed(1)} KB</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={onUseLoadedCv} loading={isLoading} disabled={isLoading} data-testid="use-loaded-cv">
                Użyj tego CV
              </Button>
              <Button size="sm" variant="secondary" onClick={onChangeFile} disabled={isLoading} data-testid="change-cv-file">
                Zmień plik
              </Button>
            </div>
          </div>
        ) : null}

        <div>
          <label className="flex items-center gap-2 text-xs font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={fastPathProfile}
              onChange={(e) => onFastPathChange(!!e.target.checked)}
              disabled={isLoading}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            Fast path: użyj zapisanego profilu (kontakt, edukacja, zainteresowania, język)
          </label>
          <div className="mt-1 text-[11px] text-slate-600">Pozostałe sekcje zawsze są dostosowywane pod konkretną ofertę.</div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Link do oferty (opcjonalnie)</label>
          <input
            value={jobPostingUrl || ''}
            onChange={(e) => onJobUrlChange(e.target.value)}
            placeholder="https://…"
            disabled={isLoading}
            data-testid="job-url-input"
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
          />
          <div className="text-[11px] text-slate-600 mt-1">Jeśli backend nie pobierze treści, poprosi o wklejenie tekstu.</div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Treść / skrót oferty (opcjonalnie)</label>
          <textarea
            value={jobPostingText || ''}
            onChange={(e) => onJobPostingTextChange(e.target.value)}
            placeholder="Wklej opis stanowiska albo krótki skrót wymagań (min. kilka zdań)…"
            disabled={isLoading}
            data-testid="job-text-input"
            className="w-full min-h-[120px] text-sm border border-slate-200 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50 resize-y"
          />
          <div className="text-[11px] text-slate-600 mt-1">To pole przyspiesza analizę (nie musisz czekać na pobranie z URL).</div>
        </div>
      </div>
    </Card>
  );
}
