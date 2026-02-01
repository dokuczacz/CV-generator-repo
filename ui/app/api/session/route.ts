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

  return { status: response.status, payload };
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const sessionId = typeof body?.session_id === 'string' ? body.session_id.trim() : '';
    if (!sessionId) {
      return NextResponse.json({ success: false, error: 'session_id is required' }, { status: 400 });
    }

    const { status, payload } = await callAzureFunction('/cv-tool-call-handler', {
      tool_name: 'get_cv_session',
      session_id: sessionId,
      params: {},
    });

    return NextResponse.json(
      {
        success: !!payload?.success,
        session_id: sessionId,
        cv_data: payload?.cv_data || null,
        metadata: payload?.metadata || null,
        readiness: payload?.readiness || null,
        trace_id: payload?.trace_id || null,
        error: payload?.error || null,
      },
      { status: status || 200 }
    );
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ success: false, error: msg }, { status: 500 });
  }
}

