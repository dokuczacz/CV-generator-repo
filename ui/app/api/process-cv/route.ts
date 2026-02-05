import { NextRequest, NextResponse } from 'next/server';

const AZURE_FUNCTIONS_BASE_URL = process.env.AZURE_FUNCTIONS_BASE_URL || 'http://127.0.0.1:7071/api';

async function callAzureFunction(path: string, body: any): Promise<{ status: number; payload: any }> {
  const url = `${AZURE_FUNCTIONS_BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const contentType = (response.headers.get('content-type') || '').toLowerCase();
  const text = await response.text();

  let payload: any = { raw: text };
  if (contentType.includes('application/json')) {
    try {
      payload = JSON.parse(text || '{}');
    } catch {
      payload = { success: false, error: 'Invalid JSON from Azure Function', raw: text.slice(0, 1200) };
    }
  }

  if (!response.ok) {
    const snippet = text ? text.slice(0, 1200) : '';
    console.error(
      `❌ Azure Function call failed: ${url} status=${response.status} ${response.statusText} ` +
        (snippet ? `body=${snippet}` : '')
    );
  }

  return { status: response.status, payload };
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const hasDocx = typeof body?.docx_base64 === 'string' && !!body.docx_base64.trim();
    const rawMessage = typeof body?.message === 'string' ? body.message : '';

    const userAction = typeof body?.user_action === 'object' && body?.user_action ? body.user_action : undefined;
    const userActionId = typeof userAction?.id === 'string' ? userAction.id : '';
    if (!rawMessage.trim() && !userActionId.trim() && !hasDocx) {
      return NextResponse.json({ success: false, error: 'message is required (or provide user_action or docx_base64)' }, { status: 400 });
    }
    const message = rawMessage.trim() ? rawMessage : 'start';

    const { status, payload } = await callAzureFunction('/cv-tool-call-handler', {
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
        user_action: userAction,
      },
    });

    return NextResponse.json(
      {
        success: !!payload?.success,
        response: payload?.assistant_text || '',
        pdf_base64: payload?.pdf_base64 || '',
        filename: payload?.filename || payload?.pdf_metadata?.download_name || '',
        session_id: payload?.session_id || null,
        trace_id: payload?.trace_id || null,
        stage: payload?.stage || null,
        stage_updates: payload?.stage_updates || [],
        run_summary: payload?.run_summary || null,
        turn_trace: payload?.turn_trace || null,
        ui_action: payload?.ui_action || null,
        job_posting_url: payload?.job_posting_url || '',
        job_posting_text: payload?.job_posting_text || '',
      },
      { status: status || 200 }
    );
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ success: false, error: msg }, { status: 500 });
  }
}
