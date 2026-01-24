import { NextRequest, NextResponse } from 'next/server';

const AZURE_FUNCTIONS_BASE_URL = process.env.AZURE_FUNCTIONS_BASE_URL || 'http://127.0.0.1:7071/api';

async function callAzureFunction(path: string, body: any): Promise<any> {
  const url = `${AZURE_FUNCTIONS_BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const contentType = (response.headers.get('content-type') || '').toLowerCase();
  const text = await response.text();

  if (!response.ok) {
    const snippet = text ? text.slice(0, 1200) : '';
    console.error(
      `❌ Azure Function call failed: ${url} status=${response.status} ${response.statusText} ` +
        (snippet ? `body=${snippet}` : '')
    );
    throw new Error(
      `Azure Function error: ${response.status} ${response.statusText}${snippet ? ` - ${snippet}` : ''}`
    );
  }

  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(text || '{}');
    } catch {
      return { success: false, error: 'Invalid JSON from Azure Function', raw: text.slice(0, 1200) };
    }
  }

  return { success: true, raw: text };
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const message = typeof body?.message === 'string' ? body.message : '';
    if (!message.trim()) {
      return NextResponse.json({ success: false, error: 'message is required' }, { status: 400 });
    }

    const payload = await callAzureFunction('/cv-tool-call-handler', {
      tool_name: 'process_cv_orchestrated',
      params: {
        message,
        session_id: typeof body?.session_id === 'string' ? body.session_id : '',
        docx_base64: typeof body?.docx_base64 === 'string' ? body.docx_base64 : '',
        job_posting_url: typeof body?.job_posting_url === 'string' ? body.job_posting_url : '',
        job_posting_text: typeof body?.job_posting_text === 'string' ? body.job_posting_text : '',
        language: typeof body?.language === 'string' ? body.language : 'en',
        extract_photo: body?.extract_photo !== false,
        client_context: typeof body?.client_context === 'object' ? body.client_context : undefined,
      },
    });

    return NextResponse.json(
      {
        success: !!payload?.success,
        response: payload?.assistant_text || '',
        pdf_base64: payload?.pdf_base64 || '',
        session_id: payload?.session_id || null,
        trace_id: payload?.trace_id || null,
        stage: payload?.stage || null,
        run_summary: payload?.run_summary || null,
        turn_trace: payload?.turn_trace || null,
      },
      { status: 200 }
    );
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ success: false, error: msg }, { status: 500 });
  }
}

