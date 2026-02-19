import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

async function getWizardStage(page: any) {
  return page
    .getByTestId('stage-panel')
    .getAttribute('data-wizard-stage')
    .then((v: string | null) => (v || '').trim());
}

async function waitForStageOneOf(page: any, stages: string[], timeoutMs = 60_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const s = await getWizardStage(page);
    if (s && stages.includes(s)) return s;
    await page.waitForTimeout(150);
  }
  throw new Error(`Timed out waiting for stage in: ${stages.join(', ')}`);
}

async function waitForStage(page: any, stage: string, timeoutMs = 60_000) {
  await expect(page.getByTestId('stage-panel')).toHaveAttribute('data-wizard-stage', stage, { timeout: timeoutMs });
}

async function clickAction(page: any, actionId: string) {
  const panel = page.getByTestId('stage-panel');
  const btn = panel.getByTestId(`action-${actionId}`);
  if (!(await btn.isVisible().catch(() => false))) {
    const more = panel.getByText('Więcej akcji').first();
    if (await more.isVisible().catch(() => false)) {
      await more.click();
    }
  }
  await expect(btn).toBeVisible({ timeout: 30_000 });
  await expect(btn).toBeEnabled({ timeout: 30_000 });
  await btn.click();
}

test('quick smoke test - contact + education only', async ({ page }) => {
  test.setTimeout(120_000);

  page.on('dialog', async (dialog) => {
    await dialog.dismiss().catch(() => undefined);
  });

  console.log('[smoke] Starting test...');
  
  // Load page
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  console.log('[smoke] Page loaded');

  // Force deterministic path for this smoke: do not skip contact/education via fast profile.
  const fastPath = page.getByRole('checkbox', { name: /Fast path:/i });
  if (await fastPath.isVisible().catch(() => false)) {
    if (await fastPath.isChecked()) {
      await fastPath.uncheck();
    }
  }

  // Upload CV
  await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
  const useLoadedCv = page.getByTestId('use-loaded-cv');
  await expect(useLoadedCv).toBeVisible({ timeout: 30_000 });
  await expect(useLoadedCv).toBeEnabled({ timeout: 30_000 });
  console.log('[smoke] Starting wizard from uploaded CV...');
  await useLoadedCv.click();
  
  await expect(page.getByTestId('stage-panel')).toBeVisible({ timeout: 60_000 });

  // Wait for language/import/contact entry stage.
  const stage0 = await waitForStageOneOf(page, ['language_selection', 'import_gate_pending', 'contact'], 60_000);
  console.log('[smoke] Import/Language stage reached');

  // Handle language selection.
  if (stage0 === 'language_selection') {
    console.log('[smoke] Clicking English...');
    await clickAction(page, 'LANGUAGE_SELECT_EN');
    console.log('[smoke] Language selected');
  }

  const stage1 = await waitForStageOneOf(page, ['import_gate_pending', 'contact'], 60_000);

  // Handle import gate if present.
  if (stage1 === 'import_gate_pending') {
    console.log('[smoke] Clicking Import DOCX prefill...');
    await clickAction(page, 'CONFIRM_IMPORT_PREFILL_YES');
    console.log('[smoke] DOCX imported');
  }

  // Wait for Stage 1: Contact
  await waitForStage(page, 'contact', 60_000);
  console.log('[smoke] ✓ Stage 1: Contact reached');

  // Click Confirm on Contact
  await clickAction(page, 'CONTACT_CONFIRM');
  console.log('[smoke] Contact confirmed');

  // Wait for Stage 2: Education
  await waitForStage(page, 'education', 60_000);
  console.log('[smoke] ✓ Stage 2: Education reached');

  console.log('[smoke] ✅ Smoke test passed!');
});
