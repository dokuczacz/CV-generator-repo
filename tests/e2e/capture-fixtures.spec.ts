import { test, expect, Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * This test captures all API responses from a full wizard run.
 * Use this to record fixtures for mocked tests.
 * Run with real OpenAI to get complete response data.
 */

const CAPTURE_DIR = path.join(__dirname, '../fixtures');
const RESPONSES_LOG = path.join(__dirname, '../capture-responses.jsonl');

// Ensure capture dir exists
if (!fs.existsSync(CAPTURE_DIR)) {
  fs.mkdirSync(CAPTURE_DIR, { recursive: true });
}

// Clear previous captures
if (fs.existsSync(RESPONSES_LOG)) {
  fs.unlinkSync(RESPONSES_LOG);
}

function logResponse(name: string, response: any) {
  const line = JSON.stringify({
    timestamp: new Date().toISOString(),
    name,
    response
  }) + '\n';
  fs.appendFileSync(RESPONSES_LOG, line);
  console.log(`[CAPTURED] ${name}: ${JSON.stringify(response.ui_action || {}).substring(0, 100)}`);
}

test('capture full wizard flow with real OpenAI', async ({ page }) => {
  // Intercept all /api/process-cv responses to log them
  const responses: { name: string; response: any }[] = [];

  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/process-cv')) {
      try {
        const body = await response.json();
        const actionId = body?.ui_action?.id || 'unknown';
        responses.push({ name: actionId, response: body });
        logResponse(actionId, body);
      } catch (e) {
        console.log('[ERROR] Failed to parse response:', e);
      }
    }
  });

  // Navigate
  console.log('\n[START] Opening CV generator...');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: /CV Generator/i })).toBeVisible({ timeout: 10000 });

  // Upload CV
  console.log('[STEP] Uploading CV file...');
  const fileInput = page.locator('input[type="file"]');
  const sampleFile = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');
  
  if (fs.existsSync(sampleFile)) {
    await fileInput.setInputFiles(sampleFile);
    console.log('[OK] CV file uploaded');
  } else {
    console.log('[ERROR] Sample CV not found at:', sampleFile);
    throw new Error('Sample CV not found');
  }

  // Send initial message
  console.log('[STEP] Sending initial message...');
  const messageInput = page.locator('textarea, input[type="text"]').filter({ hasText: '' }).first();
  try {
    await messageInput.fill('Please analyze my CV', { timeout: 5000 });
    await page.keyboard.press('Enter');
    console.log('[OK] Message sent');
  } catch (e) {
    console.log('[ERROR] Failed to send message:', e);
  }
  await page.waitForTimeout(2000);

  // Handle language selection if present
  console.log('[STEP] Looking for language selection...');
  const langButton = page.locator('button').filter({ hasText: /English|Polski/i }).first();
  if (await langButton.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('[STEP] Selecting language...');
    await langButton.click();
    await page.waitForTimeout(2000);
  }

  // Handle import DOCX confirm
  console.log('[STEP] Looking for import DOCX dialog...');
  const importBtn = page.locator('button').filter({ hasText: /Yes|Confirm|Import|Tak/i }).nth(0);
  if (await importBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('[STEP] Confirming import...');
    await importBtn.click();
    await page.waitForTimeout(2000);
  }

  // Stage 1: Contact
  console.log('[STEP 1/6] Contact stage - waiting for render...');
  await expect(page.getByText(/Stage 1\/6.*Contact/i)).toBeVisible({ timeout: 30000 });
  console.log('[OK] Contact stage visible');
  
  // Find and click the Confirm button (look for "Confirm & lock" text)
  const confirmButton = page.locator('button').filter({ hasText: /Confirm.*lock|Confirm/i }).first();
  if (await confirmButton.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('[STEP] Clicking Confirm button');
    await confirmButton.click();
    await page.waitForTimeout(2000);
  }

  // Stage 2: Education
  console.log('[STEP 2/6] Education stage - waiting...');
  await expect(page.getByText(/Stage 2\/6/i)).toBeVisible({ timeout: 30000 }).catch(() => {
    console.log('[ERROR] Education stage never appeared');
    throw new Error('Education stage timeout');
  });
  console.log('[OK] Education stage visible');
  
  // Click Continue/Confirm for education
  const eduButton = page.locator('button').filter({ hasText: /Confirm|Continue|Next/i }).first();
  if (await eduButton.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('[STEP] Clicking Education button');
    await eduButton.click();
    await page.waitForTimeout(2000);
  }

  // Stage 3: Job offer / Work experience
  console.log('[STEP 3/6] Work experience stage - waiting...');
  await expect(page.getByText(/Stage 3\/6/i)).toBeVisible({ timeout: 30000 }).catch(() => {
    console.log('[ERROR] Stage 3 never appeared');
  });
  await page.locator('button').filter({ hasText: /Skip|Confirm|Next/i }).first().click();
  await page.waitForTimeout(2000);

  // Stage 4: Skills
  console.log('[STEP 4/6] Skills stage - waiting...');
  try {
    await expect(page.getByText(/Stage 4\/6/i)).toBeVisible({ timeout: 30000 });
    await page.locator('button').filter({ hasText: /Confirm|Next|Continue/i }).first().click();
    await page.waitForTimeout(2000);
  } catch (e) {
    console.log('[SKIP] Stage 4 not found');
  }

  // Stage 5: Projects
  console.log('[STEP 5/6] Projects stage - waiting...');
  try {
    await expect(page.getByText(/Stage 5\/6/i)).toBeVisible({ timeout: 30000 });
    await page.locator('button').filter({ hasText: /Confirm|Next|Continue|Generate/i }).first().click();
    await page.waitForTimeout(2000);
  } catch (e) {
    console.log('[SKIP] Stage 5 not found');
  }

  // Stage 6: PDF
  console.log('[STEP 6/6] PDF generation - waiting...');
  try {
    await expect(page.getByText(/Stage 6\/6|PDF|Download|Generated/i)).toBeVisible({ timeout: 30000 });
  } catch (e) {
    console.log('[INFO] PDF stage message');
  }

  console.log('\n[COMPLETE] Fixture capture finished');
  console.log(`[SAVED] ${responses.length} responses logged to ${RESPONSES_LOG}`);
  console.log('\n[NEXT] Run: npx ts-node tests/parse-capture.ts');
});
