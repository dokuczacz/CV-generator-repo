import { test, expect, type Locator } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SESSION_ID = process.env.E2E_STABLE_SESSION_ID || '539dd501-46df-4454-a9f3-a5040afda2bc';

async function getStage(panel: Locator): Promise<string> {
  return ((await panel.getAttribute('data-wizard-stage')) || '').trim();
}

test('session WORK_TAILOR_RUN advances to work_tailor_review', async ({ page }) => {
  test.setTimeout(180_000);

  await page.addInitScript((sid) => {
    try {
      window.localStorage.setItem('cvgen:session_id', sid);
    } catch {
      // ignore
    }
  }, SESSION_ID);

  await page.goto(BASE_URL, { waitUntil: 'networkidle' });

  const panel = page.getByTestId('stage-panel');
  await expect(panel).toBeVisible({ timeout: 60_000 });

  let stage = '';
  const waitStart = Date.now();
  while (Date.now() - waitStart < 30_000) {
    stage = await getStage(panel);
    if (stage) break;
    await page.waitForTimeout(250);
  }
  expect(stage.length).toBeGreaterThan(0);

  if (stage === 'work_tailor_review') {
    await expect(panel.getByTestId('action-WORK_TAILOR_ACCEPT')).toBeVisible({ timeout: 15_000 });
    return;
  }

  const alreadyPastWorkStage = [
    'work_tailor_feedback',
    'it_ai_skills',
    'skills_tailor_review',
    'review_final',
    'generate_confirm',
    'cover_letter_review',
  ].includes(stage);
  if (alreadyPastWorkStage) {
    expect(stage.length).toBeGreaterThan(0);
    return;
  }

  const runBtn = panel.getByTestId('action-WORK_TAILOR_RUN');
  const runVisible = await runBtn.isVisible().catch(() => false);
  if (!runVisible) {
    const more = panel.getByText('Więcej akcji').first();
    if (await more.isVisible().catch(() => false)) {
      await more.click();
    }
  }

  const hasRunButton = await runBtn.isVisible().catch(() => false);
  if (!hasRunButton) {
    throw new Error(`Session is not in a runnable work tailoring state. Current stage='${stage}'.`);
  }
  await expect(runBtn).toBeVisible({ timeout: 30_000 });
  await expect(runBtn).toBeEnabled({ timeout: 30_000 });

  const reqPromise = page.waitForRequest(
    (req) =>
      req.url().includes('/api/process-cv') &&
      req.method() === 'POST' &&
      String(req.postData() || '').includes('WORK_TAILOR_RUN'),
    { timeout: 60_000 }
  );

  const respPromise = page.waitForResponse(
    (res) => res.url().includes('/api/process-cv') && res.request().method() === 'POST',
    { timeout: 120_000 }
  );

  await runBtn.click();
  await reqPromise;
  const response = await respPromise;

  let responseBody: any = null;
  try {
    responseBody = await response.json();
  } catch {
    responseBody = null;
  }

  const stageWaitStart = Date.now();
  while (Date.now() - stageWaitStart < 45_000) {
    stage = await getStage(panel);
    if (stage === 'work_tailor_review') break;
    await page.waitForTimeout(400);
  }

  if (stage !== 'work_tailor_review') {
    const assistant = (responseBody && String(responseBody.assistant_text || '')) || '';
    const backendStage =
      responseBody && responseBody.metadata && typeof responseBody.metadata.wizard_stage === 'string'
        ? responseBody.metadata.wizard_stage
        : '';
    throw new Error(
      `Expected work_tailor_review, got ui_stage='${stage}', backend_stage='${backendStage}', assistant='${assistant.slice(
        0,
        240
      )}'`
    );
  }

  await expect(panel.getByTestId('action-WORK_TAILOR_ACCEPT')).toBeVisible({ timeout: 30_000 });
});
