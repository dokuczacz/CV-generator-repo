import { expect, test, type Page, type Route } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

type ProcessReq = {
  message?: string;
  session_id?: string | null;
  user_action?: { id?: string; payload?: Record<string, unknown> };
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function setupMock(page: Page) {
  const sessionId = 'sess-cover-001';
  const seen: ProcessReq[] = [];

  await page.route('**/api/session', async (route) => {
    await fulfillJson(route, {
      success: true,
      session_id: sessionId,
      cv_data: {
        full_name: 'Mariusz Horodecki',
        email: 'm@example.com',
        phone: '+41 77 000 0000',
        work_experience: [
          {
            title: 'Operations Manager',
            employer: 'Lonza',
            date_range: '2021-01 - 2025-01',
            bullets: ['Reduced changeover by 30%'],
          },
        ],
        education: [{ title: 'MSc', institution: 'University', date_range: '2010-2015' }],
        it_ai_skills: ['Automation'],
        technical_operational_skills: ['KAIZEN'],
      },
      metadata: {
        flow_mode: 'wizard',
        wizard_stage: 'cover_letter_review',
      },
      readiness: {
        can_generate: true,
        required_present: {
          full_name: true,
          email: true,
          phone: true,
          work_experience: true,
          education: true,
        },
        confirmed_flags: {
          contact_confirmed: true,
          education_confirmed: true,
        },
        missing: [],
      },
    });
  });

  await page.route('**/api/process-cv', async (route) => {
    const raw = route.request().postData() || '{}';
    const req = JSON.parse(raw) as ProcessReq;
    seen.push(req);

    if ((req.user_action?.id || '') === 'COVER_LETTER_GENERATE') {
      await fulfillJson(route, {
        success: true,
        session_id: sessionId,
        response: 'Cover letter PDF generated.',
        ui_action: {
          kind: 'review_form',
          stage: 'COVER_LETTER',
          title: 'Stage 7/7 — Cover Letter (optional)',
          text: 'Review your cover letter draft. Generate the final 1-page PDF when ready.',
          fields: [
            {
              key: 'cover_letter_preview',
              label: 'Cover letter',
              value: 'Generated draft',
            },
          ],
          actions: [
            { id: 'COVER_LETTER_GENERATE', label: 'Generate final Cover Letter PDF', style: 'primary' },
            { id: 'COVER_LETTER_BACK', label: 'Back', style: 'secondary' },
          ],
          disable_free_text: true,
        },
        stage: 'cover_letter_review',
        pdf_base64: Buffer.from('pdf-bytes').toString('base64'),
        filename: 'cover-letter.pdf',
      });
      return;
    }

    await fulfillJson(route, {
      success: true,
      session_id: sessionId,
      response: 'Resume loaded.',
      ui_action: {
        kind: 'review_form',
        stage: 'COVER_LETTER',
        title: 'Stage 7/7 — Cover Letter (optional)',
        text: 'Review your cover letter draft. Generate the final 1-page PDF when ready.',
        fields: [{ key: 'cover_letter_preview', label: 'Cover letter', value: '(not generated)' }],
        actions: [
          { id: 'COVER_LETTER_GENERATE', label: 'Generate final Cover Letter PDF', style: 'primary' },
          { id: 'COVER_LETTER_BACK', label: 'Back', style: 'secondary' },
        ],
        disable_free_text: true,
      },
      stage: 'cover_letter_review',
    });
  });

  return { sessionId, seen };
}

test.describe('Cover letter generate action', () => {
  test('dispatches user_action without forced start message and updates stage panel', async ({ page }) => {
    test.setTimeout(120_000);

    const { sessionId, seen } = await setupMock(page);

    await page.addInitScript((sid) => {
      window.localStorage.setItem('cvgen:session_id', sid);
    }, sessionId);

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    const stagePanel = page.getByTestId('stage-panel');
    await expect(stagePanel).toBeVisible({ timeout: 30_000 });

    const generateBtn = stagePanel.getByTestId('action-COVER_LETTER_GENERATE');
    await expect(generateBtn).toBeVisible({ timeout: 30_000 });
    await expect(generateBtn).toBeEnabled({ timeout: 30_000 });

    const reqPromise = page.waitForRequest(
      (r) =>
        r.url().includes('/api/process-cv') &&
        r.method() === 'POST' &&
        String(r.postData() || '').includes('COVER_LETTER_GENERATE'),
      { timeout: 30_000 }
    );

    await generateBtn.click();
    const req = await reqPromise;
    const body = JSON.parse(req.postData() || '{}') as ProcessReq;

    expect(body.user_action?.id).toBe('COVER_LETTER_GENERATE');
    expect((body.message || '').trim()).toBe('');

    await expect(stagePanel).toContainText('Generated draft');
    await expect(page.getByTestId('download-pdf')).toBeVisible({ timeout: 30_000 });

    const generateCalls = seen.filter((r) => r.user_action?.id === 'COVER_LETTER_GENERATE');
    expect(generateCalls).toHaveLength(1);
  });
});
