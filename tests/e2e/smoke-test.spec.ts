import { test, expect, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

test('quick smoke test - contact + education only', async ({ page }) => {
  test.setTimeout(120_000);

  page.on('dialog', async (dialog) => {
    await dialog.dismiss().catch(() => undefined);
  });

  console.log('[smoke] Starting test...');
  
  // Load page
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  console.log('[smoke] Page loaded');

  // Upload CV
  await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
  const messageInput = page.locator('textarea').first();
  await messageInput.fill('start');
  
  const sendButton = page.getByRole('button', { name: /Send/i });
  await expect(sendButton).toBeEnabled({ timeout: 10_000 });
  
  console.log('[smoke] Sending initial message...');
  await messageInput.press('Enter');
  
  // Wait for import gate or stage 1
  await page.waitForFunction(
    () => {
      const text = document.body.innerText;
      return text.includes('confirm whether to import') || text.includes('Language Selection');
    },
    undefined,
    { timeout: 60_000 }
  );
  console.log('[smoke] Import/Language stage reached');

  // Handle language selection
  const langBtn = page.getByRole('button', { name: /^English$/i });
  if (await langBtn.isVisible().catch(() => false)) {
    console.log('[smoke] Clicking English...');
    const responsePromise = page
      .waitForResponse((r) => r.url().includes('/api/process-cv'), { timeout: 30_000 })
      .catch(() => null);

    await langBtn.click();
    await responsePromise;

    // Wait until we leave Language Selection, or proceed to import / Stage 1.
    await page.waitForFunction(
      () => {
        const text = document.body.innerText;
        return (
          !text.includes('Language Selection') ||
          text.includes('Import DOCX prefill') ||
          /Stage\s+1\s*\//i.test(text)
        );
      },
      undefined,
      { timeout: 60_000 }
    );
    console.log('[smoke] Language selected');
  }

  // Handle import
  const importBtn = page.getByRole('button', { name: /Import DOCX prefill/i });
  if (await importBtn.isVisible().catch(() => false)) {
    console.log('[smoke] Clicking Import DOCX prefill...');
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/process-cv'),
      { timeout: 30_000 }
    ).catch(() => null);
    
    await importBtn.click();
    await responsePromise;
    await page.waitForTimeout(2000);
    console.log('[smoke] DOCX imported');
  }

  // Wait for Stage 1: Contact
  await page.waitForFunction(
    () => /Stage\s+1\s*\//i.test(document.body.innerText),
    undefined,
    { timeout: 30_000 }
  );
  console.log('[smoke] ✓ Stage 1: Contact reached');

  // Click Confirm on Contact
  await page.getByRole('button', { name: /Confirm & lock/i }).first().click();
  await page.waitForTimeout(2000);
  console.log('[smoke] Contact confirmed');

  // Wait for Stage 2: Education
  await page.waitForFunction(
    () => document.body.innerText.includes('Stage 2/6'),
    undefined,
    { timeout: 30_000 }
  );
  console.log('[smoke] ✓ Stage 2: Education reached');

  console.log('[smoke] ✅ Smoke test passed!');
});
