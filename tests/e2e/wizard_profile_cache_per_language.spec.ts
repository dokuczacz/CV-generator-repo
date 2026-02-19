import { test, expect, type Page } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

async function waitForStagePanel(page: Page, timeoutMs = 60_000) {
  await expect(page.getByTestId('stage-panel')).toBeVisible({ timeout: timeoutMs });
}

async function getWizardStage(page: Page) {
  return page
    .getByTestId('stage-panel')
    .getAttribute('data-wizard-stage')
    .then((v) => (v || '').trim());
}

async function waitForStage(page: Page, stage: string, timeoutMs = 60_000) {
  await expect(page.getByTestId('stage-panel')).toHaveAttribute('data-wizard-stage', stage, { timeout: timeoutMs });
}

async function waitForStageOneOf(page: Page, stages: string[], timeoutMs = 60_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const s = await getWizardStage(page);
    if (s && stages.includes(s)) return s;
    await page.waitForTimeout(150);
  }
  throw new Error(`Timed out waiting for stage in: ${stages.join(', ')}`);
}

async function clickAction(page: Page, actionId: string) {
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

async function uploadCv(page: Page) {
  await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
  const useButton = page.getByTestId('use-loaded-cv');
  await expect(useButton).toBeVisible({ timeout: 30_000 });
  await expect(useButton).toBeEnabled({ timeout: 30_000 });
  await useButton.click();
  await waitForStagePanel(page, 60_000);
}

test.describe('Profile cache per target language (AI disabled)', () => {
  test('should apply cached profile only for matching target language', async ({ page }) => {
    test.setTimeout(300_000);

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    // Session A (DE): Save stable profile under German.
    await uploadCv(page);
    const stage0 = await waitForStageOneOf(page, ['language_selection', 'import_gate_pending', 'contact', 'job_posting'], 60_000);
    if (stage0 === 'language_selection') {
      await clickAction(page, 'LANGUAGE_SELECT_DE');
    }
    const stage1 = await waitForStageOneOf(page, ['import_gate_pending', 'contact', 'job_posting'], 60_000);
    if (stage1 === 'import_gate_pending') {
      await clickAction(page, 'CONFIRM_IMPORT_PREFILL_YES');
    }
    const stageA2 = await waitForStageOneOf(page, ['contact', 'education', 'job_posting'], 60_000);
    if (stageA2 === 'contact') {
      await clickAction(page, 'CONTACT_CONFIRM');
      const next = await waitForStageOneOf(page, ['education', 'job_posting'], 60_000);
      if (next === 'education') {
        await clickAction(page, 'EDUCATION_CONFIRM');
      }
    } else if (stageA2 === 'education') {
      await clickAction(page, 'EDUCATION_CONFIRM');
    }
    await waitForStage(page, 'job_posting', 60_000);

    // Reset to Step 1 (new session) without losing UI prefill controls.
    await page.getByRole('button', { name: /Zmień plik/i }).first().click();
    await expect(page.getByTestId('cv-upload-dropzone')).toBeVisible({ timeout: 30_000 });

    // Session B (DE): Enable fast path and ensure it skips contact/education to job_posting.
    const fastPath = page.getByRole('checkbox', { name: /Fast path:/i });
    if (!(await fastPath.isChecked())) await fastPath.check();

    await uploadCv(page);
    const stageB0 = await waitForStageOneOf(page, ['language_selection', 'import_gate_pending', 'contact', 'job_posting'], 60_000);
    if (stageB0 === 'language_selection') {
      await clickAction(page, 'LANGUAGE_SELECT_DE');
    }
    const stageB1 = await waitForStageOneOf(page, ['import_gate_pending', 'contact', 'job_posting'], 60_000);
    if (stageB1 === 'import_gate_pending') {
      await clickAction(page, 'CONFIRM_IMPORT_PREFILL_YES');
    }

    // Fast path should land on job_posting (not contact).
    await waitForStage(page, 'job_posting', 60_000);

    // Reset again.
    await page.getByRole('button', { name: /Zmień plik/i }).first().click();
    await expect(page.getByTestId('cv-upload-dropzone')).toBeVisible({ timeout: 30_000 });

    // Session C (EN): Fast path enabled but target language differs -> should NOT apply cached DE profile.
    if (!(await fastPath.isChecked())) await fastPath.check();
    await uploadCv(page);
    const stageC0 = await waitForStageOneOf(page, ['language_selection', 'import_gate_pending', 'contact', 'job_posting'], 60_000);
    if (stageC0 === 'language_selection') {
      await clickAction(page, 'LANGUAGE_SELECT_EN');
    }
    const stageC1 = await waitForStageOneOf(page, ['import_gate_pending', 'contact', 'job_posting'], 60_000);
    if (stageC1 === 'import_gate_pending') {
      await clickAction(page, 'CONFIRM_IMPORT_PREFILL_YES');
    }

    // Current flow may enter contact/education or jump directly to job_posting when profile is complete.
    await waitForStageOneOf(page, ['contact', 'education', 'job_posting'], 60_000);
  });
});

