import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SESSION_ID = process.env.E2E_STABLE_SESSION_ID || 'b56c51bc-9ef3-4117-a071-c7f2a9c60487';

test('resumed session shows final-stage PDF and cover buttons', async ({ page }) => {
  test.setTimeout(120_000);

  await page.addInitScript((sid) => {
    try {
      window.localStorage.setItem('cvgen:session_id', sid);
    } catch {
      // ignore
    }
  }, SESSION_ID);

  await page.goto(BASE_URL, { waitUntil: 'networkidle' });

  const stagePanel = page.getByTestId('stage-panel');
  await expect(stagePanel).toBeVisible({ timeout: 60_000 });

  let stage = '';
  const started = Date.now();
  while (Date.now() - started < 60_000) {
    stage = ((await stagePanel.getAttribute('data-wizard-stage')) || '').trim();
    if (stage) break;
    await page.waitForTimeout(250);
  }

  expect(stage).toBe('review_final');

  const pdfBtn = stagePanel.getByTestId('action-REQUEST_GENERATE_PDF');
  const coverPreviewBtn = stagePanel.getByTestId('action-COVER_LETTER_PREVIEW');

  await expect(pdfBtn).toBeVisible({ timeout: 30_000 });
  await expect(pdfBtn).toBeEnabled({ timeout: 30_000 });
  await expect(coverPreviewBtn).toBeVisible({ timeout: 30_000 });
  await expect(coverPreviewBtn).toBeEnabled({ timeout: 30_000 });
});
