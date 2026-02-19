import { test, expect, type Page, type Route } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

type ProcessCvReq = {
  message?: string;
  session_id?: string | null;
  docx_base64?: string;
  user_action?: { id?: string; payload?: Record<string, unknown> };
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function setupDeterministicApiMock(page: Page) {
  const requests: ProcessCvReq[] = [];
  const sessionId = 'sess-new-version-001';

  await page.route('**/api/process-cv', async (route) => {
    const raw = route.request().postData() || '{}';
    let req: ProcessCvReq = {};
    try {
      req = JSON.parse(raw);
    } catch {
      await fulfillJson(route, { success: false, error: 'invalid_json' }, 400);
      return;
    }

    requests.push(req);

    if (!req.session_id) {
      await fulfillJson(route, {
        success: true,
        session_id: sessionId,
        response: 'Session started.',
        ui_action: {
          kind: 'review_form',
          stage: 'JOB_POSTING',
          title: 'Stage 3/6 — Job offer',
          text: 'Provide job posting or continue.',
          fields: [],
          actions: [
            { id: 'JOB_OFFER_SKIP', label: 'Skip', style: 'secondary' },
            { id: 'REQUEST_GENERATE_PDF', label: 'Generate PDF', style: 'primary' },
          ],
          disable_free_text: true,
        },
      });
      return;
    }

    const actionId = req.user_action?.id || '';
    if (actionId === 'NEW_VERSION_RESET') {
      await fulfillJson(route, {
        success: true,
        session_id: sessionId,
        response: 'New version ready. Translation cache and CV data are kept; tailoring artifacts were reset.',
        ui_action: {
          kind: 'review_form',
          stage: 'JOB_POSTING',
          title: 'Stage 3/6 — Job offer',
          text: 'Provide job posting or continue.',
          fields: [],
          actions: [
            { id: 'JOB_OFFER_SKIP', label: 'Skip', style: 'secondary' },
            { id: 'REQUEST_GENERATE_PDF', label: 'Generate PDF', style: 'primary' },
          ],
          disable_free_text: true,
        },
      });
      return;
    }

    await fulfillJson(route, {
      success: true,
      session_id: sessionId,
      response: 'OK',
      ui_action: {
        kind: 'review_form',
        stage: 'JOB_POSTING',
        title: 'Stage 3/6 — Job offer',
        text: 'Provide job posting or continue.',
        fields: [],
        actions: [{ id: 'JOB_OFFER_SKIP', label: 'Skip', style: 'secondary' }],
        disable_free_text: true,
      },
    });
  });

  await page.route('**/api/session', async (route) => {
    await fulfillJson(route, {
      success: true,
      cv_data: {
        full_name: 'Mariusz Horodecki',
        work_experience: [],
        it_ai_skills: [],
      },
      metadata: {
        target_language: 'en',
        active_cv_state: 'translated',
        active_cv_state_lang: 'en',
        bulk_translation_cache: { en: { summary: 'cached' } },
        pdf_generated: false,
      },
      readiness: {},
    });
  });

  return { requests, sessionId };
}

test.describe('Wizard new version reset', () => {
  test('keeps same session and uses NEW_VERSION_RESET action without re-upload', async ({ page }) => {
    test.setTimeout(120_000);

    const api = await setupDeterministicApiMock(page);
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    await page.getByTestId('use-loaded-cv').click();

    await expect(page.getByTestId('stage-panel')).toBeVisible({ timeout: 30_000 });

    const reqPromise = page.waitForRequest(
      (r) =>
        r.url().includes('/api/process-cv') &&
        r.method() === 'POST' &&
        String(r.postData() || '').includes('NEW_VERSION_RESET'),
      { timeout: 30_000 }
    );

    await page.getByRole('button', { name: 'Nowa wersja' }).click();

    const req = await reqPromise;
    const actionPayload = JSON.parse(req.postData() || '{}') as ProcessCvReq;

    expect(actionPayload.session_id).toBe(api.sessionId);
    expect(actionPayload.user_action?.id).toBe('NEW_VERSION_RESET');
    expect(actionPayload.docx_base64).toBeUndefined();

    const actionRequests = api.requests.filter((r) => r.user_action?.id === 'NEW_VERSION_RESET');
    expect(actionRequests).toHaveLength(1);

    await expect(page.getByTestId('stage-panel')).toBeVisible();
    await expect(page.getByTestId('cv-upload-dropzone')).toHaveCount(0);
  });
});
