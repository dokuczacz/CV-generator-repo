'use client';

import type { HTMLAttributes, InputHTMLAttributes } from 'react';
import { useState, useRef, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { downloadPDF } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { UploadStartSection } from './cv/sections/UploadStartSection';
import { WizardStageSection } from './cv/sections/WizardStageSection';
import { CvPreviewSection } from './cv/sections/CvPreviewSection';
import { OpsSection } from './cv/sections/OpsSection';
import { useProcessCvClient } from './cv/hooks/useProcessCvClient';
import type { CVSessionPreview, Message, StageUpdate, StepperItem, UIAction, WizardStep } from './cv/types';

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
  const { postProcessCv } = useProcessCvClient();
  const [messages, setMessages] = useState<Message[]>([INITIAL_ASSISTANT_MESSAGE]);
  const [expandedMessages, setExpandedMessages] = useState<Record<number, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [jobPostingUrl, setJobPostingUrl] = useState<string | null>(null);
  const [jobPostingText, setJobPostingText] = useState<string | null>(null);
  const [fastPathProfile, setFastPathProfile] = useState(true);
  const [uiAction, setUiAction] = useState<UIAction | null>(null);
  const [resumeFailed, setResumeFailed] = useState<string | null>(null);
  const [latestPdfBase64, setLatestPdfBase64] = useState<string | null>(null);
  const [latestPdfFilename, setLatestPdfFilename] = useState<string | null>(null);
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
    setLatestPdfFilename(null);
    setLastTraceId(null);
    setLastStage(null);
    setStageUpdates([]);
    setCvPreview(null);
    setCvPreviewError(null);
    setResumeFailed(null);
    try {
      window.localStorage.removeItem(SESSION_ID_KEY);
      window.localStorage.removeItem(JOB_URL_KEY);
      window.localStorage.removeItem(JOB_TEXT_KEY);
      window.localStorage.removeItem(SESSION_TIMESTAMP_KEY);
    } catch {
      // ignore
    }
  };

  const resumeStoredSession = useCallback(
    async (storedSessionId: string, opts?: { silent?: boolean }) => {
      const silent = !!opts?.silent;
      try {
        setIsLoading(true);
        setResumeFailed(null);

        const response = await postProcessCv({
          message: 'continue',
          session_id: storedSessionId,
          job_posting_url: jobPostingUrl || '',
          job_posting_text: jobPostingText || '',
        });

        if (!response.ok) {
          throw new Error(`Server error: ${response.status} - ${response.text.substring(0, 200)}`);
        }

        const result = response.json;
        if (Array.isArray(result.stage_updates)) {
          setStageUpdates(result.stage_updates as StageUpdate[]);
        }
        if (typeof result?.trace_id === 'string' && result.trace_id.trim()) {
          setLastTraceId(result.trace_id);
        }
        if (typeof result?.stage === 'string' && result.stage.trim()) {
          setLastStage(result.stage);
        }
        if (result?.ui_action) {
          setUiAction(result.ui_action as UIAction);
        }
        if (result?.session_id && typeof result.session_id === 'string') {
          setSessionId(result.session_id);
        }

        if (!silent) {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: result?.response || '✅ Wznowiono poprzednią sesję.' },
          ]);
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        setResumeFailed(errorMessage);
        clearLocalSession();
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `⚠️ Nie udało się wznowić sesji: ${errorMessage}` },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [jobPostingText, jobPostingUrl, postProcessCv]
  );

  useEffect(() => {
    try {
      const storedSessionId = window.localStorage.getItem(SESSION_ID_KEY);
      const storedFastProfile = window.localStorage.getItem(FAST_PROFILE_KEY);

      if (storedSessionId) {
        setSessionId(storedSessionId);
        try {
          const jobUrl = window.localStorage.getItem(JOB_URL_KEY);
          if (jobUrl) setJobPostingUrl(jobUrl);
          const jobText = window.localStorage.getItem(JOB_TEXT_KEY);
          if (jobText) setJobPostingText(jobText);
        } catch {
          // ignore
        }
        void resumeStoredSession(storedSessionId, { silent: true });
      }
      if (storedFastProfile === '0' || storedFastProfile === '1') {
        setFastPathProfile(storedFastProfile === '1');
      }
    } catch {
      // ignore
    }
  }, [resumeStoredSession]);

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
        setLatestPdfFilename(null);
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

      const response = await postProcessCv(requestBody);
      if (!response.ok) {
        if (response.status === 409) {
          let errJson: any = null;
          try {
            errJson = response.json;
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
        throw new Error(`Server error: ${response.status} - ${response.text.substring(0, 200)}`);
      }

      const result = response.json;
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
        if (actionId === 'NEW_VERSION_RESET') {
          setLatestPdfBase64(null);
          setLatestPdfFilename(null);
        }

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
          if (typeof result.filename === 'string' && result.filename.trim()) {
            setLatestPdfFilename(result.filename.trim());
          }

          const isCoverLetterAction = actionId === 'COVER_LETTER_GENERATE' || actionId === 'COVER_LETTER_PREVIEW';
          if (isCoverLetterAction) {
            const fallbackName = `CoverLetter_${Date.now()}.pdf`;
            const downloadName =
              typeof result.filename === 'string' && result.filename.trim() ? result.filename.trim() : fallbackName;
            downloadPDF(result.pdf_base64, downloadName);
          }
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
          'NEW_VERSION_RESET',
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

        const response = await postProcessCv({
          message: '',
          docx_base64,
          session_id: '',
          job_posting_url: jobPostingUrl || '',
          job_posting_text: jobPostingText || '',
          client_context: {
            fast_path_profile: fastPathProfile,
          },
        });

        if (!response.ok) throw new Error(`Server error: ${response.status} - ${response.text.substring(0, 200)}`);

        const result = response.json;
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
    [isLoading, sessionId, jobPostingUrl, jobPostingText, fastPathProfile, postProcessCv]
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

  const wizardStep = (() => {
    const title = String(uiAction?.title || '');
    const m = title.match(/Stage\s+(\d+)\s*\/\s*(\d+)/i);
    if (!m) return null;
    const current = Number(m[1]);
    const total = Number(m[2]);
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
    return { current, total };
  })();

  const latestPdfDownloadName = (() => {
    if (!cvPreview?.metadata || typeof cvPreview.metadata !== 'object') return null;
    const pdfRefs = (cvPreview.metadata as any)?.pdf_refs;
    if (!pdfRefs || typeof pdfRefs !== 'object') return null;
    const entries = Object.entries(pdfRefs as Record<string, any>).filter(([, v]) => v && typeof v === 'object');
    if (!entries.length) return null;
    entries.sort((a, b) => String(b[1]?.created_at || '').localeCompare(String(a[1]?.created_at || '')));
    const latest = entries[0]?.[1];
    const name = String(latest?.download_name || '').trim();
    return name || null;
  })();

  const stepper = (() => {
    if (!wizardStep || wizardStep.total !== 6) return null;
    return [
      { n: 1, label: 'Kontakt', targetWizardStage: 'contact' },
      { n: 2, label: 'Edukacja', targetWizardStage: 'education' },
      { n: 3, label: 'Oferta (opcjonalnie)', targetWizardStage: 'job_posting' },
      { n: 4, label: 'Doświadczenie', targetWizardStage: 'work_experience' },
      { n: 5, label: 'Skills', targetWizardStage: 'it_ai_skills' },
      { n: 6, label: 'PDF', targetWizardStage: 'review_final' },
    ] as const;
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

  const dropzoneRootProps = getRootProps() as HTMLAttributes<HTMLDivElement>;
  const dropzoneInputProps = getInputProps() as InputHTMLAttributes<HTMLInputElement>;
  const hasGeneratedPdf = !!(cvPreview?.metadata as Record<string, unknown> | undefined)?.pdf_generated;

  const handleHardNewSession = () => {
    clearLocalSession();
    setCvFile(null);
    setMessages([INITIAL_ASSISTANT_MESSAGE]);
    setExpandedMessages({});
  };

  const handleNewVersion = () => {
    void handleSendUserAction('NEW_VERSION_RESET');
  };

  const handleFastPathChange = (value: boolean) => {
    setFastPathProfile(value);
    try {
      window.localStorage.setItem(FAST_PROFILE_KEY, value ? '1' : '0');
    } catch {
      // ignore
    }
  };

  const handleJobPostingTextChange = (value: string) => {
    setJobPostingText(value);
  };

  const handleCopyCvJson = () => {
    void copyText(JSON.stringify({ cv_data: cvPreview?.cv_data, readiness: cvPreview?.readiness, metadata: cvPreview?.metadata }, null, 2), 'CV JSON');
  };

  const handleDownloadLatestPdf = () => {
    if (!latestPdfBase64) return;
    downloadPDF(latestPdfBase64, latestPdfDownloadName || latestPdfFilename || `CV_${Date.now()}.pdf`);
  };

  const handleToggleWorkLock = (roleIndex: number) => {
    setActionNotice('Aktualizuję lock…');
    setCvPreview((prev) => {
      if (!prev) return prev;
      const prevMeta = (prev.metadata || {}) as Record<string, unknown>;
      const prevLocks = (prevMeta.work_role_locks || {}) as Record<string, boolean>;
      const locks = { ...prevLocks };
      const key = String(roleIndex);
      if (locks[key]) delete locks[key];
      else locks[key] = true;
      return { ...prev, metadata: { ...prevMeta, work_role_locks: locks } as Record<string, unknown> };
    });
    void handleSendUserAction('WORK_TOGGLE_LOCK', { role_index: roleIndex });
  };

  return (
    <div className="flex h-screen bg-slate-50 p-4 gap-4">
      {!sessionId ? (
        <UploadStartSection
          resumeFailed={resumeFailed}
          isDragActive={isDragActive}
          dropzoneRootProps={dropzoneRootProps}
          dropzoneInputProps={dropzoneInputProps}
          cvFile={cvFile}
          isLoading={isLoading}
          fastPathProfile={fastPathProfile}
          jobPostingUrl={jobPostingUrl}
          jobPostingText={jobPostingText}
          onUseLoadedCv={() => {
            if (!cvFile) return;
            void startWizardFromUpload(cvFile);
          }}
          onChangeFile={() => setCvFile(null)}
          onFastPathChange={handleFastPathChange}
          onJobUrlChange={handleJobUrlChange}
          onJobPostingTextChange={handleJobPostingTextChange}
          onNewSession={handleHardNewSession}
        />
      ) : null}

      <WizardStageSection
        sessionId={sessionId}
        uiAction={uiAction}
        lastStage={lastStage}
        lastTraceId={lastTraceId}
        wizardStep={wizardStep as WizardStep}
        stepper={stepper as readonly StepperItem[] | null}
        isLoading={isLoading}
        latestPdfBase64={latestPdfBase64}
        latestPdfFilename={latestPdfFilename}
        latestPdfDownloadName={latestPdfDownloadName}
        hasGeneratedPdf={hasGeneratedPdf}
        formDraft={formDraft}
        stageUpdates={stageUpdates}
        messages={messages}
        onFormDraftChange={(key, value) => setFormDraft((prev) => ({ ...prev, [key]: value }))}
        onSendUserAction={handleSendUserAction}
        onStartFresh={handleNewVersion}
        onChangeFile={handleHardNewSession}
        onRefresh={loadCvPreview}
        cvPreviewLoading={cvPreviewLoading}
      />

      <CvPreviewSection
        cvFile={cvFile}
        sessionId={sessionId}
        cvPreview={cvPreview}
        cvPreviewError={cvPreviewError}
        cvPreviewLoading={cvPreviewLoading}
        showCvJson={showCvJson}
        copyNotice={copyNotice}
        actionNotice={actionNotice}
        latestPdfBase64={latestPdfBase64}
        latestPdfFilename={latestPdfFilename}
        latestPdfDownloadName={latestPdfDownloadName}
        isLoading={isLoading}
        onToggleShowCvJson={() => setShowCvJson((v) => !v)}
        onCopyCvJson={handleCopyCvJson}
        onRefresh={loadCvPreview}
        onDownloadPdf={handleDownloadLatestPdf}
        onScrollToStagePanel={scrollToStagePanel}
        onToggleWorkLock={handleToggleWorkLock}
        describeMissing={describeMissing}
        requiredLabel={requiredLabel}
      />

      <OpsSection
        visible={Boolean(sessionId || cvFile)}
        lastStage={lastStage}
        lastTraceId={lastTraceId}
        stageUpdates={stageUpdates}
        messages={messages}
        onCopyTraceId={() => {
          if (!lastTraceId) return;
          void copyText(lastTraceId, 'trace_id');
        }}
      />
    </div>
  );
}
