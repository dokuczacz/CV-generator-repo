'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { downloadPDF } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  pdfBase64?: string;
}

interface UIActionButton {
  id: string;
  label: string;
  style?: 'primary' | 'secondary' | 'tertiary';
}

interface UIActionField {
  key: string;
  label: string;
  value: string;
  type?: 'text' | 'textarea';
  editable?: boolean;
  placeholder?: string;
}

interface UIAction {
  kind: string;
  stage?: string;
  title?: string;
  text?: string;
  actions?: UIActionButton[];
  fields?: UIActionField[];
  disable_free_text?: boolean;
}

type StageUpdate = {
  step: string;
  ok?: boolean;
  mode?: string;
  error?: string;
  [key: string]: any;
};

type CVSessionPreview = {
  cv_data: any;
  metadata: any;
  readiness: any;
};

const SESSION_ID_KEY = 'cvgen:session_id';
const JOB_URL_KEY = 'cvgen:job_posting_url';
const JOB_TEXT_KEY = 'cvgen:job_posting_text';
const FAST_PROFILE_KEY = 'cvgen:fast_path_profile';
const SESSION_TIMESTAMP_KEY = 'cvgen:session_timestamp';
const DEBUG_STAGE = process.env.NEXT_PUBLIC_CV_DEBUG_STAGE === '1';

const INITIAL_ASSISTANT_MESSAGE: Message = {
  role: 'assistant',
  content: 'Cześć! Wgraj swoje CV (DOCX lub PDF) albo opisz informacje o sobie. Pomogę Ci wygenerować profesjonalne CV w PDF.',
};

export default function CVGenerator() {
  const [messages, setMessages] = useState<Message[]>([INITIAL_ASSISTANT_MESSAGE]);
  const [expandedMessages, setExpandedMessages] = useState<Record<number, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [jobPostingUrl, setJobPostingUrl] = useState<string | null>(null);
  const [jobPostingText, setJobPostingText] = useState<string | null>(null);
  const [fastPathProfile, setFastPathProfile] = useState(true);
  const [uiAction, setUiAction] = useState<UIAction | null>(null);
  const [showSessionDialog, setShowSessionDialog] = useState(false);
  const [pendingSession, setPendingSession] = useState<{ id: string; timestamp: string } | null>(null);
  const [latestPdfBase64, setLatestPdfBase64] = useState<string | null>(null);
  const [lastTraceId, setLastTraceId] = useState<string | null>(null);
  const [lastStage, setLastStage] = useState<string | null>(null);
  const [stageUpdates, setStageUpdates] = useState<StageUpdate[]>([]);
  const [cvPreview, setCvPreview] = useState<CVSessionPreview | null>(null);
  const [cvPreviewError, setCvPreviewError] = useState<string | null>(null);
  const [cvPreviewLoading, setCvPreviewLoading] = useState(false);
  const [showCvJson, setShowCvJson] = useState(false);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const clearLocalSession = () => {
    setSessionId(null);
    setJobPostingUrl(null);
    setJobPostingText(null);
    setUiAction(null);
    setLatestPdfBase64(null);
    setLastTraceId(null);
    setLastStage(null);
    setStageUpdates([]);
    setCvPreview(null);
    setCvPreviewError(null);
    try {
      window.localStorage.removeItem(SESSION_ID_KEY);
      window.localStorage.removeItem(JOB_URL_KEY);
      window.localStorage.removeItem(JOB_TEXT_KEY);
      window.localStorage.removeItem(SESSION_TIMESTAMP_KEY);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    try {
      const storedSessionId = window.localStorage.getItem(SESSION_ID_KEY);
      const storedTimestamp = window.localStorage.getItem(SESSION_TIMESTAMP_KEY);
      const storedFastProfile = window.localStorage.getItem(FAST_PROFILE_KEY);

      if (storedSessionId) {
        // Found a previous session - ask user if they want to continue or start fresh
        setPendingSession({
          id: storedSessionId,
          timestamp: storedTimestamp || 'unknown',
        });
        setShowSessionDialog(true);
      }
      if (storedFastProfile === '0' || storedFastProfile === '1') {
        setFastPathProfile(storedFastProfile === '1');
      }
      // Job URL/text are only loaded if user chooses to continue session
    } catch {
      // ignore
    }
  }, []);

  const loadCvPreview = useCallback(async () => {
    if (!sessionId) return;
    setCvPreviewLoading(true);
    setCvPreviewError(null);
    try {
      const res = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || !json?.success) {
        throw new Error(String(json?.error || `HTTP ${res.status}`));
      }
      setCvPreview({ cv_data: json.cv_data, metadata: json.metadata, readiness: json.readiness });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setCvPreviewError(msg);
      setCvPreview(null);
    } finally {
      setCvPreviewLoading(false);
    }
  }, [sessionId]);

  const copyText = useCallback(async (text: string, label: string) => {
    const value = String(text || '');
    if (!value.trim()) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopyNotice(`${label} skopiowane`);
    } catch {
      try {
        const el = document.createElement('textarea');
        el.value = value;
        el.style.position = 'fixed';
        el.style.left = '-9999px';
        el.style.top = '0';
        document.body.appendChild(el);
        el.focus();
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
        setCopyNotice(`${label} skopiowane`);
      } catch {
        setCopyNotice(`Nie udało się skopiować: ${label}`);
      }
    } finally {
      window.setTimeout(() => setCopyNotice(null), 1800);
    }
  }, []);

  const scrollToStagePanel = useCallback(() => {
    const el = document.querySelector('[data-testid=\"stage-panel\"]');
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    loadCvPreview();
  }, [sessionId, lastStage, loadCvPreview]);

  const handleContinueSession = () => {
    if (pendingSession) {
      setSessionId(pendingSession.id);
      try {
        const jobUrl = window.localStorage.getItem(JOB_URL_KEY);
        if (jobUrl) setJobPostingUrl(jobUrl);
        const jobText = window.localStorage.getItem(JOB_TEXT_KEY);
        if (jobText) setJobPostingText(jobText);
      } catch {
        // ignore
      }
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `✅ Kontynuuję poprzednią sesję. Możesz kontynuować edycję CV lub wrzuć nowy plik, żeby zacząć od nowa.`,
        },
      ]);
    }
    setShowSessionDialog(false);
    setPendingSession(null);
  };

  const handleStartFresh = () => {
    // Clear all stored session data
    clearLocalSession();
    setShowSessionDialog(false);
    setPendingSession(null);
  };

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const file = acceptedFiles[0];
      if (
        file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
        file.type === 'application/pdf' ||
        file.name.endsWith('.docx') ||
        file.name.endsWith('.pdf')
      ) {
        setCvFile(file);
        setLatestPdfBase64(null);
        setLastTraceId(null);
        setLastStage(null);
        setStageUpdates([]);

        // New file = new session.
        setSessionId(null);
        try {
          window.localStorage.removeItem(SESSION_ID_KEY);
          window.localStorage.removeItem(SESSION_TIMESTAMP_KEY);
        } catch {
          // ignore
        }

        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `Plik załadowany: ${file.name} (${(file.size / 1024).toFixed(1)} KB)\n\nWklej ofertę (opcjonalnie) i kliknij „Użyj tego CV”.`,
          },
        ]);
      }
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/pdf': ['.pdf'],
    },
    noClick: false,
  });

  const handleJobUrlChange = (value: string) => {
    const v = value.trim();
    setJobPostingUrl(v || null);
    try {
      if (v) {
        window.localStorage.setItem(JOB_URL_KEY, v);
      } else {
        window.localStorage.removeItem(JOB_URL_KEY);
      }
    } catch {
      // ignore
    }
  };

  const handleSendUserAction = async (actionId: string, actionPayload?: Record<string, any>) => {
    if (!actionId.trim()) return;
    if (!sessionId) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Please upload a CV first (new session required).',
        },
      ]);
      return;
    }

    setIsLoading(true);

    try {
      const requestBody = {
        message: '',
        session_id: sessionId,
        job_posting_url: jobPostingUrl,
        job_posting_text: jobPostingText,
        user_action: actionPayload ? { id: actionId, payload: actionPayload } : { id: actionId },
      };

      const response = await fetch('/api/process-cv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      const text = await response.text();
      if (!response.ok) {
        if (response.status === 409) {
          let errJson: any = null;
          try {
            errJson = JSON.parse(text || '{}');
          } catch {
            // ignore
          }
          clearLocalSession();
          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content: (errJson?.response as string) || (errJson?.error as string) || 'Session incompatible. Please start a new session.',
            },
          ]);
          return;
        }
        throw new Error(`Server error: ${response.status} - ${text.substring(0, 200)}`);
      }

      const result = JSON.parse(text || '{}');
      if (Array.isArray(result.stage_updates)) {
        setStageUpdates(result.stage_updates as StageUpdate[]);
      } else {
        setStageUpdates([]);
      }

      if (typeof result?.trace_id === 'string' && result.trace_id.trim()) {
        setLastTraceId(result.trace_id);
      }
      if (typeof result?.stage === 'string' && result.stage.trim()) {
        setLastStage(result.stage);
      }

      if (result?.ui_action) {
        setUiAction(result.ui_action as UIAction);
      } else {
        setUiAction(null);
      }

      // Keep CV preview in sync for lock/unlock actions.
      if (result.success && actionId === 'WORK_TOGGLE_LOCK') {
        if (typeof result?.response === 'string' && result.response.trim()) {
          setActionNotice(result.response.trim());
          window.setTimeout(() => setActionNotice(null), 1800);
        }
        void loadCvPreview();
      }

      if (result?.session_id) {
        setSessionId(result.session_id);
        try {
          window.localStorage.setItem(SESSION_ID_KEY, result.session_id);
          window.localStorage.setItem(SESSION_TIMESTAMP_KEY, new Date().toISOString());
        } catch {
          // ignore
        }
      }

      if (typeof result?.job_posting_url === 'string' && result.job_posting_url.trim()) {
        setJobPostingUrl(result.job_posting_url);
        try {
          window.localStorage.setItem(JOB_URL_KEY, result.job_posting_url);
        } catch {
          // ignore
        }
      }
      if (typeof result?.job_posting_text === 'string' && result.job_posting_text.trim()) {
        setJobPostingText(result.job_posting_text);
        try {
          window.localStorage.setItem(JOB_TEXT_KEY, result.job_posting_text);
        } catch {
          // ignore
        }
      }

      if (result.success) {
        const assistantMsg: Message = {
          role: 'assistant',
          content:
            DEBUG_STAGE && result.stage
              ? `[stage=${result.stage}]\n\n${result.response || 'Processing completed'}`
              : result.response || 'Processing completed',
        };
        if (result.pdf_base64) {
          assistantMsg.pdfBase64 = result.pdf_base64;
          setLatestPdfBase64(result.pdf_base64);
        }
        setMessages((prev) => [...prev, assistantMsg]);

        // Keep the CV preview pane in sync after mutations (accept/apply/generate).
        const refreshActions = new Set([
          'WORK_TAILOR_RUN',
          'WORK_TAILOR_ACCEPT',
          'SKILLS_TAILOR_RUN',
          'SKILLS_TAILOR_ACCEPT',
          'REQUEST_GENERATE_PDF',
          'FAST_RUN',
          'FAST_RUN_TO_PDF',
          'CONFIRM_IMPORT_PREFILL_YES',
          'CONTACT_CONFIRM_LOCK',
          'EDU_CONFIRM_LOCK',
          'EDUCATION_CONFIRM_LOCK',
        ]);
        if (actionId && (refreshActions.has(actionId) || actionId.endsWith('_ACCEPT'))) {
          void loadCvPreview();
        }
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `❌ Error: ${result.error}`,
          },
        ]);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            `❌ Błąd: ${errorMessage}` +
            (lastTraceId ? `\n\ntrace_id: ${lastTraceId}` : '') +
            `\n\nWskazówka: jeśli problem się powtarza, kliknij „Kopiuj trace_id” i podeślij mi ten identyfikator.`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const readFileBase64 = async (file: File): Promise<string | undefined> => {
    try {
      return await new Promise<string | undefined>((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          try {
            const result = e.target?.result as string;
            if (!result) return resolve(undefined);
            if (result.startsWith('data:')) {
              const base64Part = result.split(',')[1];
              return resolve(base64Part || undefined);
            }
            resolve(result);
          } catch {
            resolve(undefined);
          }
        };
        reader.onerror = () => resolve(undefined);
        reader.readAsDataURL(file);
      });
    } catch {
      return undefined;
    }
  };

  const startWizardFromUpload = useCallback(
    async (file: File) => {
      if (!file) return;
      if (isLoading) return;
      if (sessionId) return;

      setIsLoading(true);
      setUiAction(null);
      try {
        const docx_base64 = await readFileBase64(file);
        if (!docx_base64) {
          throw new Error('Nie udało się odczytać pliku (base64). Spróbuj ponownie.');
        }

        const response = await fetch('/api/process-cv', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: '',
            docx_base64,
            session_id: '',
            job_posting_url: jobPostingUrl || '',
            job_posting_text: jobPostingText || '',
            client_context: {
              fast_path_profile: fastPathProfile,
            },
          }),
        });

        const text = await response.text();
        if (!response.ok) throw new Error(`Server error: ${response.status} - ${text.substring(0, 200)}`);

        const result = JSON.parse(text || '{}');
        if (Array.isArray(result.stage_updates)) setStageUpdates(result.stage_updates as StageUpdate[]);
        else setStageUpdates([]);

        if (typeof result?.trace_id === 'string' && result.trace_id.trim()) setLastTraceId(result.trace_id);
        if (typeof result?.stage === 'string' && result.stage.trim()) setLastStage(result.stage);

        if (result?.ui_action) setUiAction(result.ui_action as UIAction);
        else setUiAction(null);

        if (result?.session_id) {
          setSessionId(result.session_id);
          try {
            window.localStorage.setItem(SESSION_ID_KEY, result.session_id);
            window.localStorage.setItem(SESSION_TIMESTAMP_KEY, new Date().toISOString());
          } catch {
            // ignore
          }
        }

        if (result.success) {
          setMessages((prev) => [...prev, { role: 'assistant', content: result.response || 'Kreator uruchomiony.' }]);
        } else {
          setMessages((prev) => [...prev, { role: 'assistant', content: `❌ Error: ${result.error || 'unknown error'}` }]);
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        setMessages((prev) => [...prev, { role: 'assistant', content: `❌ Błąd: ${errorMessage}` }]);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, sessionId, jobPostingUrl, jobPostingText, fastPathProfile]
  );

  useEffect(() => {
    // Intentionally no auto-start: keep step 1 visible so the user can paste job offer URL/text
    // and explicitly confirm "Użyj tego CV" before starting the wizard.
  }, []);

  const [formDraft, setFormDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    // When backend sends editable fields, seed local form state from fields.
    const fields = Array.isArray(uiAction?.fields) ? uiAction?.fields : [];
    const hasEditable = uiAction?.kind === 'edit_form' || fields.some((f) => !!f?.editable);
    if (hasEditable) {
      const next: Record<string, string> = {};
      fields.forEach((f) => {
        if (f && typeof f.key === 'string') next[f.key] = String(f.value ?? '');
      });
      setFormDraft(next);
    }
  }, [uiAction?.kind, uiAction?.fields]);

  // Format timestamp for display
  const formatSessionTime = (isoString: string) => {
    if (isoString === 'unknown') return 'nieznany czas';
    try {
      const date = new Date(isoString);
      return date.toLocaleString('pl-PL', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return 'nieznany czas';
    }
  };

  const wizardStep = (() => {
    const title = String(uiAction?.title || '');
    const m = title.match(/Stage\s+(\d+)\s*\/\s*(\d+)/i);
    if (!m) return null;
    const current = Number(m[1]);
    const total = Number(m[2]);
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
    return { current, total };
  })();

  const describeMissing = (key: string): { label: string; hint: string } => {
    const map: Record<string, { label: string; hint: string }> = {
      full_name: { label: 'Imię i nazwisko', hint: 'Uzupełnij w kroku „Kontakt”.' },
      email: { label: 'Email', hint: 'Uzupełnij w kroku „Kontakt”.' },
      phone: { label: 'Telefon', hint: 'Uzupełnij w kroku „Kontakt”.' },
      address_lines: { label: 'Adres', hint: 'Uzupełnij w kroku „Kontakt” (jeśli wymagane w strict_template).' },
      profile: { label: 'Profil', hint: 'Dodaj krótki profil w danych CV (lub wykonaj sugestie w kroku).'},
      languages: { label: 'Języki', hint: 'Dodaj języki w danych CV (lub wykonaj sugestie w kroku).'},
      it_ai_skills: { label: 'Umiejętności IT & AI', hint: 'Uzupełnij/zaakceptuj w kroku „Skills”.' },
      technical_operational_skills: { label: 'Umiejętności techniczne', hint: 'Uzupełnij/zaakceptuj w kroku „Skills”.' },
      work_experience: { label: 'Doświadczenie', hint: 'W kroku „Work experience” zaakceptuj propozycję lub popraw dane.' },
      education: { label: 'Edukacja', hint: 'W kroku „Edukacja” potwierdź/uzupełnij wpisy.' },
      contact_not_confirmed: { label: 'Kontakt niepotwierdzony', hint: 'W kroku „Kontakt” kliknij „Save” (i/lub potwierdź).'},
      education_not_confirmed: { label: 'Edukacja niepotwierdzona', hint: 'W kroku „Edukacja” kliknij „Confirm & lock”.'},
    };
    return map[key] || { label: key, hint: 'Otwórz zakładkę „Krok” i wykonaj wymagane akcje.' };
  };

  const requiredLabel = (key: string): string => {
    const map: Record<string, string> = {
      full_name: 'Imię i nazwisko',
      email: 'Email',
      phone: 'Telefon',
      work_experience: 'Doświadczenie',
      education: 'Edukacja',
      address_lines: 'Adres',
      profile: 'Profil',
      languages: 'Języki',
      it_ai_skills: 'IT & AI skills',
      technical_operational_skills: 'Technical & operational skills',
    };
    return map[key] || key;
  };

  return (
    <div className="flex h-screen bg-slate-50 p-4 gap-4">
      {/* Session Resume Dialog */}
      {showSessionDialog && pendingSession && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 max-w-md mx-4 shadow-xl border border-slate-200">
            <h3 className="text-base font-semibold text-slate-900 mb-2">Znaleziono poprzednią sesję</h3>
            <p className="text-sm text-slate-600 mb-4">
              Masz zapisaną sesję CV z {formatSessionTime(pendingSession.timestamp)}.
              <br />
              Czy chcesz kontynuować poprzednią pracę czy zacząć od nowa?
            </p>
            <div className="flex gap-3">
              <Button className="flex-1" onClick={handleContinueSession}>
                Kontynuuj
              </Button>
              <Button className="flex-1" variant="secondary" onClick={handleStartFresh}>
                Zacznij od nowa
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Main Wizard (Step 1 = upload, then run as wizard) */}
      {!sessionId ? (
        <Card className="flex-1 flex flex-col overflow-hidden">
          <div className="p-6 border-b border-slate-200 bg-white">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-900">CV Generator</div>
                <div className="mt-1 text-xs text-slate-600">Krok 1/6 — wgraj CV (DOCX/PDF), potem przejdziesz przez kreator.</div>
              </div>
              <Button
                size="sm"
                variant="danger"
                onClick={() => {
                  clearLocalSession();
                  setCvFile(null);
                  setMessages([INITIAL_ASSISTANT_MESSAGE]);
                  setExpandedMessages({});
                }}
                data-testid="new-session"
              >
                Nowa sesja
              </Button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            <div
              {...getRootProps()}
              data-testid="cv-upload-dropzone"
              className={`border border-dashed rounded-xl p-10 text-center cursor-pointer transition flex items-center justify-center ${
                isDragActive ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'
              }`}
            >
              <input {...getInputProps()} />
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
                  <Button
                    size="sm"
                    onClick={() => void startWizardFromUpload(cvFile)}
                    loading={isLoading}
                    disabled={isLoading}
                    data-testid="use-loaded-cv"
                  >
                    Użyj tego CV
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setCvFile(null)}
                    disabled={isLoading}
                    data-testid="change-cv-file"
                  >
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
                  onChange={(e) => {
                    const v = !!e.target.checked;
                    setFastPathProfile(v);
                    try {
                      window.localStorage.setItem(FAST_PROFILE_KEY, v ? '1' : '0');
                    } catch {
                      // ignore
                    }
                  }}
                  disabled={isLoading}
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                Fast path: użyj zapisanego profilu (kontakt, edukacja, zainteresowania, język)
              </label>
              <div className="mt-1 text-[11px] text-slate-600">
                Pozostałe sekcje zawsze są dostosowywane pod konkretną ofertę.
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Link do oferty (opcjonalnie)</label>
              <input
                value={jobPostingUrl || ''}
                onChange={(e) => handleJobUrlChange(e.target.value)}
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
                onChange={(e) => setJobPostingText(e.target.value)}
                placeholder="Wklej opis stanowiska albo krótki skrót wymagań (min. kilka zdań)…"
                disabled={isLoading}
                data-testid="job-text-input"
                className="w-full min-h-[120px] text-sm border border-slate-200 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50 resize-y"
              />
              <div className="text-[11px] text-slate-600 mt-1">To pole przyspiesza analizę (nie musisz czekać na pobranie z URL).</div>
            </div>
          </div>
        </Card>
      ) : null}

      {/* Stage panel (desktop) */}
      <div className={`${!sessionId ? 'hidden' : ''} w-[420px] shrink-0`}>
        <Card className="h-full flex flex-col">
          <div className="border-b border-slate-200 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-900">Krok</div>
                <div className="mt-1 text-xs text-slate-600">Aktualny etap kreatora i akcje.</div>
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  clearLocalSession();
                  setCvFile(null);
                  setMessages([INITIAL_ASSISTANT_MESSAGE]);
                  setExpandedMessages({});
                }}
              >
                Zmień CV
              </Button>
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
                    <div className="text-xs text-slate-600">
                      Krok {wizardStep.current}/{wizardStep.total}
                    </div>
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
                              onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                              disabled={isLoading}
                              className="mt-2 w-full resize-y rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                              rows={8}
                              placeholder={f.placeholder}
                            />
                          ) : (
                            <input
                              value={formDraft[f.key] ?? ''}
                              onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                              disabled={isLoading}
                              className="mt-2 w-full rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                              placeholder={f.placeholder}
                            />
                          )
                        ) : (
                          <div className="mt-1 text-sm text-slate-900 whitespace-pre-wrap break-words">{f.value || ''}</div>
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
                    const primary = actions.filter((a) => !(a.style === 'secondary' || a.style === 'tertiary'));
                    const advanced = actions.filter((a) => a.style === 'secondary' || a.style === 'tertiary');

                    const renderButtons = (items: UIActionButton[]) => (
                      <div className="flex flex-wrap gap-2">
                        {items.map((a) => {
                          const isSecondary = a.style === 'secondary' || a.style === 'tertiary';
                          const isCancel = a.id.endsWith('_CANCEL') || a.id.endsWith('_BACK');
                          const payload = hasEditable && !isCancel ? formDraft : undefined;
                          return (
                            <Button
                              key={a.id}
                              variant={isSecondary ? 'secondary' : 'primary'}
                              onClick={() => {
                                // If we already have a PDF in memory and the action is effectively "download",
                                // download directly instead of round-tripping through the backend.
                                const wantsDownload =
                                  a.id === 'REQUEST_GENERATE_PDF' && String(a.label || '').toLowerCase().includes('pobierz');
                                if (wantsDownload && latestPdfBase64) {
                                  downloadPDF(latestPdfBase64, `CV_${Date.now()}.pdf`);
                                  return;
                                }
                                void handleSendUserAction(a.id, payload);
                              }}
                              loading={isLoading}
                              data-testid={`action-${a.id}`}
                            >
                              {a.label}
                            </Button>
                          );
                        })}
                      </div>
                    );

                    return (
                      <div className="space-y-2">
                        {primary.length ? renderButtons(primary) : renderButtons(actions)}
                        {advanced.length ? (
                          <details className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                            <summary className="cursor-pointer text-xs font-semibold text-slate-800">Więcej akcji</summary>
                            <div className="mt-2">{renderButtons(advanced)}</div>
                          </details>
                        ) : null}
                      </div>
                    );
                  })()
                ) : null}

                {uiAction.disable_free_text ? (
                  <div className="text-xs text-slate-600">W tym kroku wiadomości są wyłączone — użyj akcji powyżej.</div>
                ) : null}

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
              <div
                className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700"
                data-testid="stage-panel"
                data-stage=""
                data-wizard-stage={lastStage || ''}
              >
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

      {/* CV panel (desktop) */}
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
                  <Button size="sm" variant="secondary" onClick={() => setShowCvJson((v) => !v)}>
                    {showCvJson ? 'Widok' : 'JSON'}
                  </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    copyText(
                      JSON.stringify({ cv_data: cvPreview?.cv_data, readiness: cvPreview?.readiness, metadata: cvPreview?.metadata }, null, 2),
                      'CV JSON'
                    )
                  }
                  disabled={!cvPreview}
                >
                  Kopiuj
                </Button>
                <Button size="sm" variant="secondary" onClick={loadCvPreview} loading={cvPreviewLoading} disabled={!sessionId}>
                  Odśwież
                </Button>
                {latestPdfBase64 ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => downloadPDF(latestPdfBase64, `CV_${Date.now()}.pdf`)}
                    data-testid="download-pdf"
                  >
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
                      const required = r.required_present || {};
                      const confirmed = r.confirmed_flags || {};
                      const missing: string[] = Array.isArray(r.missing) ? r.missing : [];
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
                                  <Button size="sm" variant="secondary" onClick={scrollToStagePanel}>
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
                        const ci = d.contact_information || {};
                        const name = ci.full_name ?? d.full_name ?? '';
                        const email = ci.email ?? d.email ?? '';
                        const phone = ci.phone ?? d.phone ?? '';
                        const addr = Array.isArray(d.address_lines) ? d.address_lines.join('\n') : d.address ?? '';
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
                    <summary className="cursor-pointer text-sm font-semibold text-slate-900">Profil</summary>
                    <div className="mt-2 text-sm text-slate-900 whitespace-pre-wrap break-words">
                      {String(cvPreview.cv_data?.profile || '') || '(brak)'}
                    </div>
                  </details>

                  <details className="rounded-lg border border-slate-200 bg-white p-3">
                    <summary className="cursor-pointer text-sm font-semibold text-slate-900">Doświadczenie</summary>
                    <div className="mt-2 space-y-2 text-sm text-slate-900">
                      {Array.isArray(cvPreview.cv_data?.work_experience) && cvPreview.cv_data.work_experience.length ? (
                        cvPreview.cv_data.work_experience.slice(0, 12).map((r: any, i: number) => (
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
                                const locks = cvPreview?.metadata?.work_role_locks || {};
                                const isLocked = !!locks?.[String(i)];
                                return (
                                  <Button
                                    size="sm"
                                    variant={isLocked ? 'secondary' : 'primary'}
                                    onClick={() => {
                                      setActionNotice('Aktualizuję lock…');
                                      setCvPreview((prev) => {
                                        if (!prev) return prev;
                                        const locks = { ...(prev.metadata?.work_role_locks || {}) };
                                        const k = String(i);
                                        if (locks[k]) delete locks[k];
                                        else locks[k] = true;
                                        return { ...prev, metadata: { ...(prev.metadata || {}), work_role_locks: locks } };
                                      });
                                      void handleSendUserAction('WORK_TOGGLE_LOCK', { role_index: i });
                                    }}
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
                                {r.bullets.slice(0, 6).map((b: any, bi: number) => (
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
                        cvPreview.cv_data.education.map((e: any, i: number) => (
                          <div key={i} className="rounded-md border border-slate-200 bg-slate-50 p-2">
                            <div className="font-semibold">{String(e.title || '').trim() || '(bez tytułu)'}</div>
                            <div className="text-xs text-slate-600">
                              {[e.institution || e.school, e.date_range].filter(Boolean).map((x: any) => String(x)).join(' — ')}
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
                        const it = Array.isArray(d.it_ai_skills) ? d.it_ai_skills : [];
                        const ops = Array.isArray(d.technical_operational_skills) ? d.technical_operational_skills : [];
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

      {/* Right panel: logs / admin / user (desktop) */}
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
                <Button size="sm" variant="secondary" onClick={() => copyText(lastTraceId, 'trace_id')}>
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

    </div>
  );
}
