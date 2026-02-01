'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { downloadPDF } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Modal } from '@/components/ui/modal';

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

type PreviewTab = 'step' | 'cv' | 'pdf';

type CVSessionPreview = {
  cv_data: any;
  metadata: any;
  readiness: any;
};

const SESSION_ID_KEY = 'cvgen:session_id';
const JOB_URL_KEY = 'cvgen:job_posting_url';
const JOB_TEXT_KEY = 'cvgen:job_posting_text';
const SESSION_TIMESTAMP_KEY = 'cvgen:session_timestamp';
const DEBUG_STAGE = process.env.NEXT_PUBLIC_CV_DEBUG_STAGE === '1';

const INITIAL_ASSISTANT_MESSAGE: Message = {
  role: 'assistant',
  content: 'Cześć! Wgraj swoje CV (DOCX lub PDF) albo opisz informacje o sobie. Pomogę Ci wygenerować profesjonalne CV w PDF.',
};

export default function CVGenerator() {
  const [messages, setMessages] = useState<Message[]>([INITIAL_ASSISTANT_MESSAGE]);
  const [expandedMessages, setExpandedMessages] = useState<Record<number, boolean>>({});
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [jobPostingUrl, setJobPostingUrl] = useState<string | null>(null);
  const [jobPostingText, setJobPostingText] = useState<string | null>(null);
  const [uiAction, setUiAction] = useState<UIAction | null>(null);
  const [showSessionDialog, setShowSessionDialog] = useState(false);
  const [pendingSession, setPendingSession] = useState<{ id: string; timestamp: string } | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewTab, setPreviewTab] = useState<PreviewTab>('step');
  const [latestPdfBase64, setLatestPdfBase64] = useState<string | null>(null);
  const [latestPdfUrl, setLatestPdfUrl] = useState<string | null>(null);
  const [lastTraceId, setLastTraceId] = useState<string | null>(null);
  const [lastStage, setLastStage] = useState<string | null>(null);
  const [cvPreview, setCvPreview] = useState<CVSessionPreview | null>(null);
  const [cvPreviewError, setCvPreviewError] = useState<string | null>(null);
  const [cvPreviewLoading, setCvPreviewLoading] = useState(false);
  const [showCvJson, setShowCvJson] = useState(false);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const clearLocalSession = () => {
    setSessionId(null);
    setJobPostingUrl(null);
    setJobPostingText(null);
    setUiAction(null);
    setLatestPdfBase64(null);
    setLastTraceId(null);
    setLastStage(null);
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

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    try {
      const storedSessionId = window.localStorage.getItem(SESSION_ID_KEY);
      const storedTimestamp = window.localStorage.getItem(SESSION_TIMESTAMP_KEY);

      if (storedSessionId) {
        // Found a previous session - ask user if they want to continue or start fresh
        setPendingSession({
          id: storedSessionId,
          timestamp: storedTimestamp || 'unknown',
        });
        setShowSessionDialog(true);
      }
      // Job URL/text are only loaded if user chooses to continue session
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (!latestPdfBase64) {
      setLatestPdfUrl(null);
      return;
    }
    try {
      const byteCharacters = atob(latestPdfBase64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      setLatestPdfUrl(url);
      return () => URL.revokeObjectURL(url);
    } catch {
      setLatestPdfUrl(null);
    }
  }, [latestPdfBase64]);

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

  useEffect(() => {
    if (previewTab !== 'cv') return;
    if (!sessionId) return;
    loadCvPreview();
  }, [previewTab, sessionId, loadCvPreview]);

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

        // New file = new session.
        setSessionId(null);
        setJobPostingUrl(null);
        setJobPostingText(null);
        try {
          window.localStorage.removeItem(SESSION_ID_KEY);
          window.localStorage.removeItem(JOB_URL_KEY);
          window.localStorage.removeItem(JOB_TEXT_KEY);
          window.localStorage.removeItem(SESSION_TIMESTAMP_KEY);
        } catch {
          // ignore
        }

        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `Plik załadowany: ${file.name} (${(file.size / 1024).toFixed(1)} KB)\n\nNapisz, co chcesz uzyskać (np. „wygeneruj CV po angielsku” albo „dopasuj do oferty”).`,
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

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;
    if (uiAction?.disable_free_text) return;

    const userMessage = inputValue;
    setInputValue('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);
    setUiAction(null);

    try {
      let docx_base64: string | undefined;

      // Only send the file once (to create a session). Later turns use session_id (stateless API).
      if (cvFile && !sessionId) {
        docx_base64 = await new Promise<string | undefined>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            try {
              const result = e.target?.result as string;
              if (!result) {
                resolve(undefined);
                return;
              }
              // Check if it's data URL format (starts with data:)
              if (result.startsWith('data:')) {
                const base64Part = result.split(',')[1];
                resolve(base64Part || undefined);
              } else {
                // If it's already base64
                resolve(result);
              }
            } catch (err) {
              console.error('Error parsing base64:', err);
              resolve(undefined);
            }
          };
          reader.onerror = (err) => {
            console.error('FileReader error:', err);
            resolve(undefined);
          };
          reader.readAsDataURL(cvFile);
        });
        
        console.log('File loaded, base64 length:', docx_base64?.length || 0);
      }

      const payload = {
        message: userMessage,
        docx_base64,
        session_id: sessionId,
        job_posting_url: jobPostingUrl,
        job_posting_text: jobPostingText,
      };
      
      console.log('=== Frontend Request ===');
      console.log('Message:', userMessage);
      console.log('Has docx_base64:', !!docx_base64);
      console.log('Base64 length:', docx_base64?.length || 0);
      console.log('Payload size:', JSON.stringify(payload).length, 'bytes');

      const response = await fetch('/api/process-cv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      console.log('Response status:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Response error:', errorText);

        // Handle deterministic "start fresh" errors (409 session incompatible) without throwing.
        if (response.status === 409) {
          let errJson: any = null;
          try {
            errJson = JSON.parse(errorText || '{}');
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

        // If the session is missing/expired, clear local session state so the user can re-upload cleanly.
        if (errorText.includes('Session not found or expired')) {
          clearLocalSession();
        }
        throw new Error(`Server error: ${response.status} - ${errorText.substring(0, 200)}`);
      }

      const result = await response.json();
      console.log('Result:', {
        success: result.success,
        hasResponse: !!result.response,
        hasPDF: !!result.pdf_base64,
        session_id: result.session_id,
        stage: result.stage,
        stage_seq: result.stage_seq,
      });
      if (Array.isArray(result.stage_updates) && result.stage_updates.length) {
        console.log('Stage updates:', result.stage_updates);
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
          setPreviewTab('pdf');
        }

        setMessages((prev) => [...prev, assistantMsg]);
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
      console.error('=== Frontend Error ===', error);
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
    setMessages((prev) => [...prev, { role: 'user', content: `[Action] ${actionId}` }]);

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
          setPreviewTab('pdf');
        }
        setMessages((prev) => [...prev, assistantMsg]);
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

  const [formDraft, setFormDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    // When backend sends an edit_form, seed local form state from fields.
    if (uiAction?.kind === 'edit_form' && Array.isArray(uiAction.fields)) {
      const next: Record<string, string> = {};
      uiAction.fields.forEach((f) => {
        if (f && typeof f.key === 'string') next[f.key] = String(f.value ?? '');
      });
      setFormDraft(next);
    }
  }, [uiAction?.kind, uiAction?.fields]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

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

      {/* Sidebar - File Upload */}
      <Card className="w-80 shrink-0 p-6 flex flex-col">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="text-sm font-semibold text-slate-900">CV Generator</div>
          {uiAction?.title ? <Badge variant="accent">{uiAction.title}</Badge> : null}
        </div>

        <div
          {...getRootProps()}
          data-testid="cv-upload-dropzone"
          className={`border border-dashed rounded-xl p-6 text-center cursor-pointer transition flex-1 flex items-center justify-center ${
            isDragActive
              ? 'border-indigo-400 bg-indigo-50'
              : cvFile
                ? 'border-emerald-200 bg-emerald-50'
                : 'border-slate-200 bg-white hover:bg-slate-50'
          }`}
        >
          <input {...getInputProps()} />
          {cvFile ? (
            <div className="space-y-2">
              <div className="text-xs font-semibold text-emerald-700">Plik gotowy</div>
              <p className="text-sm font-semibold text-slate-900">{cvFile.name}</p>
              <p className="text-xs text-slate-600">{(cvFile.size / 1024).toFixed(1)} KB</p>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-900">{isDragActive ? 'Upuść tutaj' : 'Wgraj CV'}</p>
              <p className="text-xs text-slate-600">DOCX lub PDF</p>
            </div>
          )}
        </div>

        <div className="mt-4">
          <label className="block text-xs font-semibold text-slate-700 mb-1">Link do oferty (opcjonalnie)</label>
          <input
            value={jobPostingUrl || ''}
            onChange={(e) => handleJobUrlChange(e.target.value)}
            placeholder="https://…"
            disabled={isLoading}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
          />
          <div className="text-[11px] text-slate-600 mt-1">Jeśli backend nie pobierze treści, poprosi o wklejenie tekstu.</div>
        </div>

        <div className="mt-4 pt-4 border-t border-slate-200 text-xs text-slate-600">
          <p className="font-semibold mb-2">Jak pracujemy:</p>
          <ul className="space-y-1">
            <li>1. Wgraj CV</li>
            <li>2. Wykonuj kroki w kreatorze</li>
            <li>3. Wygeneruj PDF i pobierz</li>
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setPreviewTab('step');
                setPreviewOpen(true);
              }}
              data-testid="open-preview"
            >
              Podgląd kroku / PDF
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={() => {
                clearLocalSession();
                setCvFile(null);
                setMessages([INITIAL_ASSISTANT_MESSAGE]);
                setExpandedMessages({});
                setInputValue('');
              }}
              data-testid="new-session"
            >
              Nowa sesja
            </Button>
          </div>
        </div>
      </Card>

      {/* Main Chat Area */}
      <Card className="flex-1 flex flex-col overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((msg, idx) => {
            const len = msg.content?.length || 0;
            // Keep user messages collapsible for very long pastes; show assistant messages fully unless extreme.
            const collapseThreshold = msg.role === 'assistant' ? 30000 : 8000;
            const isCollapsible = len > collapseThreshold;
            const isExpanded = !!expandedMessages[idx];
            const toggleExpand = () =>
              setExpandedMessages((prev) => ({ ...prev, [idx]: !isExpanded }));
            const displayContent =
              isCollapsible && !isExpanded
                ? `${msg.content.slice(0, collapseThreshold)}\n...[ukryto ${len - collapseThreshold} znaków]`
                : msg.content;

            return (
              <div
                key={idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-2xl rounded-xl border p-4 ${
                    msg.role === 'user'
                      ? 'border-indigo-600 bg-indigo-600 text-white'
                      : 'border-slate-200 bg-white text-slate-900'
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words">{displayContent}</p>
                  {isCollapsible && (
                    <button
                      onClick={toggleExpand}
                      className={`mt-2 text-sm ${
                        msg.role === 'user' ? 'text-white/90 hover:text-white' : 'text-indigo-700 hover:text-indigo-900'
                      }`}
                    >
                      {isExpanded ? 'Pokaż mniej' : 'Pokaż więcej'}
                    </button>
                  )}
                  {msg.pdfBase64 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setLatestPdfBase64(msg.pdfBase64!);
                          setPreviewTab('pdf');
                          setPreviewOpen(true);
                        }}
                      >
                        Podgląd PDF
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => downloadPDF(msg.pdfBase64!, `CV_${idx}.pdf`)}>
                        Pobierz PDF
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {isLoading && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 text-slate-900">
              <div className="flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
                <span>Przetwarzanie…</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-slate-200 bg-white p-4 space-y-3">
          <div className="xl:hidden space-y-3">
          {uiAction?.kind === 'review_form' && Array.isArray(uiAction.fields) ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              {uiAction.title ? <div className="font-semibold text-slate-900 mb-1">{uiAction.title}</div> : null}
              {uiAction.text ? <div className="text-sm text-slate-700 whitespace-pre-wrap mb-3">{uiAction.text}</div> : null}
              <div className="space-y-2 mb-3">
                {uiAction.fields.map((f) => (
                  <div key={f.key} className="bg-white border border-slate-200 rounded-lg p-2">
                    <div className="text-xs font-semibold text-slate-600 mb-1">{f.label}</div>
                    <div className="text-sm text-slate-900 whitespace-pre-wrap break-words">{f.value || ''}</div>
                  </div>
                ))}
              </div>
              {uiAction.actions?.length ? (
                <div className="flex flex-wrap gap-2">
                  {uiAction.actions.map((a) => (
                    <Button
                      key={a.id}
                      onClick={() => handleSendUserAction(a.id)}
                      loading={isLoading}
                      size="sm"
                      variant={a.style === 'secondary' || a.style === 'tertiary' ? 'secondary' : 'primary'}
                    >
                      {a.label}
                    </Button>
                  ))}
                </div>
              ) : null}
              {uiAction.disable_free_text ? (
                <div className="text-xs text-slate-600 mt-2">Wiadomości są wyłączone w tym kroku.</div>
              ) : null}
            </div>
          ) : null}

          {uiAction?.kind === 'edit_form' && Array.isArray(uiAction.fields) ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              {uiAction.title ? <div className="font-semibold text-slate-900 mb-1">{uiAction.title}</div> : null}
              {uiAction.text ? <div className="text-sm text-slate-700 whitespace-pre-wrap mb-3">{uiAction.text}</div> : null}

              <div className="space-y-3 mb-3">
                {uiAction.fields.map((f) => (
                  <div key={f.key}>
                    <div className="text-xs font-semibold text-slate-600 mb-1">{f.label}</div>
                    {f.type === 'textarea' ? (
                      <textarea
                        value={formDraft[f.key] ?? ''}
                        onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                        disabled={isLoading}
                        className="w-full p-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y disabled:bg-slate-50"
                        rows={8}
                      />
                    ) : (
                      <input
                        value={formDraft[f.key] ?? ''}
                        onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                        disabled={isLoading}
                        className="w-full p-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                      />
                    )}
                  </div>
                ))}
              </div>

              {uiAction.actions?.length ? (
                <div className="flex flex-wrap gap-2">
                  {uiAction.actions.map((a) => (
                    <Button
                      key={a.id}
                      onClick={() => {
                        // Most edit_form actions expect the current form fields (e.g. ANALYZE).
                        // Send formDraft by default unless this is clearly a navigation-only action.
                        const isNavOnly = a.id.endsWith('_CANCEL') || a.id.endsWith('_BACK') || a.id.endsWith('_CONTINUE');
                        handleSendUserAction(a.id, isNavOnly ? undefined : formDraft);
                      }}
                      loading={isLoading}
                      size="sm"
                      variant={a.style === 'secondary' || a.style === 'tertiary' ? 'secondary' : 'primary'}
                    >
                      {a.label}
                    </Button>
                  ))}
                </div>
              ) : null}

              {uiAction.disable_free_text ? (
                <div className="text-xs text-slate-600 mt-2">Wiadomości są wyłączone w tym kroku.</div>
              ) : null}
            </div>
          ) : null}

          {uiAction?.kind !== 'review_form' && uiAction?.kind !== 'edit_form' && uiAction?.actions?.length ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              {uiAction.title ? <div className="font-semibold text-slate-900 mb-1">{uiAction.title}</div> : null}
              {uiAction.text ? <div className="text-sm text-slate-700 whitespace-pre-wrap mb-3">{uiAction.text}</div> : null}
              <div className="flex flex-wrap gap-2">
                {uiAction.actions.map((a) => (
                  <Button
                    key={a.id}
                    onClick={() => handleSendUserAction(a.id)}
                    loading={isLoading}
                    size="sm"
                    variant={a.style === 'secondary' || a.style === 'tertiary' ? 'secondary' : 'primary'}
                  >
                    {a.label}
                  </Button>
                ))}
              </div>
              {uiAction.disable_free_text ? (
                <div className="text-xs text-slate-600 mt-2">Wiadomości są wyłączone w tym kroku.</div>
              ) : null}
            </div>
          ) : null}
          </div>

          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading || !!uiAction?.disable_free_text}
            placeholder={uiAction?.disable_free_text ? 'W tym kroku użyj akcji powyżej.' : 'Napisz wiadomość… (Shift+Enter = nowa linia)'}
            className="w-full p-3 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none disabled:bg-slate-50"
            rows={3}
          />

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs text-slate-600">
              {lastTraceId ? (
                <span>
                  trace_id: <span className="font-mono">{lastTraceId}</span>
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              {copyNotice ? <span className="text-xs text-emerald-700">{copyNotice}</span> : null}
              {lastTraceId ? (
                <Button size="sm" variant="secondary" onClick={() => copyText(lastTraceId, 'trace_id')}>
                  Kopiuj trace_id
                </Button>
              ) : null}
            </div>
          </div>

          <Button
            onClick={handleSendMessage}
            disabled={isLoading || !inputValue.trim() || !!uiAction?.disable_free_text}
            loading={isLoading}
            className="w-full"
          >
            Wyślij
          </Button>
        </div>
      </Card>

      {/* Preview Panel (desktop) */}
      <div className="hidden xl:block w-[380px] shrink-0">
        <Card className="h-full flex flex-col">
          <div className="border-b border-slate-200 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-900">Podgląd</div>
                <div className="mt-1 text-xs text-slate-600">Aktualny krok + PDF (gdy dostępny).</div>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant={previewTab === 'step' ? 'primary' : 'secondary'} onClick={() => setPreviewTab('step')}>
                  Krok
                </Button>
                <Button
                  size="sm"
                  variant={previewTab === 'cv' ? 'primary' : 'secondary'}
                  onClick={() => {
                    setShowCvJson(false);
                    setPreviewTab('cv');
                  }}
                >
                  CV
                </Button>
                <Button size="sm" variant={previewTab === 'pdf' ? 'primary' : 'secondary'} onClick={() => setPreviewTab('pdf')}>
                  PDF
                </Button>
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {previewTab === 'step' ? (
              uiAction ? (
                <div className="space-y-4" data-testid="stage-panel">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold text-slate-900">{uiAction.title || 'Aktualny krok'}</div>
                    {uiAction.stage ? <Badge variant="accent">{uiAction.stage}</Badge> : null}
                  </div>
                  {wizardStep ? (
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1">
                        {Array.from({ length: wizardStep.total }).map((_, i) => {
                          const active = i < wizardStep.current;
                          return (
                            <span
                              key={i}
                              className={`h-2 w-2 rounded-full ${active ? 'bg-indigo-600' : 'bg-slate-200'}`}
                              aria-hidden="true"
                            />
                          );
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
                          {uiAction.kind === 'edit_form' ? (
                            f.type === 'textarea' ? (
                              <textarea
                                value={formDraft[f.key] ?? ''}
                                onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                                disabled={isLoading}
                                className="mt-2 w-full resize-y rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                                rows={8}
                              />
                            ) : (
                              <input
                                value={formDraft[f.key] ?? ''}
                                onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                                disabled={isLoading}
                                className="mt-2 w-full rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
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
                    <div className="flex flex-wrap gap-2">
                      {uiAction.actions.map((a) => {
                        const isSecondary = a.style === 'secondary' || a.style === 'tertiary';
                        const isNavOnly = a.id.endsWith('_CANCEL') || a.id.endsWith('_BACK') || a.id.endsWith('_CONTINUE');
                        const payload = uiAction.kind === 'edit_form' && !isNavOnly ? formDraft : undefined;
                        return (
                          <Button
                            key={a.id}
                            variant={isSecondary ? 'secondary' : 'primary'}
                            onClick={() => handleSendUserAction(a.id, payload)}
                            loading={isLoading}
                            data-testid={`action-${a.id}`}
                          >
                            {a.label}
                          </Button>
                        );
                      })}
                    </div>
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
                <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700" data-testid="stage-panel">
                  Brak aktywnego kroku. Wgraj CV lub wyślij wiadomość.
                </div>
              )
            ) : previewTab === 'cv' ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-900">Podgląd danych CV</div>
                  <div className="flex items-center gap-2">
                    {copyNotice ? <span className="text-xs text-emerald-700">{copyNotice}</span> : null}
                    <Button size="sm" variant="secondary" onClick={() => setPreviewTab('step')}>
                      Krok
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setShowCvJson((v) => !v)}>
                      {showCvJson ? 'Widok' : 'JSON'}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        copyText(
                          JSON.stringify(
                            { cv_data: cvPreview?.cv_data, readiness: cvPreview?.readiness, metadata: cvPreview?.metadata },
                            null,
                            2
                          ),
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
                  </div>
                </div>

                {!sessionId ? (
                  <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak aktywnej sesji.</div>
                ) : cvPreviewError ? (
                  <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
                    Nie udało się pobrać danych sesji: {cvPreviewError}
                  </div>
                ) : cvPreviewLoading && !cvPreview ? (
                  <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Ładowanie…</div>
                ) : cvPreview ? (
                  showCvJson ? (
                    <pre className="overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-800">
                      {JSON.stringify(
                        { cv_data: cvPreview.cv_data, readiness: cvPreview.readiness, metadata: cvPreview.metadata },
                        null,
                        2
                      )}
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
                          const canGenerate = !!r.can_generate;
                          const strict = !!r.strict_template;
                          const items = Object.entries(required).filter(([, v]) => typeof v === 'boolean') as Array<[string, boolean]>;
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
                                      <Button size="sm" variant="secondary" onClick={() => setPreviewTab('step')}>
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
                            const addr = Array.isArray(d.address_lines) ? d.address_lines.join('\n') : (d.address ?? '');
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
                                <div className="font-semibold">
                                  {String(r.title || r.position || '').trim() || '(bez tytułu)'}{' '}
                                  {String(r.company || r.employer || '').trim() ? `— ${String(r.company || r.employer)}` : ''}
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
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-900">Podgląd PDF</div>
                  {latestPdfBase64 ? (
                    <Button size="sm" variant="secondary" onClick={() => downloadPDF(latestPdfBase64, `CV_${Date.now()}.pdf`)}>
                      Pobierz
                    </Button>
                  ) : null}
                </div>
                {latestPdfUrl ? (
                  <iframe
                    title="PDF preview"
                    src={latestPdfUrl}
                    className="h-[720px] w-full rounded-lg border border-slate-200 bg-white"
                    data-testid="pdf-preview"
                  />
                ) : (
                  <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
                    Brak PDF do podglądu. Wygeneruj PDF w ostatnim kroku kreatora.
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Preview Modal (mobile + quick access) */}
      <Modal open={previewOpen} title="Podgląd" description="Krok (akcje) oraz PDF w jednym miejscu." onClose={() => setPreviewOpen(false)}>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant={previewTab === 'step' ? 'primary' : 'secondary'} onClick={() => setPreviewTab('step')}>
            Krok
          </Button>
          <Button
            size="sm"
            variant={previewTab === 'cv' ? 'primary' : 'secondary'}
            onClick={() => {
              setShowCvJson(false);
              setPreviewTab('cv');
            }}
          >
            CV
          </Button>
          <Button size="sm" variant={previewTab === 'pdf' ? 'primary' : 'secondary'} onClick={() => setPreviewTab('pdf')}>
            PDF
          </Button>
        </div>

        <div className="mt-4">
          {previewTab === 'step' ? (
            uiAction ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-sm font-semibold text-slate-900">{uiAction.title || 'Aktualny krok'}</div>
                  {uiAction.stage ? <Badge variant="accent">{uiAction.stage}</Badge> : null}
                </div>
                {wizardStep ? (
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1">
                      {Array.from({ length: wizardStep.total }).map((_, i) => {
                        const active = i < wizardStep.current;
                        return (
                          <span
                            key={i}
                            className={`h-2 w-2 rounded-full ${active ? 'bg-indigo-600' : 'bg-slate-200'}`}
                            aria-hidden="true"
                          />
                        );
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
                        {uiAction.kind === 'edit_form' ? (
                          f.type === 'textarea' ? (
                            <textarea
                              value={formDraft[f.key] ?? ''}
                              onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                              disabled={isLoading}
                              className="mt-2 w-full resize-y rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                              rows={8}
                            />
                          ) : (
                            <input
                              value={formDraft[f.key] ?? ''}
                              onChange={(e) => setFormDraft((prev) => ({ ...prev, [f.key]: e.target.value }))}
                              disabled={isLoading}
                              className="mt-2 w-full rounded-md border border-slate-200 bg-white p-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
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
                  <div className="flex flex-wrap gap-2">
                    {uiAction.actions.map((a) => {
                      const isSecondary = a.style === 'secondary' || a.style === 'tertiary';
                      const isNavOnly = a.id.endsWith('_CANCEL') || a.id.endsWith('_BACK') || a.id.endsWith('_CONTINUE');
                      const payload = uiAction.kind === 'edit_form' && !isNavOnly ? formDraft : undefined;
                      return (
                        <Button key={a.id} variant={isSecondary ? 'secondary' : 'primary'} onClick={() => handleSendUserAction(a.id, payload)} loading={isLoading}>
                          {a.label}
                        </Button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak aktywnego kroku.</div>
            )
          ) : previewTab === 'cv' ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold text-slate-900">Podgląd danych CV</div>
                <div className="flex items-center gap-2">
                  {copyNotice ? <span className="text-xs text-emerald-700">{copyNotice}</span> : null}
                  <Button size="sm" variant="secondary" onClick={() => setPreviewTab('step')}>
                    Krok
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setShowCvJson((v) => !v)}>
                    {showCvJson ? 'Widok' : 'JSON'}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      copyText(
                        JSON.stringify(
                          { cv_data: cvPreview?.cv_data, readiness: cvPreview?.readiness, metadata: cvPreview?.metadata },
                          null,
                          2
                        ),
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
                </div>
              </div>

              {!sessionId ? (
                <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak aktywnej sesji.</div>
              ) : cvPreviewError ? (
                <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
                  Nie udało się pobrać danych sesji: {cvPreviewError}
                </div>
              ) : cvPreviewLoading && !cvPreview ? (
                <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Ładowanie…</div>
              ) : cvPreview ? (
                showCvJson ? (
                  <pre className="overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-800">
                    {JSON.stringify(
                      { cv_data: cvPreview.cv_data, readiness: cvPreview.readiness, metadata: cvPreview.metadata },
                      null,
                      2
                    )}
                  </pre>
                ) : (
                  <div className="space-y-3">
                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <div className="text-xs font-semibold text-slate-600">Gotowość</div>
                      {(() => {
                        const r = cvPreview.readiness || {};
                        const required = r.required_present || {};
                        const missing: string[] = Array.isArray(r.missing) ? r.missing : [];
                        const items = Object.entries(required).filter(([, v]) => typeof v === 'boolean') as Array<[string, boolean]>;
                        return (
                          <div className="mt-2 space-y-3">
                            <div className="flex flex-wrap items-center gap-2">
                              {r.can_generate ? <Badge variant="success">Gotowe do PDF</Badge> : <Badge variant="warning">Nie gotowe</Badge>}
                              {r?.confirmed_flags?.contact_confirmed ? <Badge variant="success">Kontakt OK</Badge> : <Badge variant="warning">Kontakt niepotwierdzony</Badge>}
                              {r?.confirmed_flags?.education_confirmed ? <Badge variant="success">Edukacja OK</Badge> : <Badge variant="warning">Edukacja niepotwierdzona</Badge>}
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
                            ) : null}

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
                                    <Button size="sm" variant="secondary" onClick={() => setPreviewTab('step')}>
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
                          const addr = Array.isArray(d.address_lines) ? d.address_lines.join('\n') : (d.address ?? '');
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
                          cvPreview.cv_data.work_experience.slice(0, 8).map((r: any, i: number) => (
                            <div key={i} className="rounded-md border border-slate-200 bg-slate-50 p-2">
                              <div className="font-semibold">
                                {String(r.title || r.position || '').trim() || '(bez tytułu)'}{' '}
                                {String(r.company || r.employer || '').trim() ? `— ${String(r.company || r.employer)}` : ''}
                              </div>
                              <div className="text-xs text-slate-600">{String(r.date_range || '').trim()}</div>
                              {Array.isArray(r.bullets) && r.bullets.length ? (
                                <ul className="mt-2 list-disc space-y-1 pl-5">
                                  {r.bullets.slice(0, 4).map((b: any, bi: number) => (
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
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold text-slate-900">Podgląd PDF</div>
                {latestPdfBase64 ? (
                  <Button size="sm" variant="secondary" onClick={() => downloadPDF(latestPdfBase64, `CV_${Date.now()}.pdf`)}>
                    Pobierz
                  </Button>
                ) : null}
              </div>
              {latestPdfUrl ? (
                <iframe title="PDF preview" src={latestPdfUrl} className="h-[70vh] w-full rounded-lg border border-slate-200 bg-white" />
              ) : (
                <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">Brak PDF do podglądu.</div>
              )}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
