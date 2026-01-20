import { NextRequest, NextResponse } from 'next/server';
import OpenAI from 'openai';
import { CV_SYSTEM_PROMPT } from '@/lib/prompts';
import { CV_TOOLS_RESPONSES } from '@/lib/tools';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

function extractFirstUrl(text: string): string | null {
  const m = text.match(/https?:\/\/[^\s)\]]+/i);
  if (!m) return null;
  // Trim common trailing punctuation
  return m[0].replace(/[),.]+$/, '');
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
    throw new Error(`Azure Function error: ${response.statusText}`);
  }

  return response.json();
}

async function processToolCall(toolName: string, toolInput: any): Promise<string> {
  try {
    switch (toolName) {
      case 'extract_photo':
        const photoResult = await callAzureFunction('/extract-photo', {
          docx_base64: toolInput.docx_base64,
        });
        return JSON.stringify(photoResult);

      case 'validate_cv':
        const validateResult = await callAzureFunction('/validate-cv', toolInput);
        return JSON.stringify(validateResult);

      case 'generate_cv_action':
        const generateResult = await callAzureFunction('/generate-cv-action', {
          cv_data: toolInput,
          language: toolInput.language || 'pl',
          source_docx_base64: toolInput.source_docx_base64,
        });
        return JSON.stringify(generateResult);

      default:
        return JSON.stringify({ error: `Unknown tool: ${toolName}` });
    }
  } catch (error) {
    return JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' });
  }
}

async function chatWithCV(userMessage: string, docx_base64?: string) {
  console.log('\n🤖 Starting chatWithCV');

  const hasDocx = !!docx_base64;
  const url = extractFirstUrl(userMessage);
  const jobText = url ? await fetchJobPostingText(url) : null;

  const userContent = [
    userMessage,
    hasDocx
      ? "[CV DOCX is already uploaded in this chat. Do NOT ask the user to re-send it or paste base64. If you need file bytes, call tools; backend will inject docx_base64 for you.]"
      : null,
    jobText
      ? `\n\n[Job posting text extracted from ${url} (may be partial):]\n${jobText}`
      : null,
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
        'The user already uploaded a CV document. Never ask them to paste base64 or re-upload. If you need the file bytes, call the tools and the backend will provide docx_base64 to the tool inputs.',
    });
  }

  inputList.push({
    role: 'user',
    content: userContent,
  });

  console.log('📤 Calling OpenAI Responses API...');
  const apiStartTime = Date.now();

  const buildRequest = (input: any[]) => {
    // IMPORTANT:
    // - If using a stored prompt, let the prompt define model/params unless OPENAI_MODEL overrides.
    // - This avoids mismatches like a prompt that sets `reasoning.effort` while code forces `gpt-4o`.
    const req: any = {
      ...(promptId ? { prompt: { id: promptId } } : { instructions: CV_SYSTEM_PROMPT }),
      input,
      tools: CV_TOOLS_RESPONSES,
      store: true,
      metadata: {
        app: 'cv-generator-ui',
        prompt_id: promptId || 'none',
      },
    };

    if (modelOverride) {
      req.model = modelOverride;
    } else if (!promptId) {
      req.model = 'gpt-4o';
    }

    return req;
  };

  let response = await openai.responses.create(buildRequest(inputList));

  console.log('✅ OpenAI response received in', Date.now() - apiStartTime, 'ms');

  let pdfBase64 = '';
  let iteration = 0;
  const maxIterations = 10;

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
      if (toolName === 'extract_photo') {
        toolArgs.docx_base64 = toolArgs.docx_base64 || docx_base64;
      }
      if (toolName === 'generate_cv_action') {
        toolArgs.source_docx_base64 = toolArgs.source_docx_base64 || docx_base64;
      }

      console.log(`  → Calling tool: ${toolName}`);
      const toolStartTime = Date.now();
      const toolOutput = await processToolCall(toolName, toolArgs);
      console.log(`  ✓ ${toolName} completed in ${Date.now() - toolStartTime}ms`);

      // Capture PDF if present.
      try {
        const parsed = JSON.parse(toolOutput);
        if (toolName === 'generate_cv_action' && parsed?.pdf_base64) {
          pdfBase64 = parsed.pdf_base64;
          console.log('  📄 PDF generated, length:', pdfBase64.length);
        }
      } catch {
        // ignore
      }

      inputList.push({
        type: 'function_call_output',
        call_id: toolCall.call_id,
        output: toolOutput,
      });
    }

    response = await openai.responses.create(buildRequest(inputList));
  }

  const finalText = (response as any).output_text || '';
  return {
    response: finalText || 'Processing completed',
    pdf_base64: pdfBase64,
  };
}

export async function POST(request: NextRequest) {
  const startTime = Date.now();
  try {
    const { message, docx_base64 } = await request.json();

    console.log('\n=== Backend Process CV Request ===');
    console.log('Timestamp:', new Date().toISOString());
    console.log('Message:', message);
    console.log('Has docx_base64:', !!docx_base64);
    if (docx_base64) {
      console.log('Base64 length:', docx_base64.length);
      console.log('Base64 first 50 chars:', docx_base64.substring(0, 50));
    }

    if (!message) {
      console.error('❌ No message provided');
      return NextResponse.json({ error: 'Message is required' }, { status: 400 });
    }

    console.log('⏳ Calling chatWithCV...');
    const result = await chatWithCV(message, docx_base64);
    
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
