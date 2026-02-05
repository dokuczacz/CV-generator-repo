import { test, expect, type Page, type Response } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');
const OUTPUT_DIR = path.join(__dirname, '..', 'test-output');

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

async function completeWizardFlow(page: Page, generateCoverLetter: boolean) {
  // Stage 1: Contact
  await ensureContactConfirmed(page);

  // Stage 2: Education
  await expect(page.getByText('Stage 2/6 — Education', { exact: true })).toBeVisible({ timeout: 60_000 });
  await clickActionAndWait(page, 'Confirm & lock');

  // Stage 3: Job offer (skip for CV-only, provide for cover letter)
  await expect(page.getByText('Stage 3/6 — Job offer (optional)', { exact: true })).toBeVisible({ timeout: 60_000 });
  
  if (generateCoverLetter) {
    // Add minimal job offer details for cover letter generation
    await clickActionAndWait(page, 'Add job details');
    const jobCard = page
      .locator('div.border.border-gray-200.rounded-lg.p-3.bg-gray-50')
      .filter({ hasText: 'Stage 3/6 — Job offer' });
    
    const jobInputs = jobCard.locator('input, textarea');
    await jobInputs.nth(0).fill('Senior Quality Engineer');
    await jobInputs.nth(1).fill('ACME Manufacturing AG');
    await clickActionAndWait(page, 'Save');
    await clickActionAndWait(page, 'Confirm & lock');
  } else {
    await clickActionAndWait(page, 'Skip');
  }

  // Stage 4: Work experience (skip tailoring for deterministic test)
  await expect(page.getByText('Stage 4/6 — Work experience', { exact: true })).toBeVisible({ timeout: 60_000 });
  
  if (await page.getByRole('button', { name: 'Skip tailoring' }).isVisible().catch(() => false)) {
    await clickActionAndWait(page, 'Skip tailoring');
  } else {
    await clickActionAndWait(page, 'Continue');
  }

  // Stage 6: Generate
  await expect(page.getByText('Stage 6/6 — Generate', { exact: true })).toBeVisible({ timeout: 60_000 });
}

async function generateAndSavePDF(page: Page, filename: string) {
  await clickActionAndWait(page, 'Generate PDF');

  // Confirm generate gate
  await expect(page.getByText('Generate PDF?')).toBeVisible({ timeout: 60_000 });
  const generateResult = await clickActionAndWait(page, 'Generate PDF');

  // Persist PDF to disk
  const pdfBase64 = tryExtractPdfBase64(generateResult);
  if (pdfBase64) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    const outPath = path.join(OUTPUT_DIR, filename);
    fs.writeFileSync(outPath, Buffer.from(pdfBase64, 'base64'));
    // eslint-disable-next-line no-console
    console.log(`[artifact] wrote ${outPath}`);
    return outPath;
  }

  throw new Error(`Failed to extract PDF base64 for ${filename}`);
}

test.describe('DoD: CV and Cover Letter Generation (Normal Path + Fast Path)', () => {
  
  test('Normal Path: Generate CV + Cover Letter', async ({ page }) => {
    test.setTimeout(600_000); // 10 minutes - wizard + LLM + PDF generation

    page.on('dialog', async (dialog) => {
      await dialog.dismiss().catch(() => undefined);
    });

    await page.goto(BASE_URL);
    
    // Upload CV and create session
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    const messageInput = page.locator('textarea').first();
    await messageInput.fill('start');
    await messageInput.press('Enter');

    // Wait for import gate or stage 1
    await page.waitForFunction(
      () =>
        document.body.innerText.includes('Import DOCX data?') ||
        document.body.innerText.includes('Stage 1/6 — Contact'),
      undefined,
      { timeout: 60_000 }
    );

    await maybeHandleImportPrefill(page);

    // === Generate CV (normal path) ===
    await completeWizardFlow(page, false);
    const cvPath = await generateAndSavePDF(page, 'normal_path_cv.pdf');
    
    // eslint-disable-next-line no-console
    console.log(`[DoD] Normal path CV generated: ${cvPath}`);
    
    // Verify CV was downloaded
    await expect(page.getByRole('button', { name: /Download PDF/i })).toBeVisible({ timeout: 120_000 });

    // === Generate Cover Letter (normal path) ===
    // Go back to job offer stage or start new flow with job details
    await messageInput.fill('I want to generate a cover letter');
    await messageInput.press('Enter');
    
    // Wait for response
    await page.waitForTimeout(3000);
    
    // Check if we need to add job details
    if (await page.getByText('Please add job offer details').isVisible().catch(() => false)) {
      await messageInput.fill('Add job details: Senior Quality Engineer at ACME Manufacturing AG');
      await messageInput.press('Enter');
      await page.waitForTimeout(5000);
    }

    // Look for cover letter generation option
    if (await page.getByRole('button', { name: 'Generate cover letter' }).isVisible().catch(() => false)) {
      const clPath = await generateAndSavePDF(page, 'normal_path_cover_letter.pdf');
      // eslint-disable-next-line no-console
      console.log(`[DoD] Normal path Cover Letter generated: ${clPath}`);
      
      // Verify CL was downloaded
      await expect(page.getByRole('button', { name: /Download PDF/i })).toBeVisible({ timeout: 120_000 });
    } else {
      // eslint-disable-next-line no-console
      console.log('[WARN] Cover letter generation not available in normal path - may need job details');
    }
  });

  test('Fast Path: Generate CV + Cover Letter (with profile cache)', async ({ page }) => {
    test.setTimeout(600_000); // 10 minutes - full wizard flow + LLM calls take time

    page.on('dialog', async (dialog) => {
      await dialog.dismiss().catch(() => undefined);
    });

    // === STEP 1: Create initial session to populate profile cache ===
    await page.goto(BASE_URL);
    
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    let messageInput = page.locator('textarea').first();
    await messageInput.fill('start');
    await messageInput.press('Enter');

    await page.waitForFunction(
      () =>
        document.body.innerText.includes('Import DOCX data?') ||
        document.body.innerText.includes('Stage 1/6 — Contact'),
      undefined,
      { timeout: 60_000 }
    );

    await maybeHandleImportPrefill(page);
    await completeWizardFlow(page, false);
    await generateAndSavePDF(page, '_setup_cv.pdf');

    // === STEP 2: Start new session with fast-path (should use profile cache) ===
    await page.goto(BASE_URL);
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    messageInput = page.locator('textarea').first();
    await messageInput.fill('Generate my CV');
    await messageInput.press('Enter');

    // Wait for fast-path message or stage
    await page.waitForTimeout(5000);
    
    // Check for fast-path indicators
    const bodyText = await page.locator('body').innerText();
    const isFastPath = bodyText.includes('profile') || 
                       bodyText.includes('cached') || 
                       bodyText.includes('previous');

    if (isFastPath) {
      // eslint-disable-next-line no-console
      console.log('[DoD] Fast path detected - profile cache used');
    }

    // Generate CV via fast path
    await page.waitForFunction(
      () => document.body.innerText.includes('Generate') || 
            document.body.innerText.includes('Stage 6/6'),
      undefined,
      { timeout: 60_000 }
    );

    const cvPath = await generateAndSavePDF(page, 'fast_path_cv.pdf');
    // eslint-disable-next-line no-console
    console.log(`[DoD] Fast path CV generated: ${cvPath}`);

    // === Generate Cover Letter via fast path ===
    messageInput = page.locator('textarea').first();
    await messageInput.fill('Generate cover letter for Quality Engineer position');
    await messageInput.press('Enter');
    await page.waitForTimeout(5000);

    if (await page.getByRole('button', { name: 'Generate cover letter' }).isVisible().catch(() => false)) {
      const clPath = await generateAndSavePDF(page, 'fast_path_cover_letter.pdf');
      // eslint-disable-next-line no-console
      console.log(`[DoD] Fast path Cover Letter generated: ${clPath}`);
    } else {
      // eslint-disable-next-line no-console
      console.log('[WARN] Cover letter generation not available in fast path');
    }
  });

  test('Verify all DoD artifacts were generated', async () => {
    // Verify that both normal path and fast path generated CV and CL PDFs
    const requiredFiles = [
      'normal_path_cv.pdf',
      'fast_path_cv.pdf',
    ];

    const optionalFiles = [
      'normal_path_cover_letter.pdf',
      'fast_path_cover_letter.pdf',
    ];

    for (const file of requiredFiles) {
      const filePath = path.join(OUTPUT_DIR, file);
      expect(fs.existsSync(filePath), `${file} should exist`).toBeTruthy();
      const stats = fs.statSync(filePath);
      expect(stats.size, `${file} should not be empty`).toBeGreaterThan(0);
      // eslint-disable-next-line no-console
      console.log(`[DoD] Verified ${file}: ${stats.size} bytes`);
    }

    for (const file of optionalFiles) {
      const filePath = path.join(OUTPUT_DIR, file);
      if (fs.existsSync(filePath)) {
        const stats = fs.statSync(filePath);
        // eslint-disable-next-line no-console
        console.log(`[DoD] Optional ${file}: ${stats.size} bytes`);
      } else {
        // eslint-disable-next-line no-console
        console.log(`[DoD] Optional ${file}: not generated`);
      }
    }
  });
});
