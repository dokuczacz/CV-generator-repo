import { test, expect, type Page, type Response } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

async function clickActionAndWait(page: Page, buttonName: string) {
  const responsePromise = page.waitForResponse(
    (r: Response) => r.url().includes('/api/process-cv') && r.request().method() === 'POST',
    { timeout: 60_000 }
  );

  await page.getByRole('button', { name: buttonName }).click();

  const response = await responsePromise;
  const responseText = await response.text().catch(() => '');
  // eslint-disable-next-line no-console
  console.log(`[process-cv] after "${buttonName}" status=${response.status()} body=${responseText.slice(0, 220)}`);
  return responseText;
}

function tryExtractPdfBase64(jsonText: string): string | null {
  try {
    const obj = JSON.parse(jsonText);
    const pdfBase64 = obj?.pdf_base64;
    return typeof pdfBase64 === 'string' && pdfBase64.length > 0 ? pdfBase64 : null;
  } catch {
    return null;
  }
}

async function maybeHandleImportPrefill(page: Page) {
  const importTitle = page.getByText('Import DOCX data?');
  if (await importTitle.isVisible().catch(() => false)) {
    await expect(page.getByRole('button', { name: 'Import DOCX prefill' })).toBeVisible({ timeout: 60_000 });
    await clickActionAndWait(page, 'Import DOCX prefill');
    await expect(importTitle).toBeHidden({ timeout: 60_000 });
  }
}

async function ensureContactConfirmed(page: Page) {
  await expect(page.getByText('Stage 1/6 — Contact')).toBeVisible({ timeout: 60_000 });

  let body = await clickActionAndWait(page, 'Confirm & lock');
  if (!body.includes('Contact is incomplete')) return;

  // Fill missing required fields.
  await clickActionAndWait(page, 'Edit');
  const contactCard = page
    .locator('div.border.border-gray-200.rounded-lg.p-3.bg-gray-50')
    .filter({ hasText: 'Stage 1/6 — Contact' });

  const inputs = contactCard.locator('input');
  await inputs.nth(0).fill('Test User');
  await inputs.nth(1).fill('test@example.com');
  await inputs.nth(2).fill('+41 79 000 0000');
  await clickActionAndWait(page, 'Save');
  await clickActionAndWait(page, 'Confirm & lock');
}

async function lockAllWorkExperienceRoles(page: Page) {
  await expect(page.getByText('Stage 4/6 — Work experience', { exact: true })).toBeVisible({ timeout: 60_000 });

  // Optional: verify tailoring notes are editable (critical interaction surface).
  if (await page.getByRole('button', { name: 'Add tailoring notes' }).isVisible().catch(() => false)) {
    await clickActionAndWait(page, 'Add tailoring notes');
    const notesCard = page
      .locator('div.border.border-gray-200.rounded-lg.p-3.bg-gray-50')
      .filter({ hasText: 'Stage 4/6 — Work experience' });
    const notesArea = notesCard.locator('textarea').first();
    await expect(notesArea).toBeVisible({ timeout: 60_000 });
    const noteText = 'Emphasize: quality systems (IATF), audits, process improvement, claims reduction.';
    await notesArea.fill(noteText);
    await clickActionAndWait(page, 'Save notes');
    const stageCard = page
      .locator('div.border.border-gray-200.rounded-lg.p-3.bg-gray-50')
      .filter({ hasText: 'Stage 4/6 — Work experience' });
    await expect(stageCard.getByText('Emphasize: quality systems', { exact: false })).toBeVisible({ timeout: 60_000 });
  }

  // If there are no roles, stage can be confirmed immediately.
  if (await page.getByRole('button', { name: 'Confirm & lock stage' }).isVisible().catch(() => false)) {
    await clickActionAndWait(page, 'Confirm & lock stage');
    return;
  }

  // Otherwise lock roles one by one: open index i, lock, back to list.
  for (let i = 0; i < 20; i++) {
    // List view
    await expect(page.getByRole('button', { name: 'Select role' })).toBeVisible({ timeout: 60_000 });
    await clickActionAndWait(page, 'Select role');

    // Select role form
    const stageCard = page
      .locator('div.border.border-gray-200.rounded-lg.p-3.bg-gray-50')
      .filter({ hasText: 'Stage 4/6 — Work experience' });
    const roleIndexInput = stageCard.locator('input').first();
    await expect(roleIndexInput).toBeVisible({ timeout: 60_000 });
    await roleIndexInput.fill(String(i));
    const openBody = await clickActionAndWait(page, 'Open role');

    // If index is invalid, we're done.
    if (openBody.includes('Invalid role index')) {
      // Back to list (Cancel is safest if we stayed in select form)
      if (await page.getByRole('button', { name: 'Cancel' }).isVisible().catch(() => false)) {
        await clickActionAndWait(page, 'Cancel');
      }
      break;
    }

    // Role view: lock and go back.
    await expect(page.getByRole('button', { name: /Lock role/i })).toBeVisible({ timeout: 60_000 });
    await clickActionAndWait(page, 'Lock role');
    await clickActionAndWait(page, 'Back to list');

    // If stage confirm is now available, proceed.
    if (await page.getByRole('button', { name: 'Confirm & lock stage' }).isVisible().catch(() => false)) {
      await clickActionAndWait(page, 'Confirm & lock stage');
      return;
    }
  }

  // Last attempt: if confirm is available now, click it.
  if (await page.getByRole('button', { name: 'Confirm & lock stage' }).isVisible().catch(() => false)) {
    await clickActionAndWait(page, 'Confirm & lock stage');
  }
}

test.describe('CV Generator E2E', () => {
  test('should load chat interface', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Check for main elements
    await expect(page.getByText('CV Generator')).toBeVisible();
    await expect(page.locator('input[type="file"]')).toBeVisible();
    await expect(page.locator('textarea')).toBeVisible();
  });

  test('should generate PDF through deterministic wizard (sample DOCX)', async ({ page }) => {
    test.setTimeout(180_000);

    page.on('dialog', async (dialog) => {
      await dialog.dismiss().catch(() => undefined);
    });

    await page.goto(BASE_URL);
    
    // Upload CV and create a session by sending any message.
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    const messageInput = page.locator('textarea').first();
    await messageInput.fill('start');
    await messageInput.press('Enter');

    // Wait for import gate or stage 1.
    await page.waitForFunction(
      () =>
        document.body.innerText.includes('Import DOCX data?') ||
        document.body.innerText.includes('Stage 1/6 — Contact'),
      undefined,
      { timeout: 60_000 }
    );

    await maybeHandleImportPrefill(page);

    // Stage 1: Contact
    await ensureContactConfirmed(page);

    // Stage 2: Education
    await expect(page.getByText('Stage 2/6 — Education', { exact: true })).toBeVisible({ timeout: 60_000 });
    await clickActionAndWait(page, 'Confirm & lock');

    // Stage 3: Job offer (skip)
    await expect(page.getByText('Stage 3/6 — Job offer (optional)', { exact: true })).toBeVisible({ timeout: 60_000 });
    await clickActionAndWait(page, 'Skip');

    // Stage 4: Work experience (lock roles and confirm stage)
    await lockAllWorkExperienceRoles(page);

    // Stage 6: Generate
    await expect(page.getByText('Stage 6/6 — Generate', { exact: true })).toBeVisible({ timeout: 60_000 });
    await clickActionAndWait(page, 'Generate PDF');

    // Confirm generate gate
    await expect(page.getByText('Generate PDF?')).toBeVisible({ timeout: 60_000 });
    const generateResult = await clickActionAndWait(page, 'Generate PDF');

    // Persist PDF to disk for easy access.
    const pdfBase64 = tryExtractPdfBase64(generateResult);
    if (pdfBase64) {
      const outDir = path.join(__dirname, '..', 'test-output');
      fs.mkdirSync(outDir, { recursive: true });
      const outPath = path.join(outDir, 'mariusz_generated_cv.pdf');
      fs.writeFileSync(outPath, Buffer.from(pdfBase64, 'base64'));
      // eslint-disable-next-line no-console
      console.log(`[artifact] wrote ${outPath}`);
    }

    // PDF should be available.
    await expect(page.getByRole('button', { name: /Download PDF/i })).toBeVisible({ timeout: 120_000 });
  });

  test('should validate error handling', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Try to generate without uploading
    const messageInput = page.locator('textarea');
    await messageInput.fill('Generate PDF');
    await messageInput.press('Enter');
    
    // Should show error or instruction to upload
    await expect(page.getByText('Please upload your CV DOCX to start.')).toBeVisible({ timeout: 10000 });
  });

});

test.describe('CV Generator API Integration', () => {
  
  test('should call health endpoint', async ({ request }) => {
    const response = await request.get(`${process.env.AZURE_FUNCTIONS_URL || 'http://localhost:7071'}/api/health`);
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(data.status).toBe('healthy');
  });

  test('should handle cleanup endpoint', async ({ request }) => {
    const response = await request.post(
      `${process.env.AZURE_FUNCTIONS_URL || 'http://localhost:7071'}/api/cv-tool-call-handler`,
      {
        data: {
          tool_name: 'cleanup_expired_sessions',
          params: {}
        }
      }
    );
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.success).toBeTruthy();
  });

});
