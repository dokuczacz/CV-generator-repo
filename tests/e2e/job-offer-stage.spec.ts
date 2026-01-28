import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

async function clickActionAndLog(page, buttonName: string) {
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes('/api/process-cv') && r.request().method() === 'POST',
    { timeout: 60_000 }
  );

  await page.getByRole('button', { name: buttonName }).click();

  const response = await responsePromise;
  const responseText = await response.text().catch(() => '');
  // eslint-disable-next-line no-console
  console.log(`[process-cv] after "${buttonName}" status=${response.status()} body=${responseText.slice(0, 300)}`);
  return responseText;
}

async function maybeHandleImportPrefill(page) {
  const importTitle = page.getByText('Import DOCX data?');
  if (await importTitle.isVisible().catch(() => false)) {
    // Prefer importing: it usually populates Contact/Education, letting us reach Job Offer quickly.
    // If clicking import fails for any reason, fall back to "Do not import".
    try {
      await expect(page.getByRole('button', { name: 'Import DOCX prefill' })).toBeVisible({ timeout: 60_000 });
      await clickActionAndLog(page, 'Import DOCX prefill');
    } catch {
      await expect(page.getByRole('button', { name: 'Do not import' })).toBeVisible({ timeout: 60_000 });
      await clickActionAndLog(page, 'Do not import');
    }

    await expect(importTitle).toBeHidden({ timeout: 60_000 });
  }
}

async function ensureContactCanConfirm(page) {
  const contactTitle = page.getByText('Stage 1/6 — Contact');
  await expect(contactTitle).toBeVisible({ timeout: 60_000 });

  let body = await clickActionAndLog(page, 'Confirm & lock');
  if (!body.includes('Contact is incomplete')) return;

  await clickActionAndLog(page, 'Edit');

  const contactCard = page
    .locator('div.border.border-gray-200.rounded-lg.p-3.bg-gray-50')
    .filter({ hasText: 'Stage 1/6 — Contact' });

  const inputs = contactCard.locator('input');
  await expect(inputs.first()).toBeVisible({ timeout: 60_000 });

  await inputs.nth(0).fill('Test User');
  await inputs.nth(1).fill('test@example.com');
  await inputs.nth(2).fill('+41 79 000 0000');

  // Address is optional; keep empty for test determinism.
  const addressTextarea = contactCard.locator('textarea').first();
  if (await addressTextarea.isVisible().catch(() => false)) {
    await addressTextarea.fill('');
  }

  await clickActionAndLog(page, 'Save');
  body = await clickActionAndLog(page, 'Confirm & lock');
  expect(body).not.toContain('Contact is incomplete');
}

test.describe('Job offer stage', () => {
  test('should allow pasting job offer text and send it on Analyze', async ({ page }) => {
    test.setTimeout(120_000);

    page.on('pageerror', (err) => {
      // eslint-disable-next-line no-console
      console.log('[pageerror]', err.message);
    });

    page.on('dialog', async (dialog) => {
      // eslint-disable-next-line no-console
      console.log('[dialog]', dialog.type(), dialog.message());
      await dialog.dismiss().catch(() => undefined);
    });

    await page.goto(BASE_URL);

    // Upload CV (file is sent on the first chat message)
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);

    // Create session by sending any message
    const messageInput = page.locator('textarea').first();
    await messageInput.fill('start');
    await messageInput.press('Enter');

    // Wait for the backend to respond with either the import gate or Stage 1.
    await page.waitForFunction(
      () =>
        document.body.innerText.includes('Import DOCX data?') ||
        document.body.innerText.includes('Stage 1/6 — Contact'),
      undefined,
      { timeout: 60_000 }
    );

    // If DOCX prefill import gate appears, resolve it.
    await maybeHandleImportPrefill(page);

    // Stage 1: Contact (auto-fix if required fields are missing)
    await ensureContactCanConfirm(page);

    // Stage 2: Education
    await expect(page.getByText('Stage 2/6 — Education')).toBeVisible({ timeout: 60_000 });
    await clickActionAndLog(page, 'Confirm & lock');

    // Stage 3: Job offer
    await expect(page.getByText('Stage 3/6 — Job offer (optional)')).toBeVisible({ timeout: 60_000 });
    await clickActionAndLog(page, 'Paste job offer text');

    // Paste form should show a textarea and accept input
    const jobOfferCard = page
      .locator('div.border.border-gray-200.rounded-lg.p-3.bg-gray-50')
      .filter({ hasText: 'Stage 3/6 — Job offer (optional)' });
    await expect(jobOfferCard.getByText('Job offer text (or paste a URL)', { exact: true })).toBeVisible();
    const jobOfferTextarea = jobOfferCard.locator('textarea').first();
    await expect(jobOfferTextarea).toBeEnabled();

    const shortJobOffer = 'Short job offer text (intentionally < 80 chars) to validate payload wiring.';
    await jobOfferTextarea.fill(shortJobOffer);

    // Analyze should send payload; backend will reject as too short and echo it back into the form.
    await clickActionAndLog(page, 'Analyze');

    await expect(page.getByText('Job offer text is too short')).toBeVisible({ timeout: 60_000 });
    await expect(jobOfferTextarea).toHaveValue(shortJobOffer);
  });
});
