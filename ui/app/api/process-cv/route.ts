import { NextRequest, NextResponse } from 'next/server';
import OpenAI from 'openai';
import mammoth from 'mammoth';
import { CV_SYSTEM_PROMPT } from '@/lib/prompts';
import { CV_TOOLS_RESPONSES } from '@/lib/tools';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const DEBUG_TOKENS = process.env.CV_DEBUG_TOKENS === '1';

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

function roughInputChars(input: any[]): number {
  // Approximate size of the input we send to OpenAI.
  // Avoid JSON.stringify of big objects; focus on known large string fields.
  let total = 0;
  for (const item of input || []) {
    if (!item) continue;
    if (typeof item.content === 'string') total += item.content.length;
    if (Array.isArray(item.content)) {
      for (const c of item.content) {
        if (typeof c?.text === 'string') total += c.text.length;
      }
    }
    if (typeof item.output === 'string') total += item.output.length;
    if (typeof item.arguments === 'string') total += item.arguments.length;
  }
  return total;
}

function sanitizeToolOutputForModel(toolName: string, toolOutput: string): string {
  // The model does not need base64 blobs (photo/pdf) which can bloat context.
  // Return a compact summary to keep the next call small.

  const maxLen = 4000;
  const clamp = (s: string) => (s.length <= maxLen ? s : `${s.slice(0, maxLen)}\n...[truncated ${s.length - maxLen} chars]`);

  let parsed: any = null;
  try {
    parsed = JSON.parse(toolOutput);
  } catch {
    return clamp(toolOutput);
  }

  if (!parsed || typeof parsed !== 'object') {
    return clamp(toolOutput);
  }

  if (toolName === 'extract_and_store_cv') {
    const sessionId = typeof parsed.session_id === 'string' ? parsed.session_id : undefined;
    const hasPhoto = parsed.photo_extracted === true;
    const summary = parsed.cv_data_summary;
    return JSON.stringify({
      ok: parsed.success !== false,
      session_id: sessionId,
      fields_populated: summary?.fields_populated?.length ?? undefined,
      fields_empty: summary?.fields_empty?.length ?? undefined,
      photo_extracted: hasPhoto,
      error: parsed.error,
    });
  }

  if (toolName === 'generate_cv_from_session' || toolName === 'process_cv_orchestrated') {
    const pdfLen = typeof parsed.pdf_base64 === 'string' ? parsed.pdf_base64.length : 0;
    return JSON.stringify({
      ok: parsed.success !== false && pdfLen > 0,
      success: parsed.success,
      pdf_generated: pdfLen > 0,
      pdf_base64_length: pdfLen || undefined,
      validation: parsed.validation,
      errors: parsed.validation_errors || parsed.error,
      session_id: parsed.session_id,
    });
  }

  // Generic sanitizer: drop known huge fields and clamp long strings.
  const out: Record<string, any> = { ...parsed };
  for (const key of ['photo_data_uri', 'pdf_base64', 'docx_base64', 'source_docx_base64']) {
    if (key in out) delete out[key];
  }

  for (const [k, v] of Object.entries(out)) {
    if (typeof v === 'string' && v.length > 1500) {
      out[k] = `${v.slice(0, 1500)}...[truncated ${v.length - 1500} chars]`;
    }
  }

  return clamp(JSON.stringify(out));
}

function extractFirstUrl(text: string): string | null {
  const m = text.match(/https?:\/\/[^\s)\]]+/i);
  if (!m) return null;
  // Trim common trailing punctuation
  return m[0].replace(/[),.]+$/, '');
}

function wantsSkipPhoto(text: string): boolean {
  return /\b(skip photo|omit photo|without photo|no photo|bez zdj[eę]cia|pomi[nń] zdj[eę]cie)\b/i.test(
    text
  );
}

function detectLanguage(text: string): 'pl' | 'en' | 'de' {
  if (/\b(de|deutsch|german)\b/i.test(text)) return 'de';
  if (/\b(en|eng|english)\b/i.test(text)) return 'en';
  if (/\b(pl|polski|polish)\b/i.test(text)) return 'pl';
  return 'en';
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
        Accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
      },
    });

    clearTimeout(timeout);
    if (!resp.ok) return null;

    const html = await resp.text();
    const withoutScripts = html
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ');

    const text = withoutScripts
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    if (!text) return null;
    // Keep it bounded to avoid token bloat.
    return text.slice(0, 6000);
  } catch {
    return null;
  }
}

async function callAzureFunction(endpoint: string, body: any) {
  const url = `${process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_URL}${endpoint}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'x-functions-key': process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_KEY || '',
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
    throw new Error(
      `Azure Function error: ${response.status} ${response.statusText}${snippet ? ` - ${snippet}` : ''}`
    );
  }

  return response.json();
}

async function processToolCall(toolName: string, toolInput: any): Promise<string> {
  try {
    switch (toolName) {
      case 'extract_and_store_cv': {
        const result = await callAzureFunction('/extract-and-store-cv', {
          docx_base64: toolInput.docx_base64,
          language: toolInput.language,
          extract_photo: toolInput.extract_photo,
        });
        return JSON.stringify(result);
      }

      case 'get_cv_session': {
        const result = await callAzureFunction('/get-cv-session', {
          session_id: toolInput.session_id,
        });
        return JSON.stringify(result);
      }

      case 'update_cv_field': {
        const result = await callAzureFunction('/update-cv-field', {
          session_id: toolInput.session_id,
          field_path: toolInput.field_path,
          value: toolInput.value,
        });
        return JSON.stringify(result);
      }

      case 'generate_cv_from_session': {
        const result = await callAzureFunction('/generate-cv-from-session', {
          session_id: toolInput.session_id,
          language: toolInput.language,
        });
        return JSON.stringify(result);
      }

      case 'process_cv_orchestrated': {
        const result = await callAzureFunction('/process-cv-orchestrated', {
          session_id: toolInput.session_id,
          docx_base64: toolInput.docx_base64,
          language: toolInput.language,
          edits: toolInput.edits,
          extract_photo: toolInput.extract_photo,
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

async function chatWithCV(
  userMessage: string,
  docx_base64?: string,
  previousResponseId?: string
) {
  console.log('\n🤖 Starting chatWithCV');

  const hasDocx = !!docx_base64;
  const skipPhoto = wantsSkipPhoto(userMessage);
  const language = detectLanguage(userMessage);
  const isContinuation = !!previousResponseId;
  const url = extractFirstUrl(userMessage);
  const jobText = url ? await fetchJobPostingText(url) : null;

  // If we are continuing via previous_response_id, do NOT re-send the full CV text.
  // It should already be in the model context via the previous response chain.
  const cvText =
    !isContinuation && hasDocx && docx_base64 ? await extractDocxTextFromBase64(docx_base64) : null;
  const boundedCvText = cvText ? cvText.slice(0, 12000) : null;
  if (hasDocx) {
    console.log('📄 Extracted DOCX text:', boundedCvText ? `${boundedCvText.length} chars (bounded)` : 'none');
  }

  // If feature flag enabled, ask backend to build a compact ContextPackV1
  let contextPack: any = null;
  const USE_CONTEXT_PACK = process.env.CV_USE_CONTEXT_PACK === '1';
  if (USE_CONTEXT_PACK && hasDocx && boundedCvText) {
    try {
      console.log('🧩 CV_USE_CONTEXT_PACK enabled — requesting context pack from backend');
      // Send minimal cv_data with extracted text as `profile` as a starting point.
      const packResp = await callAzureFunction('/generate-context-pack', {
        cv_data: { profile: boundedCvText },
        job_posting_text: jobText,
      });
      contextPack = packResp;
      console.log('🧩 Context pack received; keys:', Object.keys(contextPack || {}));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.warn('⚠️ Failed to build context pack; falling back to injected CV text', msg);
      contextPack = null;
    }
  }

  const userContent = [
    userMessage,
    hasDocx
      ? "[CV DOCX is already uploaded in this chat. Do NOT ask the user to re-send it or paste base64. If you need file bytes, call tools; backend will inject docx_base64 for you.]"
      : null,
    skipPhoto ? '[User requested: omit photo in the final CV. Do not extract photo.]' : null,
    // Prefer context pack when available; otherwise include bounded CV text as before.
    contextPack
      ? `\n\n[CONTEXT_PACK_JSON]\n${JSON.stringify(contextPack)}`
      : boundedCvText
      ? `\n\n[CV text extracted from uploaded DOCX (may be partial):]\n${boundedCvText}`
      : null,
    // If we are continuing and the user repeats the same URL, this can duplicate content.
    // Keep it only when a URL is present in the current user message.
    url && jobText
      ? `\n\n[Job posting text extracted from ${url} (may be partial):]\n${jobText}`
      : null,
    `\n\n[Output language: ${language}.]`,
  ]
    .filter(Boolean)
    .join('\n\n');

  const promptId = process.env.OPENAI_PROMPT_ID;
  const modelOverride = process.env.OPENAI_MODEL;

  const inputList: any[] = [];

  if (hasDocx) {
    inputList.push({
      role: 'system',
      content:
        'The user already uploaded a CV document. Never ask them to paste base64 or re-upload. If you need the file bytes, call the session tools (extract_and_store_cv or process_cv_orchestrated) and the backend will inject docx_base64 for you.',
    });
  }

  // Ensure each request is self-contained (Responses API is stateless across HTTP requests).
  inputList.push({
    role: 'system',
    content:
      'Use session-based workflow only: extract_and_store_cv → get_cv_session → update_cv_field → generate_cv_from_session (or process_cv_orchestrated when all data is present). Do NOT call legacy tools. Always reuse session_id, ask for missing required fields (full_name, email, phone, work_experience, education), then generate.',
  });

  inputList.push({
    role: 'user',
    content: userContent,
  });

  console.log('📤 Calling OpenAI Responses API...');
  const apiStartTime = Date.now();

  const buildRequest = (input: any[], opts?: { usePrevious?: boolean }) => {
    // IMPORTANT:
    // - If using a stored prompt, let the prompt define model/params unless OPENAI_MODEL overrides.
    // - This avoids mismatches like a prompt that sets `reasoning.effort` while code forces `gpt-4o`.
    const req: any = {
      ...(promptId ? { prompt: { id: promptId } } : { instructions: CV_SYSTEM_PROMPT }),
      input,
      tools: CV_TOOLS_RESPONSES,
      store: true,
      truncation: opts?.usePrevious ? 'auto' : 'disabled',
      metadata: {
        app: 'cv-generator-ui',
        prompt_id: promptId || 'none',
      },
    };

    if (opts?.usePrevious && previousResponseId) {
      req.previous_response_id = previousResponseId;
    }

    if (modelOverride) {
      req.model = modelOverride;
    } else if (!promptId) {
      req.model = 'gpt-4o';
    }

    return req;
  };

  if (DEBUG_TOKENS) {
    console.log('📏 Input items:', inputList.length, 'rough chars:', roughInputChars(inputList));
  }
  let response = await openai.responses.create(
    buildRequest(inputList, { usePrevious: !!previousResponseId })
  );

  const firstUsage = getResponseUsageSummary(response);
  if (firstUsage) {
    console.log('🧮 OpenAI usage (initial):', firstUsage);
  }

  console.log('✅ OpenAI response received in', Date.now() - apiStartTime, 'ms');

  let pdfBase64 = '';
  let iteration = 0;
  const maxIterations = 10;
  let extractToolCalls = 0;

  while (iteration < maxIterations) {
    iteration++;
    console.log(`🔄 Iteration ${iteration}/${maxIterations}`);

    const toolCalls = ((response.output || []) as any[]).filter(
      (item) => item?.type === 'function_call'
    ) as any[];
    console.log('🔧 Tool calls:', toolCalls.length);

    if (toolCalls.length === 0) {
      const text = (response as any).output_text || '';
      console.log('✅ No more tool calls, finishing');
      return {
        response: text || 'Processing completed',
        pdf_base64: pdfBase64,
        last_response_id: response?.id,
      };
    }

    // Per docs, feed model output items back as part of the next input turn.
    inputList.push(...response.output);

    for (const toolCall of toolCalls) {
      const toolName: string = toolCall.name;
      let toolArgs: any = {};

      try {
        toolArgs = toolCall.arguments ? JSON.parse(toolCall.arguments) : {};
      } catch {
        toolArgs = {};
      }

      // Inject DOCX base64 if the model omitted it.
      if (toolName === 'extract_and_store_cv') {
        extractToolCalls += 1;
        toolArgs.docx_base64 = toolArgs.docx_base64 || docx_base64;
        toolArgs.language = toolArgs.language || language;
        if (skipPhoto) {
          toolArgs.extract_photo = false;
        }
      }

      if (toolName === 'process_cv_orchestrated') {
        toolArgs.docx_base64 = toolArgs.docx_base64 || docx_base64;
        toolArgs.language = toolArgs.language || language;
        if (skipPhoto) {
          toolArgs.extract_photo = false;
        }
      }

      if (toolName === 'generate_cv_from_session') {
        toolArgs.language = toolArgs.language || language;
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

      // Capture PDF if present.
      try {
        const parsed = JSON.parse(toolOutput);
        if ((toolName === 'generate_cv_from_session' || toolName === 'process_cv_orchestrated') && parsed?.pdf_base64) {
          pdfBase64 = parsed.pdf_base64;
          console.log('  📄 PDF generated, length:', pdfBase64.length);
        }
      } catch {
        // ignore
      }

      const modelToolOutput = sanitizeToolOutputForModel(toolName, toolOutput);
      if (DEBUG_TOKENS) {
        console.log(
          `  📦 Tool output sizes: raw=${toolOutput.length} chars, model=${modelToolOutput.length} chars`
        );
      }

      inputList.push({
        type: 'function_call_output',
        call_id: toolCall.call_id,
        output: modelToolOutput,
      });
    }

    if (DEBUG_TOKENS) {
      console.log('📏 Input items:', inputList.length, 'rough chars:', roughInputChars(inputList));
    }
    response = await openai.responses.create(buildRequest(inputList));

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
  };
}

export async function POST(request: NextRequest) {
  const startTime = Date.now();
  try {
    const { message, docx_base64, previous_response_id } = await request.json();

    console.log('\n=== Backend Process CV Request ===');
    console.log('Timestamp:', new Date().toISOString());
    console.log('Message:', message);
    console.log('Has docx_base64:', !!docx_base64);
    console.log('previous_response_id:', previous_response_id || 'none');
    if (docx_base64) {
      console.log('Base64 length:', docx_base64.length);
      console.log('Base64 first 50 chars:', docx_base64.substring(0, 50));
    }

    if (!message) {
      console.error('❌ No message provided');
      return NextResponse.json({ error: 'Message is required' }, { status: 400 });
    }

    console.log('⏳ Calling chatWithCV...');
    const result = await chatWithCV(message, docx_base64, previous_response_id);
    
    const duration = Date.now() - startTime;
    console.log('\n=== Backend Response ===');
    console.log('Duration:', duration, 'ms');
    console.log('Response length:', result.response.length);
    console.log('Has PDF:', !!result.pdf_base64);
    if (result.pdf_base64) {
      console.log('PDF base64 length:', result.pdf_base64.length);
    }
    console.log('✅ Success\n');
    
    return NextResponse.json({
      success: true,
      response: result.response,
      pdf_base64: result.pdf_base64,
      last_response_id: result.last_response_id,
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
