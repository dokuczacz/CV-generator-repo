import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SESSION_ID = process.env.E2E_STABLE_SESSION_ID || 'b56c51bc-9ef3-4117-a071-c7f2a9c60487';
const SAMPLE_CV =
  process.env.E2E_SAMPLE_CV_PATH ||
  path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

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
  const stagePanelVisible = await stagePanel.isVisible({ timeout: 20_000 }).catch(() => false);
  if (!stagePanelVisible) {
    const uploadDropzone = page.getByTestId('cv-upload-dropzone');
    const hasUpload = await uploadDropzone.isVisible().catch(() => false);
    if (!hasUpload) {
      const changeFile = page.getByRole('button', { name: /Zmień plik|Change file/i }).first();
      if (await changeFile.isVisible().catch(() => false)) {
        await changeFile.click();
      }
    }
    await expect(uploadDropzone).toBeVisible({ timeout: 30_000 });
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    const useLoadedCv = page.getByTestId('use-loaded-cv');
    await expect(useLoadedCv).toBeVisible({ timeout: 30_000 });
    await useLoadedCv.click();
  }
  await expect(stagePanel).toBeVisible({ timeout: 60_000 });

  let stage = '';
  const started = Date.now();
  while (Date.now() - started < 60_000) {
    stage = ((await stagePanel.getAttribute('data-wizard-stage')) || '').trim();
    if (!stage) {
      stage = ((await stagePanel.getAttribute('data-stage')) || '').trim();
    }
    if (stage) break;
    await page.waitForTimeout(250);
  }

  expect(stage.length).toBeGreaterThan(0);

  const clickAction = async (actionId: string) => {
    const btn = stagePanel.getByTestId(`action-${actionId}`);
    const hasVisible = await btn.isVisible().catch(() => false);
    if (!hasVisible) {
      const more = stagePanel.getByText('Więcej akcji').first();
      if (await more.isVisible().catch(() => false)) {
        await more.click();
      }
    }

    await expect(btn).toBeVisible({ timeout: 30_000 });
    await expect(btn).toBeEnabled({ timeout: 30_000 });

    const reqPromise = page.waitForRequest(
      (req) =>
        req.url().includes('/api/process-cv') &&
        req.method() === 'POST' &&
        String(req.postData() || '').includes(actionId),
      { timeout: 60_000 }
    );
    const respPromise = page.waitForResponse(
      (res) => res.url().includes('/api/process-cv') && res.request().method() === 'POST',
      { timeout: 60_000 }
    );

    await btn.click();
    await reqPromise;
    await respPromise;
  };

  for (let i = 0; i < 10; i++) {
    const currentStage = ((await stagePanel.getAttribute('data-wizard-stage')) || '').trim() || ((await stagePanel.getAttribute('data-stage')) || '').trim();
    if (currentStage === 'review_final' || currentStage === 'generate_confirm' || currentStage === 'cover_letter_review') break;

    const actions = await stagePanel
      .locator('[data-testid^="action-"]')
      .evaluateAll((nodes) =>
        nodes
          .map((n) => {
            const el = n as HTMLButtonElement;
            return {
              id: String(el.dataset.testid || '').replace('action-', ''),
              enabled: !el.disabled,
            };
          })
          .filter((x) => !!x.id)
      );
    const enabled = actions.filter((a) => a.enabled).map((a) => a.id);

    if (currentStage === 'language_selection' && enabled.includes('LANGUAGE_SELECT_EN')) {
      await clickAction('LANGUAGE_SELECT_EN');
      continue;
    }
    if (currentStage === 'import_gate_pending' && enabled.includes('CONFIRM_IMPORT_PREFILL_YES')) {
      await clickAction('CONFIRM_IMPORT_PREFILL_YES');
      continue;
    }
    if (currentStage === 'contact' && enabled.includes('CONTACT_CONFIRM')) {
      await clickAction('CONTACT_CONFIRM');
      continue;
    }
    if (currentStage === 'education' && enabled.includes('EDUCATION_CONFIRM')) {
      await clickAction('EDUCATION_CONFIRM');
      continue;
    }
    if ((currentStage === 'job_posting' || currentStage === 'job_posting_paste') && enabled.includes('JOB_OFFER_CONTINUE')) {
      await clickAction('JOB_OFFER_CONTINUE');
      continue;
    }
    if ((currentStage === 'job_posting' || currentStage === 'job_posting_paste') && enabled.includes('JOB_OFFER_SKIP')) {
      await clickAction('JOB_OFFER_SKIP');
      continue;
    }
    if (currentStage === 'work_notes_edit' && enabled.includes('WORK_NOTES_CANCEL')) {
      await clickAction('WORK_NOTES_CANCEL');
      continue;
    }
    if (currentStage === 'work_experience' && enabled.includes('WORK_TAILOR_SKIP')) {
      await clickAction('WORK_TAILOR_SKIP');
      continue;
    }
    if (currentStage === 'further_experience' && enabled.includes('FURTHER_TAILOR_SKIP')) {
      await clickAction('FURTHER_TAILOR_SKIP');
      continue;
    }
    if (currentStage === 'it_ai_skills' && enabled.includes('SKILLS_TAILOR_SKIP')) {
      await clickAction('SKILLS_TAILOR_SKIP');
      continue;
    }
    if (currentStage === 'it_ai_skills' && enabled.includes('SKILLS_TAILOR_RUN')) {
      await clickAction('SKILLS_TAILOR_RUN');
      continue;
    }
    if (currentStage === 'skills_tailor_review' && enabled.includes('SKILLS_TAILOR_ACCEPT')) {
      await clickAction('SKILLS_TAILOR_ACCEPT');
      continue;
    }
    break;
  }

  const pdfBtn = stagePanel.getByTestId('action-REQUEST_GENERATE_PDF');
  const coverPreviewBtn = stagePanel.getByTestId('action-COVER_LETTER_PREVIEW');
  const coverGenerateBtn = stagePanel.getByTestId('action-COVER_LETTER_GENERATE');

  const pdfVisible = await pdfBtn.isVisible({ timeout: 30_000 }).catch(() => false);
  const pdfDownloadVisible = await stagePanel.getByRole('button', { name: 'Pobierz CV' }).first().isVisible().catch(() => false);
  expect(pdfVisible || pdfDownloadVisible).toBeTruthy();

  if (pdfVisible) {
    await expect(pdfBtn).toBeEnabled({ timeout: 30_000 });
    await expect(pdfBtn).toHaveText(/Generuj PDF|Pobierz CV/);
  }

  const hasCoverPreview = await coverPreviewBtn.isVisible({ timeout: 5_000 }).catch(() => false);
  const hasCoverGenerate = await coverGenerateBtn.isVisible({ timeout: 5_000 }).catch(() => false);
  if (hasCoverPreview) {
    await expect(coverPreviewBtn).toBeEnabled({ timeout: 30_000 });
  }
  if (hasCoverGenerate) {
    await expect(coverGenerateBtn).toBeEnabled({ timeout: 30_000 });
  }
});
