import { test, expect, APIRequestContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const FUNCTIONS_BASE_URL = process.env.CV_FUNCTIONS_BASE_URL || 'http://localhost:7071/api';
const SAMPLE_DOCX_PATH = path.resolve(__dirname, '..', 'samples', 'Lebenslauf_Mariusz_Horodecki_CH.docx');

async function requireFunctionsUp(request: APIRequestContext) {
  try {
    const res = await request.get(`${FUNCTIONS_BASE_URL}/health`);
    if (!res.ok()) {
      test.skip(true, `Functions health failed (${res.status()})`);
    }
  } catch {
    test.skip(true, 'Functions server not reachable (start: func start)');
  }
}

test.describe('DOCX Prefill E2E (Functions)', () => {
  let request: APIRequestContext;

  test.beforeAll(async ({ playwright }) => {
    request = await playwright.request.newContext();
  });

  test.afterAll(async () => {
    await request.dispose();
  });

  test('extract_and_store_cv stores docx_prefill_unconfirmed with skills + further_experience', async () => {
    await requireFunctionsUp(request);

    expect(fs.existsSync(SAMPLE_DOCX_PATH)).toBeTruthy();
    const docxBase64 = fs.readFileSync(SAMPLE_DOCX_PATH).toString('base64');

    const createRes = await request.post(`${FUNCTIONS_BASE_URL}/cv-tool-call-handler`, {
      data: {
        tool_name: 'extract_and_store_cv',
        session_id: '',
        params: {
          docx_base64: docxBase64,
          language: 'de',
          extract_photo: false,
        },
      },
    });

    expect(createRes.ok()).toBeTruthy();
    const created = await createRes.json();
    expect(created).toHaveProperty('session_id');
    const sessionId = created.session_id as string;
    expect(sessionId).toMatch(/^[a-f0-9-]+$/);

    const getRes = await request.post(`${FUNCTIONS_BASE_URL}/cv-tool-call-handler`, {
      data: {
        tool_name: 'get_cv_session',
        session_id: sessionId,
        params: {},
      },
    });

    expect(getRes.ok()).toBeTruthy();
    const session = await getRes.json();

    expect(session).toHaveProperty('metadata');
    const meta = session.metadata as any;

    expect(meta).toHaveProperty('docx_prefill_unconfirmed');
    const dpu = meta.docx_prefill_unconfirmed as any;
    expect(dpu && typeof dpu === 'object').toBeTruthy();

    // Skills: ensure we captured the German "FÄHIGKEITEN & KOMPETENZEN"-style list.
    expect(Array.isArray(dpu.it_ai_skills)).toBeTruthy();
    expect(dpu.it_ai_skills.length).toBeGreaterThanOrEqual(3);
    expect((dpu.it_ai_skills as string[]).some((s) => s.includes('Technisches Projektmanagement'))).toBeTruthy();

    // Further experience / trainings: ensure at least one known training made it through.
    expect(Array.isArray(dpu.further_experience)).toBeTruthy();
    expect(dpu.further_experience.length).toBeGreaterThanOrEqual(2);
    expect(
      (dpu.further_experience as any[]).some((x) => typeof x?.title === 'string' && x.title.includes('Core Tools'))
    ).toBeTruthy();

    // Sanity-check summary aligns with extracted lists.
    expect(meta).toHaveProperty('prefill_summary');
    expect(meta.prefill_summary.it_ai_skills_count).toBe(dpu.it_ai_skills.length);
    expect(meta.prefill_summary.education_count).toBeGreaterThanOrEqual(1);
    expect(meta.prefill_summary.work_experience_count).toBeGreaterThanOrEqual(1);

    // Confirm flags should NOT clear docx_prefill_unconfirmed (needed for later stages 5a/5b).
    const confirmRes = await request.post(`${FUNCTIONS_BASE_URL}/cv-tool-call-handler`, {
      data: {
        tool_name: 'update_cv_field',
        session_id: sessionId,
        params: {
          confirm: {
            contact_confirmed: true,
            education_confirmed: true,
          },
        },
      },
    });
    expect(confirmRes.ok()).toBeTruthy();

    const getRes2 = await request.post(`${FUNCTIONS_BASE_URL}/cv-tool-call-handler`, {
      data: {
        tool_name: 'get_cv_session',
        session_id: sessionId,
        params: {},
      },
    });
    expect(getRes2.ok()).toBeTruthy();
    const session2 = await getRes2.json();
    const meta2 = session2.metadata as any;
    expect(meta2).toHaveProperty('docx_prefill_unconfirmed');
    expect(meta2.docx_prefill_unconfirmed && typeof meta2.docx_prefill_unconfirmed === 'object').toBeTruthy();
    expect(Array.isArray(meta2.docx_prefill_unconfirmed.it_ai_skills)).toBeTruthy();
    expect(Array.isArray(meta2.docx_prefill_unconfirmed.further_experience)).toBeTruthy();
  });
});
