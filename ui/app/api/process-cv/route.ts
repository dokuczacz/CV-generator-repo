import { NextRequest, NextResponse } from 'next/server';
import OpenAI from 'openai';
import mammoth from 'mammoth';
import { CV_STAGE_PROMPT, CV_SYSTEM_PROMPT, type CVStage } from '@/lib/prompts';
import { CV_TOOLS_RESPONSES } from '@/lib/tools';
import {
  buildBaseInputList,
  buildResponsesRequest,
  buildUserContent,
  determineCurrentPhase,
  roughInputChars,
  sanitizeToolOutputForModel,
} from '@/lib/capsule';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const DEBUG_TOKENS = process.env.CV_DEBUG_TOKENS === '1';

function clampStr(v: any, max: number): string {
  const s = typeof v === 'string' ? v : v == null ? '' : String(v);
  return s.length <= max ? s : s.slice(0, max);
}

async function autoFixForTwoPages(sessionId: string, language: string) {
  // Deterministic safety net: when PDF generation fails due to 2-page DoD, clamp content to known limits.
  // This avoids a model/tool thrash loop and keeps the product reliable.
  const sessionResp = await callAzureFunction('/get-cv-session', { session_id: sessionId });
  const cv = sessionResp?.cv_data || {};

  const fixedWork = (Array.isArray(cv.work_experience) ? cv.work_experience : []).slice(0, 5).map((j: any) => {
    const bullets = Array.isArray(j?.bullets) ? j.bullets : [];
    const fixedBullets = bullets
      .map((b: any) => clampStr(b, 80).trim())
      .filter(Boolean)
      .slice(0, 4);
    return {
      date_range: clampStr(j?.date_range, 25).trim(),
      employer: clampStr(j?.employer, 60).trim(),
      location: clampStr(j?.location, 50).trim(),
      title: clampStr(j?.title, 80).trim(),
      bullets: fixedBullets,
    };
  });

  const fixedEdu = (Array.isArray(cv.education) ? cv.education : []).slice(0, 3).map((e: any) => {
    const details = Array.isArray(e?.details) ? e.details : [];
    const fixedDetails = details
      .map((d: any) => clampStr(d, 120).trim())
      .filter(Boolean)
      .slice(0, 4);
    return {
      date_range: clampStr(e?.date_range, 20).trim(),
      institution: clampStr(e?.institution, 70).trim(),
      title: clampStr(e?.title, 90).trim(),
      details: fixedDetails,
    };
  });

  const fixedLanguages = (Array.isArray(cv.languages) ? cv.languages : [])
    .map((x: any) => clampStr(x, 50).trim())
    .filter(Boolean)
    .slice(0, 5);

  const fixedSkills = (Array.isArray(cv.it_ai_skills) ? cv.it_ai_skills : [])
    .map((x: any) => clampStr(x, 70).trim())
    .filter(Boolean)
    .slice(0, 8);

  const fixedProfile = clampStr(cv.profile || cv.summary || '', 320).trim();

  // Big page-2 sections are the main DoD risk; keep them minimal when we hit overflow.
  const fixedFurther: any[] = [];
  const fixedInterests = clampStr(cv.interests || '', 250).trim();
  const fixedReferences = clampStr(cv.references || '', 140).trim();

  const updates: Array<{ field_path: string; value: any }> = [
    { field_path: 'language', value: language },
    { field_path: 'profile', value: fixedProfile },
    { field_path: 'work_experience', value: fixedWork },
    { field_path: 'education', value: fixedEdu },
    { field_path: 'languages', value: fixedLanguages },
    { field_path: 'it_ai_skills', value: fixedSkills },
    { field_path: 'further_experience', value: fixedFurther },
    { field_path: 'interests', value: fixedInterests },
    { field_path: 'references', value: fixedReferences },
  ];

  for (const u of updates) {
    await callAzureFunction('/update-cv-field', { session_id: sessionId, field_path: u.field_path, value: u.value });
  }
}

async function autoSqueezeForTwoPages(sessionId: string, language: string) {
  // More aggressive deterministic clamp for stubborn 3-page overflows.
  // This keeps entry counts (work/education) but reduces per-entry verbosity.
  const sessionResp = await callAzureFunction('/get-cv-session', { session_id: sessionId });
  const cv = sessionResp?.cv_data || {};

  const fixedWork = (Array.isArray(cv.work_experience) ? cv.work_experience : []).slice(0, 5).map((j: any) => {
    const bullets = Array.isArray(j?.bullets) ? j.bullets : [];
    const fixedBullets = bullets
      .map((b: any) => clampStr(b, 65).trim())
      .filter(Boolean)
      .slice(0, 3);
    return {
      date_range: clampStr(j?.date_range, 22).trim(),
      employer: clampStr(j?.employer, 55).trim(),
      location: clampStr(j?.location, 35).trim(),
      title: clampStr(j?.title, 60).trim(),
      bullets: fixedBullets,
    };
  });

  const fixedEdu = (Array.isArray(cv.education) ? cv.education : []).slice(0, 2).map((e: any) => {
    return {
      date_range: clampStr(e?.date_range, 18).trim(),
      institution: clampStr(e?.institution, 60).trim(),
      title: clampStr(e?.title, 70).trim(),
      details: [],
    };
  });

  const fixedLanguages = (Array.isArray(cv.languages) ? cv.languages : [])
    .map((x: any) => clampStr(x, 45).trim())
    .filter(Boolean)
    .slice(0, 5);

  const fixedProfile = clampStr(cv.profile || cv.summary || '', 240).trim();

  const updates: Array<{ field_path: string; value: any }> = [
    { field_path: 'language', value: language },
    { field_path: 'profile', value: fixedProfile },
    { field_path: 'work_experience', value: fixedWork },
    { field_path: 'education', value: fixedEdu },
    { field_path: 'languages', value: fixedLanguages },
    // Remove page-2 content entirely in squeeze mode.
    { field_path: 'it_ai_skills', value: [] },
    { field_path: 'further_experience', value: [] },
    { field_path: 'interests', value: '' },
    { field_path: 'references', value: '' },
    { field_path: 'certifications', value: [] },
  ];

  for (const u of updates) {
    await callAzureFunction('/update-cv-field', { session_id: sessionId, field_path: u.field_path, value: u.value });
  }
}

function wantsGenerate(userMessage: string): boolean {
  // IMPORTANT: Do NOT scan the entire user message for keywords like "final" or "pdf".
  // Users often paste job postings that contain phrases like "final product" which should
  // not trigger PDF generation. Only consider the "intent header" (first couple lines).
  const raw = (userMessage || '').trim();
  if (!raw) return false;

  const intentHeader = raw
    .split('\n')
    .slice(0, 3)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .slice(0, 400);

  if (!intentHeader) return false;

  // If the user is explicitly saying "don't generate", never treat as approval.
  const negative = /\b(do not|don't|not yet|stop|cancel|no|nie|nie generuj|nie tworz|bez generowania|bez pdf)\b/i;
  if (negative.test(intentHeader)) return false;

  // Explicit approval / command only. Avoid weak signals like plain "ok".
  const explicit =
    /\b(proceed|ok to generate|go ahead|generate pdf|generate the pdf|generate cv|create pdf|make pdf|download pdf|finalize|finalise|zatwierdzam|zatwierd[zź]|generuj)\b/i;

  return explicit.test(intentHeader);
}

function getResponseUsageSummary(response: any): {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
} | null {
  const usage = response?.usage;
  if (!usage) return null;

  // Responses API typically returns { input_tokens, output_tokens, total_tokens }.
  const input_tokens = usage.input_tokens ?? usage.prompt_tokens;
  const output_tokens = usage.output_tokens ?? usage.completion_tokens;
  const total_tokens = usage.total_tokens ?? usage.total;

  if (
    typeof input_tokens !== 'number' &&
    typeof output_tokens !== 'number' &&
    typeof total_tokens !== 'number'
  ) {
    return null;
  }

  return { input_tokens, output_tokens, total_tokens };
}

function extractFirstUrl(text: string): string | null {
  const m = text.match(/https?:\/\/[^\s)\]]+/i);
  if (!m) return null;
  // Trim common trailing punctuation
  const cleaned = m[0].replace(/[),.]+$/, '');
  // Guard against obviously incomplete URLs (very short) which often 404.
  if (cleaned.length < 20) return null;
  return cleaned;
}

function wantsSkipPhoto(text: string): boolean {
  return /\b(skip photo|omit photo|without photo|no photo|bez zdj[eę]cia|pomi[nń] zdj[eę]cie)\b/i.test(
    text
  );
}

function detectLanguage(text: string, defaultLang: 'pl' | 'en' | 'de' = 'en'): 'pl' | 'en' | 'de' {
  const t = (text || '').toLowerCase();

  // Explicit language switch patterns (avoid triggering on proficiency mentions like "German B2").
  const explicitDe = /\b(write|respond|reply|switch|use|generate|produce|in)\s+(german|deutsch)\b/;
  const explicitPl = /\b(write|respond|reply|switch|use|generate|produce|in)\s+(polish|polski|po polsku)\b/;
  const explicitEn = /\b(write|respond|reply|switch|use|generate|produce|in)\s+(english|angielski)\b/;
  const langTag = /\blang\s*[:=]\s*(en|de|pl)\b/;

  const mTag = t.match(langTag);
  if (mTag?.[1]) return mTag[1] as 'pl' | 'en' | 'de';
  if (explicitDe.test(t)) return 'de';
  if (explicitPl.test(t)) return 'pl';
  if (explicitEn.test(t)) return 'en';

  // Fallback: keep current/default language even if proficiency is mentioned (e.g., "German B2").
  return defaultLang;
}

async function extractDocxTextFromBase64(docxBase64: string): Promise<string | null> {
  try {
    const buffer = Buffer.from(docxBase64, 'base64');
    const result = await mammoth.extractRawText({ buffer });
    const text = (result?.value || '').replace(/\s+/g, ' ').trim();
    return text || null;
  } catch {
    return null;
  }
}

async function fetchJobPostingText(url: string): Promise<string | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);

    const resp = await fetch(url, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'cv-generator-ui/1.0 (+job-posting-fetch)',
        'Accept-Language': 'en-US,en;q=0.9,de;q=0.8,pl;q=0.7',
        Accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
      },
    });

    clearTimeout(timeout);
    if (!resp.ok) {
      console.warn(`⚠️ Job posting fetch failed: url=${url} status=${resp.status}`);
      return null;
    }

    const html = await resp.text();
    const withoutScripts = html
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ');

    const text = withoutScripts
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    if (!text) {
      console.warn(`⚠️ Job posting fetch returned empty text: url=${url}`);
      return null;
    }

    // Keep it bounded to avoid token bloat, but allow "full" job postings (usually a few KB).
    const bounded = text.slice(0, 20000);
    console.log(`🧾 Job posting fetched: url=${url} chars=${bounded.length}`);
    return bounded;
  } catch {
    console.warn(`⚠️ Job posting fetch threw: url=${url}`);
    return null;
  }
}

async function callAzureFunction(endpoint: string, body: any) {
  const baseUrlRaw =
    process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_URL ||
    (process.env.NODE_ENV === 'development' ? 'http://127.0.0.1:7071/api' : '');
  const baseUrl = baseUrlRaw.replace(/\/+$/, '');
  if (!baseUrl) {
    throw new Error(
      'Missing NEXT_PUBLIC_AZURE_FUNCTIONS_URL (set it to your Functions base URL, e.g. http://127.0.0.1:7071/api)'
    );
  }

  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = `${baseUrl}${path}`;

  const functionsKey = process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_KEY || '';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      ...(functionsKey ? { 'x-functions-key': functionsKey } : {}),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let details = '';
    try {
      details = await response.text();
    } catch {
      details = '';
    }
    const snippet = details ? details.slice(0, 800) : '';
    // Log server-side for UI log visibility (helps detect silent tool failures)
    console.error(
      `❌ Azure Function call failed: ${url} status=${response.status} ${response.statusText} ` +
        (snippet ? `body=${snippet}` : '')
    );
    throw new Error(
      `Azure Function error: ${response.status} ${response.statusText}${snippet ? ` - ${snippet}` : ''}`
    );
  }
  // Handle PDF responses (application/pdf) by converting to base64
  const contentType = (response.headers.get('content-type') || '').toLowerCase();
  if (contentType.includes('application/pdf')) {
    const buf = await response.arrayBuffer();
    // Buffer is available in the Node.js runtime for Next.js API routes
    const pdfBase64 = Buffer.from(buf).toString('base64');
    return { pdf_base64: pdfBase64 };
  }
  // Default: JSON response
  return response.json();
}

async function processToolCall(toolName: string, toolInput: any): Promise<string> {
  try {
    const client_context = toolInput?.client_context && typeof toolInput.client_context === 'object'
      ? toolInput.client_context
      : undefined;
    switch (toolName) {
      case 'extract_and_store_cv': {
        const result = await callAzureFunction('/extract-and-store-cv', {
          docx_base64: toolInput.docx_base64,
          language: toolInput.language,
          extract_photo: toolInput.extract_photo,
          job_posting_url: toolInput.job_posting_url,
          job_posting_text: toolInput.job_posting_text,
        });
        return JSON.stringify(result);
      }

      case 'get_cv_session': {
        const result = await callAzureFunction('/get-cv-session', {
          session_id: toolInput.session_id,
          ...(client_context ? { client_context } : {}),
        });
        return JSON.stringify(result);
      }

      case 'update_cv_field': {
        const result = await callAzureFunction('/update-cv-field', {
          session_id: toolInput.session_id,
          field_path: toolInput.field_path,
          value: toolInput.value,
          edits: toolInput.edits,
          ...(client_context ? { client_context } : {}),
        });
        return JSON.stringify(result);
      }

      case 'generate_cv_from_session': {
        const result = await callAzureFunction('/generate-cv-from-session', {
          session_id: toolInput.session_id,
          language: toolInput.language,
          ...(client_context ? { client_context } : {}),
        });
        return JSON.stringify(result);
      }

      case 'fetch_job_posting_text': {
        const url = typeof toolInput?.url === 'string' ? toolInput.url.trim() : '';
        if (!url) {
          return JSON.stringify({ success: false, error: 'url is required' });
        }
        const text = await fetchJobPostingText(url);
        return JSON.stringify({
          success: !!(text && text.trim()),
          url,
          job_posting_text: text || '',
        });
      }

      case 'process_cv_orchestrated': {
        const result = await callAzureFunction('/process-cv-orchestrated', {
          session_id: toolInput.session_id,
          docx_base64: toolInput.docx_base64,
          language: toolInput.language,
          edits: toolInput.edits,
          extract_photo: toolInput.extract_photo,
          job_posting_url: toolInput.job_posting_url,
          job_posting_text: toolInput.job_posting_text,
        });
        return JSON.stringify(result);
      }

      default:
        return JSON.stringify({ error: `Unknown tool: ${toolName}` });
    }
  } catch (error) {
    return JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' });
  }
}

function wantsTailorToJobOffer(userMessage: string): boolean {
  const m = (userMessage || '').toLowerCase();
  return (
    m.includes('przygotuj') ||
    m.includes('dopasuj') ||
    m.includes('pod te oferte') ||
    m.includes('pod ofert') ||
    m.includes('tailor') ||
    m.includes('prepare my cv') ||
    m.includes('prepare cv') ||
    m.includes('job offer')
  );
}

function userExplicitlyRequestsInstantGeneration(userMessage: string): boolean {
  // Only trigger fast-path if user explicitly opts out of consultation
  // Keywords must be very specific to avoid false positives
  const m = (userMessage || '').toLowerCase();

  const instantKeywords = /\b(instant|immediately|directly|right now|skip.*consult|no.*review|auto.*generate)\b/i;
  const noConsultKeywords = /\b(without.*consult|bypass.*review|straight.*to.*pdf|skip.*preparation)\b/i;

  return instantKeywords.test(m) || noConsultKeywords.test(m);
}

function parseEditsOnlyJson(text: string): { edits: any[]; summary: string; language?: string } {
  const raw = (text || '').trim();
  const attempt = (s: string) => {
    const parsed = JSON.parse(s);
    const edits = Array.isArray(parsed?.edits) ? parsed.edits : [];
    const summary = typeof parsed?.summary === 'string' ? parsed.summary : '';
    const language = typeof parsed?.language === 'string' ? parsed.language : undefined;
    return { edits, summary, language };
  };

  try {
    return attempt(raw);
  } catch {
    // Best-effort: extract the first JSON object block.
    const start = raw.indexOf('{');
    const end = raw.lastIndexOf('}');
    if (start >= 0 && end > start) {
      return attempt(raw.slice(start, end + 1));
    }
    return { edits: [], summary: '' };
  }
}

function userExplicitlyAllowsTrimming(userMessage: string): boolean {
  return /\b(remove|delete|trim|shorten|cut|omit|usu[nń]|wytnij|skró[cć]|obci[aą]ć|wyrzu[cć])\b/i.test(userMessage);
}

function filterUnsafeEdits(args: {
  userMessage: string;
  cvData: any;
  edits: Array<{ field_path?: string; value?: any }>;
}): { edits: Array<{ field_path: string; value: any }>; dropped: string[] } {
  const allowTrim = userExplicitlyAllowsTrimming(args.userMessage);
  const currentWorkCount = Array.isArray(args.cvData?.work_experience) ? args.cvData.work_experience.length : 0;
  const currentEduCount = Array.isArray(args.cvData?.education) ? args.cvData.education.length : 0;
  const dropped: string[] = [];

  const out: Array<{ field_path: string; value: any }> = [];
  for (const e of args.edits || []) {
    const field_path = typeof e?.field_path === 'string' ? e.field_path : '';
    if (!field_path) continue;
    const value = (e as any).value;

    if (!allowTrim && (field_path === 'work_experience' || field_path === 'education') && Array.isArray(value)) {
      const nextLen = value.length;
      const curLen = field_path === 'work_experience' ? currentWorkCount : currentEduCount;
      if (nextLen < curLen) {
        dropped.push(`${field_path}: attempted to reduce entries ${curLen} -> ${nextLen}`);
        continue;
      }
    }

    out.push({ field_path, value });
  }

  return { edits: out, dropped };
}

async function fastPathTailorAndGenerate(args: {
  userMessage: string;
  docx_base64?: string;
  sessionId?: string;
  language: string;
  url: string | null;
  jobText: string | null;
  skipPhoto: boolean;
}): Promise<any> {
  const promptId = process.env.OPENAI_PROMPT_ID;
  const modelOverride = process.env.OPENAI_MODEL;
  if (!promptId) {
    throw new Error('fastPathTailorAndGenerate requires OPENAI_PROMPT_ID');
  }

  let sessionId: string | null = args.sessionId || null;
  try {
    // Step 1: ensure a session exists
    if (!sessionId) {
      if (!args.docx_base64) {
        return {
          response: 'Missing inputs: provide either a prior session_id or a DOCX upload.',
          pdf_base64: '',
          last_response_id: null,
          session_id: null,
          stage: 'bootstrap' as CVStage,
          stage_seq: 0,
          stage_updates: [],
          job_posting_url: args.url,
          job_posting_text: args.jobText,
        };
      }
      const createdRaw = await processToolCall('extract_and_store_cv', {
        docx_base64: args.docx_base64,
        language: args.language,
        extract_photo: !args.skipPhoto,
        job_posting_url: args.url,
        job_posting_text: args.jobText,
      });
      const created = JSON.parse(createdRaw);
      if (created?.error) {
        return {
          response: `Failed to create session: ${created.error}`,
          pdf_base64: '',
          last_response_id: null,
          session_id: null,
          stage: 'bootstrap' as CVStage,
          stage_seq: 0,
          stage_updates: [],
          job_posting_url: args.url,
          job_posting_text: args.jobText,
        };
      }
      if (typeof created?.session_id === 'string' && created.session_id.length > 10) {
        sessionId = created.session_id;
      } else {
        return {
          response: 'Failed to create session (missing session_id).',
          pdf_base64: '',
          last_response_id: null,
          session_id: null,
          stage: 'bootstrap' as CVStage,
          stage_seq: 0,
          stage_updates: [],
          job_posting_url: args.url,
          job_posting_text: args.jobText,
        };
      }
    }

    // Step 2: load full canonical CV data (source of truth)
    const sessionRespRaw = await processToolCall('get_cv_session', { session_id: sessionId });
    const sessionResp = JSON.parse(sessionRespRaw);
    if (sessionResp?.error) {
      return {
        response: `Failed to retrieve session: ${sessionResp.error}`,
        pdf_base64: '',
        last_response_id: null,
        session_id: sessionId,
        stage: 'review_session' as CVStage,
        stage_seq: 0,
        stage_updates: [],
        job_posting_url: args.url,
        job_posting_text: args.jobText,
      };
    }
    const cvData = sessionResp?.cv_data || {};

    // Step 3: one OpenAI call to produce edits[] + summary
    const sessionSnapshot = sanitizeToolOutputForModel('get_cv_session', JSON.stringify(sessionResp));
    const sessionCvJson = JSON.stringify({ session_id: sessionId, cv_data: cvData, metadata: sessionResp?.metadata || {} });

    const jobBlock = args.url
      ? args.jobText
        ? `\n\n[JOB_POSTING_TEXT]\n${args.jobText}`
        : `\n\n[JOB_POSTING_TEXT_MISSING]\nCould not fetch job posting text from ${args.url}. Tailor generically.`
      : '\n\n[JOB_POSTING_TEXT_NONE]\nNo job posting URL provided. Tailor generically.';

    const oneShotUserContent =
      `${args.userMessage}\n\n[SESSION_SNAPSHOT_JSON]\n${sessionSnapshot}\n\n[SESSION_CV_JSON]\n${sessionCvJson}${jobBlock}\n\n[Output language: ${args.language}.]`;

    const inputList = [{ role: 'user', content: oneShotUserContent }];
    const stage: CVStage = 'edits_only';
    const stageSeq = 1;

    const tools = args.jobText ? [] : [{ type: 'web_search' as const }];
    const req = buildResponsesRequest({
      promptId,
      modelOverride,
      stage,
      stageSeq,
      systemPrompt: '',
      stagePrompt: CV_STAGE_PROMPT(stage),
      inputList,
      tools,
    });

    console.log('⚡ fast-path: Calling OpenAI (edits_only) ...');
    const response = await openai.responses.create(req);
    console.log('⚡ fast-path: OpenAI model:', (response as any)?.model || 'unknown');

    const parsed = parseEditsOnlyJson((response as any).output_text || '');
    const filtered = filterUnsafeEdits({ userMessage: args.userMessage, cvData, edits: parsed.edits as any[] });
    if (filtered.dropped.length) {
      console.warn('⚠️ fast-path: dropped unsafe edits:', filtered.dropped);
    }

    // Step 4: apply edits + validate + render in one backend call
    const orchestratedRaw = await processToolCall('process_cv_orchestrated', {
      session_id: sessionId,
      language: parsed.language || args.language,
      edits: filtered.edits,
      extract_photo: false,
      job_posting_url: args.url,
      job_posting_text: args.jobText,
    });
    let orchestrated = JSON.parse(orchestratedRaw);
    let autoFixedValidation = false;

    // Deterministic safety net: if the backend rejects due to validation limits,
    // apply the same clamps we use for DoD overflow and retry once.
    if (orchestrated?.error && typeof sessionId === 'string' && sessionId.trim()) {
      const err = String(orchestrated.error || '');
      if (err.toLowerCase().includes('validation failed')) {
        console.log('🛠️ fast-path: validation failed; applying deterministic clamps and retrying once');
        await autoFixForTwoPages(sessionId, parsed.language || args.language);
        autoFixedValidation = true;

        const retryRaw = await processToolCall('process_cv_orchestrated', {
          session_id: sessionId,
          language: parsed.language || args.language,
          edits: [],
          extract_photo: false,
          job_posting_url: args.url,
          job_posting_text: args.jobText,
        });
        orchestrated = JSON.parse(retryRaw);
      }
    }

    // Deterministic safety net: if we still fail due to strict 2-page DoD, squeeze further and retry once.
    let autoSqueezedDod = false;
    if (orchestrated?.error && typeof sessionId === 'string' && sessionId.trim()) {
      const err = String(orchestrated.error || '');
      const details = String(orchestrated.details || '');
      if (details.includes('DoD violation') || details.includes('pages != 2')) {
        console.log('🛠️ fast-path: DoD overflow (3 pages); applying aggressive squeeze and retrying once');
        await autoSqueezeForTwoPages(sessionId, parsed.language || args.language);
        autoSqueezedDod = true;

        const retryRaw = await processToolCall('process_cv_orchestrated', {
          session_id: sessionId,
          language: parsed.language || args.language,
          edits: [],
          extract_photo: false,
          job_posting_url: args.url,
          job_posting_text: args.jobText,
        });
        orchestrated = JSON.parse(retryRaw);
      }
    }

    const summaryLines = [
      parsed.summary ? `Changes summary:\n${parsed.summary}` : '',
      filtered.dropped.length ? `Dropped unsafe edits:\n- ${filtered.dropped.join('\n- ')}` : '',
      autoFixedValidation
        ? 'Auto-fix applied: clamped CV fields to backend limits (bullets<=4, bullet length<=80, titles truncated).'
        : '',
      autoSqueezedDod
        ? 'Auto-squeeze applied: reduced verbosity further to satisfy strict 2-page DoD (kept entry counts, trimmed page-2 sections).'
        : '',
      orchestrated?.error ? `Backend error: ${orchestrated.error}${orchestrated.details ? ` (${orchestrated.details})` : ''}` : '',
    ]
      .filter(Boolean)
      .join('\n\n');

    const hasPdf = typeof orchestrated?.pdf_base64 === 'string' && orchestrated.pdf_base64.length > 1000;
    return {
      response: summaryLines || (orchestrated?.success ? 'Generated CV updates applied.' : 'Processing completed.'),
      pdf_base64: typeof orchestrated?.pdf_base64 === 'string' ? orchestrated.pdf_base64 : '',
      last_response_id: response?.id,
      session_id: orchestrated?.session_id || sessionId,
      stage: hasPdf ? 'final' : 'draft_proposal',
      stage_seq: stageSeq,
      stage_updates: [{ from: 'edits_only' as CVStage, to: hasPdf ? ('final' as CVStage) : ('draft_proposal' as CVStage), via: 'fast_path' }],
      job_posting_url: args.url,
      job_posting_text: args.jobText,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return {
      response: `Fast-path failed: ${msg}`,
      pdf_base64: '',
      last_response_id: null,
      session_id: sessionId,
      stage: 'draft_proposal' as CVStage,
      stage_seq: 0,
      stage_updates: [],
      job_posting_url: args.url,
      job_posting_text: args.jobText,
    };
  }
}

async function chatWithCV(
  userMessage: string,
  docx_base64?: string,
  sessionId?: string,
  jobPostingUrlFromClient?: string,
  jobPostingTextFromClient?: string
) {
  console.log('\n🤖 Starting chatWithCV');

  const hasDocx = !!docx_base64;
  const hasSession = !!sessionId;
  const skipPhoto = wantsSkipPhoto(userMessage);
  // Default language: stay with EN unless the user explicitly asks to switch.
  const language = detectLanguage(userMessage, 'en');
  const extractedUrl = extractFirstUrl(userMessage);
  const url = extractedUrl || jobPostingUrlFromClient || null;
  const jobText =
    typeof jobPostingTextFromClient === 'string' && jobPostingTextFromClient.trim()
      ? jobPostingTextFromClient
      : url
      ? await fetchJobPostingText(url)
      : null;

  // If we have no job text and we are not in execution, return a minimal ask instead of running OpenAI.
  if (!jobText && stage !== 'generate_pdf' && stage !== 'final') {
    return {
      response:
        'I could not fetch the job posting. Please paste the full job description (responsibilities + requirements + job title/company). I will not summarize or generate until I have it.',
      pdf_base64: '',
      last_response_id: null,
      session_id: sessionId || null,
      stage,
      stage_seq: 0,
      stage_updates: [],
      job_posting_url: url,
      job_posting_text: null,
    };
  }

  // No previous_response_id: treat each HTTP request as stateless.
  // If we already have a session_id, do NOT resend the DOCX text; rely on session state/tools.
  const cvText =
    !hasSession && hasDocx && docx_base64 ? await extractDocxTextFromBase64(docx_base64) : null;
  const boundedCvText = cvText ? cvText.slice(0, 12000) : null;
  if (hasDocx) {
    console.log('📄 Extracted DOCX text:', boundedCvText ? `${boundedCvText.length} chars (bounded)` : 'none');
  }

  // Determine initial stage for phase-aware context
  const userRequestedGenerate = wantsGenerate(userMessage);
  let stage: CVStage = hasSession
    ? userRequestedGenerate
      ? 'generate_pdf'
      : 'review_session'
    : hasDocx
    ? 'extract'
    : 'bootstrap';

  // If session is present, fetch phase-specific ContextPackV2
  // Otherwise, use legacy V1 context pack (or skip for bootstrap/extract)
  let contextPack: any = null;
  if (hasSession && sessionId) {
    try {
      // Determine phase from stage for V2 context pack
      const phase = determineCurrentPhase(stage);
      console.log(`📦 Fetching ContextPackV2 (phase=${phase}) for session ${sessionId.slice(0, 8)}...`);
      const packResp = await callAzureFunction('/generate-context-pack-v2', {
        phase,
        session_id: sessionId,
        job_posting_text: jobText || undefined,
        max_pack_chars: 12000,
      });
      contextPack = packResp;
      console.log(`📦 ContextPackV2 received (phase=${phase}); schema: ${packResp?.schema_version || 'unknown'}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.warn(`⚠️ Failed to fetch ContextPackV2 for session; falling back to session snapshot`, msg);
      contextPack = null;
    }
  } else if (!hasSession && process.env.CV_USE_CONTEXT_PACK === '1' && hasDocx && boundedCvText) {
    // Legacy: V1 context pack for bootstrap/extract phases (no session yet)
    try {
      console.log('🧩 CV_USE_CONTEXT_PACK enabled — requesting ContextPackV1 from backend');
      const packResp = await callAzureFunction('/generate-context-pack', {
        cv_data: { profile: boundedCvText },
        job_posting_text: jobText,
      });
      contextPack = packResp;
      console.log('🧩 ContextPackV1 received; keys:', Object.keys(contextPack || {}));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.warn('⚠️ Failed to build ContextPackV1; falling back to injected CV text', msg);
      contextPack = null;
    }
  }

  // When session_id is present, prefetch a compact session snapshot for the model.
  let sessionSnapshot: string | null = null;
  if (hasSession) {
    try {
      const sessionResp = await callAzureFunction('/get-cv-session', { session_id: sessionId });
      sessionSnapshot = sanitizeToolOutputForModel('get_cv_session', JSON.stringify(sessionResp));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.warn('⚠️ Failed to prefetch session snapshot', msg);
      sessionSnapshot = null;
    }
  }

  const userContent = buildUserContent({
    userMessage,
    hasDocx,
    hasSession,
    sessionId: sessionId || null,
    skipPhoto,
    sessionSnapshot,
    contextPack,
    boundedCvText,
    jobPostingUrl: url,
    jobPostingText: jobText,
    language,
    stage,
  });

  const promptId = process.env.OPENAI_PROMPT_ID;
  const modelOverride = process.env.OPENAI_MODEL;
  const systemPromptToSend = promptId ? '' : CV_SYSTEM_PROMPT;

  // DEPRECATED: Fast-path bypasses consultation phase (violates user intent for CV preparation)
  // Only use if user explicitly requests instant generation without consultation
  // Default: DISABLED (consultation workflow is default for CV document preparation)
  const useFastPath =
    !!promptId &&
    process.env.CV_FAST_PATH === '1' &&  // Changed: Now opt-in (was !== '0')
    (hasDocx || hasSession) &&
    userExplicitlyRequestsInstantGeneration(userMessage);  // Changed: Stricter condition

  if (useFastPath) {
    console.log('⚡ FAST-PATH TRIGGERED: User explicitly requested instant generation without consultation');
    console.log('⚠️  Note: Fast-path is deprecated and should be rare. Consider using consultative workflow.');
    return await fastPathTailorAndGenerate({
      userMessage,
      docx_base64,
      sessionId,
      language,
      url,
      jobText,
      skipPhoto,
    });
  }

  // Parse completeness from session snapshot to gate execution/generation.
  let requiredPresent: Record<string, boolean> | null = null;
  try {
    if (sessionSnapshot) {
      const snap = JSON.parse(sessionSnapshot);
      requiredPresent = snap?.required_present || snap?.completeness?.required_present || null;
    }
  } catch {
    requiredPresent = null;
  }
  const canGenerate =
    (stage === 'generate_pdf' || stage === 'final') &&
    requiredPresent &&
    Object.values(requiredPresent).every(Boolean);

  // Filter tools per stage to prevent accidental generation in preparation/confirmation.
  const toolsForStage = CV_TOOLS_RESPONSES.filter((t: any) => {
    if (t.name === 'generate_cv_from_session' || t.name === 'process_cv_orchestrated') {
      return false; // default blocked; we enable per-iteration below when allowed and not yet attempted
    }
    // Block extract/process if a session already exists (avoid model re-calling extract)
    if ((t.name === 'extract_and_store_cv' || t.name === 'process_cv_orchestrated') && hasSession) {
      return false;
    }
    return true;
  });

  const inputList = buildBaseInputList({ hasDocx, systemPrompt: systemPromptToSend, userContent });

  console.log('📤 Calling OpenAI Responses API...');
  const apiStartTime = Date.now();

  // Stage already initialized above for buildUserContent
  let stageSeq = 0;
  const stageUpdates: Array<{ from: CVStage; to: CVStage; via: string }> = [];
  let generateAllowedThisTurn = canGenerate;

  const stageFromTool = (toolName: string, toolOutputRaw: string): CVStage => {
    if (toolName === 'extract_and_store_cv' || toolName === 'process_cv_orchestrated') {
      return 'review_session';
    }
    if (toolName === 'get_cv_session') {
      return 'draft_proposal';
    }
      if (toolName === 'update_cv_field') {
        return 'draft_proposal';
      }
    if (toolName === 'generate_cv_from_session') {
      try {
        const parsed = JSON.parse(toolOutputRaw);
        if (parsed?.success === true && typeof parsed?.pdf_base64 === 'string' && parsed.pdf_base64.length > 1000) {
          return 'final';
        }
        if (parsed?.validation_errors || parsed?.details || parsed?.error) {
          return 'fix_validation';
        }
      } catch {
        // ignore
      }
      return 'fix_validation';
    }
    return stage;
  };
  // Log prompt ID to verify .env.local is loaded
  console.log('[DEBUG] OpenAI request config:', { promptId, modelOverride, stage, has_prompt: !!promptId });

  const buildRequest = (input: any[], iterationTools?: any[]) =>
    buildResponsesRequest({
      promptId,
      modelOverride,
      stage,
      stageSeq,
      systemPrompt: systemPromptToSend,
      stagePrompt: CV_STAGE_PROMPT(stage),
      inputList: input,
      tools: iterationTools || toolsForStage,
    });

  if (DEBUG_TOKENS) {
    console.log('📏 Input items:', inputList.length, 'rough chars:', roughInputChars(inputList));
  }
  stageSeq += 1;
  let response = await openai.responses.create(
    buildRequest(inputList)
  );

  const firstUsage = getResponseUsageSummary(response);
  if (firstUsage) {
    console.log('🧮 OpenAI usage (initial):', firstUsage);
  }

  console.log('✅ OpenAI response received in', Date.now() - apiStartTime, 'ms');

  let pdfBase64 = '';
  let currentSessionId: string | null = sessionId || null;
  let iteration = 0;
  const maxIterations = 10;
  let extractToolCalls = 0;
  let generateAttempted = false;

  while (iteration < maxIterations) {
    iteration++;
    console.log(`🔄 Iteration ${iteration}/${maxIterations}`);

    const toolCalls = ((response.output || []) as any[]).filter(
      (item) => item?.type === 'function_call'
    ) as any[];
    console.log('🔧 Tool calls:', toolCalls.length);

    if (toolCalls.length === 0) {
      // Deterministic fallback: if the user asked to generate a PDF but the model stopped
      // without calling the generation tool, do one server-side attempt using the current session.
      // Safety: Only allow fallback when this request was already in "generate_pdf" stage.
      // Otherwise, a pasted job posting containing "final" could accidentally auto-generate a PDF.
      if (
        stage === 'generate_pdf' &&
        userRequestedGenerate &&
        !pdfBase64 &&
        typeof currentSessionId === 'string' &&
        currentSessionId.trim() &&
        canGenerate &&
        !generateAttempted
      ) {
        try {
          console.log('🛟 Fallback: user requested PDF; attempting server-side generate_cv_from_session');
          // Preview session state before final generation to ensure edits are persisted
          try {
            const previewRaw = await processToolCall('get_cv_session', { session_id: currentSessionId });
            try {
              const preview = JSON.parse(previewRaw);
              const hasCv = !!preview?.cv_data;
              const lastUpdated =
                preview?._metadata?.updated_at ||
                preview?.updated_at ||
                preview?.last_updated ||
                preview?.timestamp ||
                null;
              const weCount = Array.isArray(preview?.cv_data?.work_experience)
                ? preview.cv_data.work_experience.length
                : undefined;
              console.log('🗃️ Session preview before fallback generate:', { hasCv, lastUpdated, weCount });
            } catch {}
          } catch {}
          const toolArgs: any = { session_id: currentSessionId, language };
          const toolOutput = await processToolCall('generate_cv_from_session', toolArgs);

          let effectiveToolOutput = toolOutput;
          try {
            const parsed = JSON.parse(toolOutput);
            const errorStr = typeof parsed?.error === 'string' ? parsed.error : '';
            const details = typeof parsed?.details === 'string' ? parsed.details : '';
            // Check for validation errors (bullet/text too long) or DoD violations
            const hasValidationError = errorStr.includes('Validation failed') || details.includes('DoD violation');
            if (parsed?.error && hasValidationError) {
              console.log('  🛠️ Fallback auto-fix validation error: applying clamps and retrying generation once');
              await autoFixForTwoPages(currentSessionId, language);
              effectiveToolOutput = await processToolCall('generate_cv_from_session', toolArgs);
              const parsed2 = JSON.parse(effectiveToolOutput);
              const errorStr2 = typeof parsed2?.error === 'string' ? parsed2.error : '';
              const details2 = typeof parsed2?.details === 'string' ? parsed2.details : '';
              const hasValidationError2 = errorStr2.includes('Validation failed') || details2.includes('DoD violation');
              if (parsed2?.error && hasValidationError2) {
                console.log('  🛠️ Fallback auto-squeeze: applying aggressive clamps and retrying once');
                await autoSqueezeForTwoPages(currentSessionId, language);
                effectiveToolOutput = await processToolCall('generate_cv_from_session', toolArgs);
              }
            }
          } catch {
            // ignore
          }

          const parsed = JSON.parse(effectiveToolOutput);
          if (typeof parsed?.pdf_base64 === 'string' && parsed.pdf_base64.length > 1000) {
            pdfBase64 = parsed.pdf_base64;
            generateAttempted = true;
            stageUpdates.push({ from: stage, to: 'final', via: 'server_fallback_generate_cv_from_session' });
            stage = 'final';
            console.log('  📄 Fallback PDF generated, length:', pdfBase64.length);
          } else {
            console.warn('⚠️ Fallback generation did not return a PDF');
            console.warn('   Backend response keys:', Object.keys(parsed || {}).join(', '));
            console.warn('   pdf_base64 type:', typeof parsed?.pdf_base64);
            console.warn('   pdf_base64 length:', parsed?.pdf_base64?.length ?? 'N/A');
            if (parsed?.error) console.warn('   error:', parsed.error);
            if (parsed?.details) console.warn('   details:', parsed.details);
          }
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e);
          console.warn('⚠️ Fallback generation failed', msg);
        }
      }

      const text = (response as any).output_text || '';
      console.log('✅ No more tool calls, finishing');
      return {
        response: text || 'Processing completed',
        pdf_base64: pdfBase64,
        last_response_id: response?.id,
        session_id: currentSessionId,
        stage,
        stage_seq: stageSeq,
        stage_updates: stageUpdates,
        job_posting_url: url,
        job_posting_text: jobText,
      };
    }

    // Per Responses API docs:
    // When store=false (ZDR compliance), response items are NOT persisted.
    // We must add tool_call items (request structures) but NOT function_call_output items
    // (which are transient when store=false and cannot be referenced later).
    //
    // Add tool calls to inputList so we can reference them when sending back outputs.
    if (response.output && Array.isArray(response.output)) {
      for (const item of response.output) {
        if (item?.type === 'function_call') {
          // This is a tool call request; it MUST be in the conversation so outputs can reference it
          inputList.push(item);
        }
        // Skip function_call_output items (they're not persisted with store=false)
      }
    }

    for (const toolCall of toolCalls) {
      const toolName: string = toolCall.name;
      let toolArgs: any = {};

      try {
        toolArgs = toolCall.arguments ? JSON.parse(toolCall.arguments) : {};
      } catch {
        toolArgs = {};
      }

      // Never trust model-provided session ids once we have one (prevents "Session not found" due to bogus ids).
      if (
        (toolName === 'get_cv_session' ||
          toolName === 'update_cv_field' ||
          toolName === 'generate_cv_from_session' ||
          toolName === 'process_cv_orchestrated') &&
        typeof currentSessionId === 'string' &&
        currentSessionId.trim()
      ) {
        toolArgs.session_id = currentSessionId;
      }

      // Batch edits supported via update_cv_field.edits; cv_patch passthrough
      if (toolName === 'update_cv_field') {
        if (toolArgs.edits && !Array.isArray(toolArgs.edits)) {
          toolArgs.edits = undefined;
        }
        if (toolArgs.cv_patch && typeof toolArgs.cv_patch !== 'object') {
          toolArgs.cv_patch = undefined;
        }
      }

      // Attach client context so the backend can store a bounded event ledger (stateless continuity).
      toolArgs.client_context = {
        stage,
        stage_seq: stageSeq,
        source: 'ui/api/process-cv',
      };

      // Inject DOCX base64 if the model omitted it.
      if (toolName === 'extract_and_store_cv') {
        extractToolCalls += 1;
        // Never trust model-provided docx_base64 (it can be truncated/corrupted).
        // If the HTTP request included the DOCX, always inject the exact bytes here.
        if (typeof docx_base64 === 'string' && docx_base64.trim()) {
          toolArgs.docx_base64 = docx_base64;
        }
        toolArgs.language = toolArgs.language || language;
        if (skipPhoto) {
          toolArgs.extract_photo = false;
        }
      }

      if (toolName === 'process_cv_orchestrated') {
        // Same rule: use request-provided DOCX bytes when available.
        if (typeof docx_base64 === 'string' && docx_base64.trim()) {
          toolArgs.docx_base64 = docx_base64;
        }
        toolArgs.language = toolArgs.language || language;
        if (skipPhoto) {
          toolArgs.extract_photo = false;
        }
      }

      if (toolName === 'generate_cv_from_session') {
        toolArgs.language = toolArgs.language || language;
        if (!canGenerate) {
          console.log('  ⛔ generate_cv_from_session blocked (not in execution or required fields missing)');
          inputList.push({
            type: 'function_call_output',
            call_id: toolCall.call_id,
            output: JSON.stringify({
              ok: false,
              blocked: 'generate_not_allowed',
              reason: 'Execution phase not reached or required fields missing',
              required_present: requiredPresent,
            }),
          });
          continue;
        }
        if (generateAttempted) {
          console.log('  ⛔ generate_cv_from_session blocked (already attempted this turn)');
          inputList.push({
            type: 'function_call_output',
            call_id: toolCall.call_id,
            output: JSON.stringify({
              ok: false,
              blocked: 'duplicate_generate',
              reason: 'Only one generate attempt per request',
            }),
          });
          continue;
        }
      }

      if (toolName === 'process_cv_orchestrated' && !canGenerate) {
        console.log('  ⛔ process_cv_orchestrated blocked (not in execution or required fields missing)');
        inputList.push({
          type: 'function_call_output',
          call_id: toolCall.call_id,
          output: JSON.stringify({
            ok: false,
            blocked: 'orchestrated_not_allowed',
            reason: 'Execution phase not reached or required fields missing',
            required_present: requiredPresent,
          }),
        });
        continue;
      }

      console.log(`  → Calling tool: ${toolName}`);
      console.log(`  📋 Tool args keys:`, Object.keys(toolArgs));
      if (toolName === 'generate_cv_from_session' || toolName === 'process_cv_orchestrated') {
        console.log(`  📋 ${toolName} args preview:`, {
          session_id: toolArgs.session_id,
          language: toolArgs.language,
          has_edits: Array.isArray(toolArgs.edits) ? toolArgs.edits.length : 0,
          has_docx: typeof toolArgs.docx_base64 === 'string',
        });
      }
      const toolStartTime = Date.now();
      const toolOutput = await processToolCall(toolName, toolArgs);
      console.log(`  ✓ ${toolName} completed in ${Date.now() - toolStartTime}ms`);

      let effectiveToolOutput = toolOutput;

      // If PDF generation fails due to strict 2-page DoD, apply deterministic clamps once and retry.
      if (toolName === 'generate_cv_from_session') {
        try {
          const parsed = JSON.parse(toolOutput);
          const details = typeof parsed?.details === 'string' ? parsed.details : '';
          if (parsed?.error && details.includes('DoD violation') && typeof toolArgs?.session_id === 'string') {
            console.log('  🛠️ Auto-fix DoD overflow: applying clamps and retrying generation once');
            await autoFixForTwoPages(toolArgs.session_id, toolArgs.language || language);
            effectiveToolOutput = await processToolCall(toolName, toolArgs);
            const parsed2 = JSON.parse(effectiveToolOutput);
            const details2 = typeof parsed2?.details === 'string' ? parsed2.details : '';
            if (parsed2?.error && details2.includes('DoD violation')) {
              console.log('  🛠️ Auto-squeeze DoD overflow: applying aggressive clamps and retrying once');
              await autoSqueezeForTwoPages(toolArgs.session_id, toolArgs.language || language);
              effectiveToolOutput = await processToolCall(toolName, toolArgs);
            }
          }
        } catch {
          // ignore
        }
      }

      // Track session id for stateless frontend usage.
      if (toolName === 'extract_and_store_cv' || toolName === 'process_cv_orchestrated' || toolName === 'get_cv_session') {
        try {
          const parsed = JSON.parse(effectiveToolOutput);
          const sid = parsed?.session_id;
          if (typeof sid === 'string' && sid.length > 10) {
            currentSessionId = sid;
          }
        } catch {
          // ignore
        }
      }

      // Capture PDF if present.
      try {
        const parsed = JSON.parse(effectiveToolOutput);
        if ((toolName === 'generate_cv_from_session' || toolName === 'process_cv_orchestrated') && parsed?.pdf_base64) {
          pdfBase64 = parsed.pdf_base64;
          generateAttempted = true;
          console.log('  📄 PDF generated, length:', pdfBase64.length);
        }
      } catch {
        // ignore
      }

      const modelToolOutput = sanitizeToolOutputForModel(toolName, effectiveToolOutput);
      if (DEBUG_TOKENS) {
        console.log(
          `  📦 Tool output sizes: raw=${effectiveToolOutput.length} chars, model=${modelToolOutput.length} chars`
        );
      }

      inputList.push({
        type: 'function_call_output',
        call_id: toolCall.call_id,
        output: modelToolOutput,
      });

      const nextStage = stageFromTool(toolName, effectiveToolOutput);
      if (nextStage !== stage) {
        console.log(`  🧭 Stage: ${stage} -> ${nextStage}`);
        stageUpdates.push({ from: stage, to: nextStage, via: toolName });
        stage = nextStage;
      }
    }

    if (DEBUG_TOKENS) {
      console.log('📏 Input items:', inputList.length, 'rough chars:', roughInputChars(inputList));
    }
    stageSeq += 1;
    const iterationTools = toolsForStage
      .map((t: any) => {
        if (t.name === 'generate_cv_from_session' || t.name === 'process_cv_orchestrated') {
          const enabled = generateAllowedThisTurn && !generateAttempted;
          return { ...t, enabled };
        }
        return t;
      })
      .filter((t: any) => t.enabled !== false);
    response = await openai.responses.create(buildRequest(inputList, iterationTools));

    const usage = getResponseUsageSummary(response);
    if (usage) {
      console.log(`🧮 OpenAI usage (iter ${iteration}):`, usage);
    }
  }

  const finalText = (response as any).output_text || '';
  return {
    response: finalText || 'Processing completed',
    pdf_base64: pdfBase64,
    last_response_id: response?.id,
    session_id: currentSessionId,
    stage,
    stage_seq: stageSeq,
    stage_updates: stageUpdates,
    job_posting_url: url,
    job_posting_text: jobText,
  };
}

export async function POST(request: NextRequest) {
  const startTime = Date.now();
  try {
    const { message, docx_base64, session_id, job_posting_url, job_posting_text } = await request.json();

    console.log('\n=== Backend Process CV Request ===');
    console.log('Timestamp:', new Date().toISOString());
    console.log('Message:', message);
    console.log('Has docx_base64:', !!docx_base64);
    console.log('session_id:', session_id || 'none');
    if (docx_base64) {
      console.log('Base64 length:', docx_base64.length);
      console.log('Base64 first 50 chars:', docx_base64.substring(0, 50));
    }

    if (!message) {
      console.error('❌ No message provided');
      return NextResponse.json({ error: 'Message is required' }, { status: 400 });
    }

    console.log('⏳ Calling chatWithCV...');
    const result = await chatWithCV(message, docx_base64, session_id, job_posting_url, job_posting_text);
    
    const duration = Date.now() - startTime;
    console.log('\n=== Backend Response ===');
    console.log('Duration:', duration, 'ms');
    console.log('Response length:', result.response.length);
    console.log('Has PDF:', !!result.pdf_base64);
    console.log('session_id (returned):', result.session_id || 'none');
    if (result.pdf_base64) {
      console.log('PDF base64 length:', result.pdf_base64.length);
    }
    console.log('✅ Success\n');
    
    return NextResponse.json({
      success: true,
      response: result.response,
      pdf_base64: result.pdf_base64,
      last_response_id: result.last_response_id,
      session_id: result.session_id,
      stage: result.stage,
      stage_seq: result.stage_seq,
      stage_updates: result.stage_updates,
      job_posting_url: result.job_posting_url,
      job_posting_text: result.job_posting_text,
    });
  } catch (error) {
    const duration = Date.now() - startTime;
    const message = error instanceof Error ? error.message : String(error);
    console.error('\n=== Backend Error ===');
    console.error('Duration:', duration, 'ms');
    console.error('Error type:', error?.constructor?.name);
    console.error('Error message:', message);
    console.error('Error stack:', error instanceof Error ? error.stack : 'N/A');
    console.error('❌ Failed\n');

    // Common misconfiguration when using stored prompts:
    // prompt includes `reasoning.effort` but the model selected (e.g. gpt-4o) doesn't support it.
    if (
      message.includes("Unsupported parameter") &&
      message.includes("reasoning.effort")
    ) {
      return NextResponse.json(
        {
          success: false,
          error: message,
          hint:
            "Your stored prompt configuration includes `reasoning.effort`, but the selected model doesn't support it. Fix by either: (1) removing `reasoning.effort` in the dashboard Prompt, or (2) setting OPENAI_MODEL in ui/.env.local to a reasoning-capable model (e.g. o3-mini) so it matches the prompt settings.",
        },
        { status: 400 }
      );
    }
    
    return NextResponse.json(
      { 
        success: false,
        error: message,
        details: error instanceof Error ? error.stack : String(error)
      },
      { status: 500 }
    );
  }
}
