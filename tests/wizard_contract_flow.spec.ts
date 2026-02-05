import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

type ProcessCvResponse = {
  success: boolean;
  session_id?: string | null;
  stage?: string | null;
  response?: string | null;
};

async function processCv(request: any, body: any): Promise<ProcessCvResponse> {
  const resp = await request.post('http://127.0.0.1:3000/api/process-cv', { data: body });
  expect(resp.ok()).toBeTruthy();
  return (await resp.json()) as ProcessCvResponse;
}

test.describe('Wizard contract flow (no browser)', () => {
  test('lock role index 0 works; work_tailoring_notes persists from Skills step payload', async ({ request }) => {
    test.setTimeout(120_000);

    const docxPath = path.resolve(process.cwd(), 'samples', 'Lebenslauf_Mariusz_Horodecki_CH.docx');
    const docxBase64 = fs.readFileSync(docxPath).toString('base64');

    // Start session with upload
    const start = await processCv(request, {
      message: 'start',
      docx_base64: docxBase64,
      language: 'en',
      extract_photo: false,
      client_context: { fast_path_profile: false },
    });
    expect(start.success).toBeTruthy();
    expect(start.session_id).toBeTruthy();
    const sessionId = String(start.session_id);

    // Language selection -> should advance (import gate or contact)
    const lang = await processCv(request, {
      session_id: sessionId,
      user_action: { id: 'LANGUAGE_SELECT_EN' },
    });
    expect(lang.success).toBeTruthy();

    // If import gate, accept it (some scenarios might not need it)
    const maybeImport = await processCv(request, {
      session_id: sessionId,
      user_action: { id: 'CONFIRM_IMPORT_PREFILL_YES' },
    }).catch(() => null);
    if (maybeImport && maybeImport.success) {
      // ok
    }

    // Lock role index 0 (should not be treated as falsy)
    const lock = await processCv(request, {
      session_id: sessionId,
      user_action: { id: 'WORK_TOGGLE_LOCK', payload: { role_index: 0 } },
    });
    expect(lock.success).toBeTruthy();
    expect(String(lock.response || '')).toMatch(/locked|unlocked/i);

    // Move to Skills step (skip job/work/further; these actions are allowed and should advance deterministically)
    await processCv(request, { session_id: sessionId, user_action: { id: 'JOB_OFFER_SKIP' } }).catch(() => null);
    await processCv(request, { session_id: sessionId, user_action: { id: 'WORK_TAILOR_SKIP' } }).catch(() => null);
    await processCv(request, { session_id: sessionId, user_action: { id: 'FURTHER_TAILOR_SKIP' } }).catch(() => null);

    // Persist work_tailoring_notes via Skills step payload (works even on "Continue")
    const notesText = 'Focus: delivery ownership, Azure Functions, orchestration, deterministic outputs.';
    const skillsSkip = await processCv(request, {
      session_id: sessionId,
      user_action: { id: 'SKILLS_TAILOR_SKIP', payload: { work_tailoring_notes: notesText } },
    });
    expect(skillsSkip.success).toBeTruthy();

    const sess = await request.post('http://127.0.0.1:3000/api/session', { data: { session_id: sessionId } });
    expect(sess.ok()).toBeTruthy();
    const sessJson = await sess.json();
    expect(sessJson?.success).toBeTruthy();
    expect(String(sessJson?.metadata?.work_tailoring_notes || '')).toContain('delivery ownership');
  });
});

