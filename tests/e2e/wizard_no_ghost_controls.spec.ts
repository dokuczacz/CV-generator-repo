import { test, expect, type Page } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

async function waitForStagePanel(page: Page, timeoutMs = 30_000) {
  await expect(page.getByTestId('stage-panel')).toBeVisible({ timeout: timeoutMs });
}

async function waitForStage(page: Page, stage: string, timeoutMs = 30_000) {
  await expect(page.getByTestId('stage-panel')).toHaveAttribute('data-wizard-stage', stage, { timeout: timeoutMs });
}

async function waitForStageOneOf(page: Page, stages: string[], timeoutMs = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const stage = await page
      .getByTestId('stage-panel')
      .getAttribute('data-wizard-stage')
      .then((v) => (v || '').trim())
      .catch(() => '');
    if (stage && stages.includes(stage)) return stage;
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
  await expect(btn).toBeVisible({ timeout: 20_000 });

  const reqPromise = page.waitForRequest(
    (r) =>
      r.url().includes('/api/process-cv') &&
      r.method() === 'POST' &&
      String(r.postData() || '').includes(actionId),
    { timeout: 30_000 }
  );

  await expect(btn).toBeEnabled();
  await btn.scrollIntoViewIfNeeded().catch(() => undefined);
  await btn.click();

  await reqPromise;
}

async function fillFirstTextareaInStagePanel(page: Page, value: string) {
  const textarea = page.getByTestId('stage-panel').locator('textarea').first();
  await expect(textarea).toBeVisible({ timeout: 20_000 });
  await textarea.fill(value);
}

async function fillContactForm(page: Page) {
  const panel = page.getByTestId('stage-panel');
  const inputs = panel.locator('input');
  const textareas = panel.locator('textarea');
  await expect(inputs.first()).toBeVisible({ timeout: 20_000 });
  await inputs.nth(0).fill('Jan Kowalski');
  await inputs.nth(1).fill('jan.kowalski@example.com');
  await inputs.nth(2).fill('+41 76 123 45 67');
  if (await textareas.first().isVisible().catch(() => false)) {
    await textareas.first().fill('Zurich, Switzerland');
  }
}

test.describe('Wizard: no ghost controls (AI disabled)', () => {
  test('should not require dummy input and every action triggers backend', async ({ page }) => {
    test.setTimeout(300_000);

    let firstProcessCvPayload: any = null;
    page.on('request', (req) => {
      if (firstProcessCvPayload) return;
      if (!req.url().includes('/api/process-cv')) return;
      if (req.method() !== 'POST') return;
      const post = req.postData();
      if (!post) return;
      try {
        firstProcessCvPayload = JSON.parse(post);
      } catch {
        // ignore
      }
    });

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    // Step 1 controls (pre-upload)
    await expect(page.getByTestId('cv-upload-dropzone')).toBeVisible();

    // Toggle fast path (ensure it affects first backend request)
    const fastPath = page.getByRole('checkbox', { name: /Fast path:/i });
    await expect(fastPath).toBeVisible();
    if (await fastPath.isChecked()) await fastPath.uncheck();
    await expect(fastPath).not.toBeChecked();

    await page.getByTestId('job-url-input').fill('https://example.com/job-offer');
    await page.getByTestId('job-text-input').fill('Quick summary: focus on quality audits and compliance.');

    // Upload + explicit start via CTA.
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    const useLoadedCv = page.getByTestId('use-loaded-cv');
    await expect(useLoadedCv).toBeVisible({ timeout: 30_000 });
    await expect(useLoadedCv).toBeEnabled({ timeout: 30_000 });
    await useLoadedCv.click();
    await waitForStagePanel(page, 60_000);

    // Assert first request preserved job inputs and fast path preference.
    expect(firstProcessCvPayload).toBeTruthy();
    expect(firstProcessCvPayload.job_posting_url).toBe('https://example.com/job-offer');
    expect(firstProcessCvPayload.job_posting_text).toBe('Quick summary: focus on quality audits and compliance.');
    expect(firstProcessCvPayload.client_context?.fast_path_profile).toBe(false);

    // Click "Kopiuj" once (should not be a ghost button).
    const copyBtn = page.getByRole('button', { name: /Kopiuj/i }).first();
    if (await copyBtn.isVisible().catch(() => false)) {
      await copyBtn.click();
    }

    // Wizard flow with action coverage.
    const stage0 = await waitForStageOneOf(page, ['language_selection', 'import_gate_pending', 'contact'], 60_000);
    if (stage0 === 'language_selection') {
      await clickAction(page, 'LANGUAGE_SELECT_EN');
    }

    const stage1 = await waitForStageOneOf(page, ['import_gate_pending', 'contact'], 60_000);
    if (stage1 === 'import_gate_pending') {
      await clickAction(page, 'CONFIRM_IMPORT_PREFILL_YES');
    }

    await waitForStage(page, 'contact', 60_000);
    await clickAction(page, 'CONTACT_EDIT');
    await waitForStage(page, 'contact_edit', 30_000);
    await fillContactForm(page);
    await clickAction(page, 'CONTACT_SAVE');
    await waitForStage(page, 'contact', 30_000);
    await clickAction(page, 'CONTACT_CONFIRM');

    await waitForStage(page, 'education', 60_000);
    await clickAction(page, 'EDUCATION_EDIT_JSON');
    await waitForStage(page, 'education_edit_json', 30_000);
    await clickAction(page, 'EDUCATION_CANCEL');
    await waitForStage(page, 'education', 30_000);
    await clickAction(page, 'EDUCATION_CONFIRM');

    await waitForStage(page, 'job_posting', 60_000);
    await clickAction(page, 'INTERESTS_EDIT');
    await waitForStage(page, 'interests_edit', 30_000);
    // Cover Cancel path.
    await clickAction(page, 'INTERESTS_CANCEL');
    await waitForStage(page, 'job_posting', 30_000);
    // Cover Save path.
    await clickAction(page, 'INTERESTS_EDIT');
    await waitForStage(page, 'interests_edit', 30_000);
    await fillFirstTextareaInStagePanel(page, 'Process improvement, automation, hiking');
    await clickAction(page, 'INTERESTS_SAVE');
    await waitForStage(page, 'job_posting', 30_000);

    await clickAction(page, 'JOB_OFFER_PASTE');
    await waitForStage(page, 'job_posting_paste', 30_000);
    await fillFirstTextareaInStagePanel(
      page,
      [
        'Senior Quality Engineer — responsibilities: audits, compliance, process improvement.',
        'Requirements: ISO 9001 / IATF 16949, audit experience, KPI-driven improvements.',
      ].join('\n')
    );
    await clickAction(page, 'JOB_OFFER_ANALYZE');

    const afterJob = await waitForStageOneOf(page, ['job_posting', 'work_notes_edit', 'work_experience'], 60_000);
    if (afterJob === 'job_posting') {
      // Prefer Continue if present, else Skip.
      const continueBtn = page.getByTestId('stage-panel').getByTestId('action-JOB_OFFER_CONTINUE');
      if (await continueBtn.isVisible().catch(() => false)) await clickAction(page, 'JOB_OFFER_CONTINUE');
      else await clickAction(page, 'JOB_OFFER_SKIP');
    }

    const workStage = await waitForStageOneOf(page, ['work_notes_edit', 'work_experience'], 60_000);
    if (workStage === 'work_notes_edit') {
      await clickAction(page, 'WORK_NOTES_CANCEL');
    }
    await waitForStage(page, 'work_experience', 60_000);

    const lock0 = page.getByTestId('work-role-lock-0');
    if (await lock0.isVisible().catch(() => false)) {
      await lock0.scrollIntoViewIfNeeded().catch(() => undefined);
      await lock0.click();
    }
    await waitForStagePanel(page);
    await clickAction(page, 'WORK_TAILOR_SKIP');

    const afterWork = await waitForStageOneOf(page, ['further_experience', 'it_ai_skills'], 60_000);
    if (afterWork === 'further_experience') {
      await expect(page.getByTestId('action-FURTHER_TAILOR_RUN')).toHaveCount(0);
      await clickAction(page, 'FURTHER_TAILOR_SKIP');
    }

    await waitForStage(page, 'it_ai_skills', 60_000);
    await clickAction(page, 'SKILLS_TAILOR_SKIP');

    const stageBeforeGenerate = await waitForStageOneOf(page, ['review_final', 'generate_confirm'], 60_000);
    if (stageBeforeGenerate === 'review_final') {
      await clickAction(page, 'REQUEST_GENERATE_PDF');
    }
    await waitForStageOneOf(page, ['generate_confirm', 'review_final'], 60_000);
    await clickAction(page, 'REQUEST_GENERATE_PDF');

    // Verify PDF is available for download.
    await expect(page.getByTestId('download-pdf')).toBeVisible({ timeout: 60_000 });

    // Cover "Zmień plik" reset path (powrót do uploadu bez zacięcia stanu).
    await page.getByRole('button', { name: /Zmień plik/i }).first().click();
    await expect(page.getByTestId('cv-upload-dropzone')).toBeVisible({ timeout: 30_000 });
  });
});
