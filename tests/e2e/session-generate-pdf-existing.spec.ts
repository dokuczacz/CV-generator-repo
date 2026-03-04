import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SESSION_ID = process.env.E2E_STABLE_SESSION_ID || 'c088833f-3791-498f-98ef-6bc69afcaa28';
const SAMPLE_CV =
  process.env.E2E_SAMPLE_CV_PATH ||
  path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

test('existing session reaches generate and produces download action', async ({ page }) => {
  test.setTimeout(240_000);

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

  const getStage = async () => {
    const wizardStage = ((await stagePanel.getAttribute('data-wizard-stage')) || '').trim();
    if (wizardStage) return wizardStage;
    return ((await stagePanel.getAttribute('data-stage')) || '').trim();
  };

  const waitEnabledAction = async (ids: string[], timeoutMs = 20_000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      for (const id of ids) {
        const btn = stagePanel.locator(`[data-testid="action-${id}"]:visible`).first();
        const visible = await btn.isVisible().catch(() => false);
        const enabled = visible ? await btn.isEnabled().catch(() => false) : false;
        if (visible && enabled) return { id, btn };
      }
      await page.waitForTimeout(250);
    }
    return null;
  };

  const clickAction = async (actionId: string) => {
    const btn = stagePanel.locator(`[data-testid="action-${actionId}"]:visible`).first();
    await expect(btn).toBeVisible({ timeout: 30_000 });
    await expect(btn).toBeEnabled({ timeout: 30_000 });

    const reqPromise = page.waitForRequest(
      (req) => req.url().includes('/api/process-cv') && req.method() === 'POST' && String(req.postData() || '').includes(actionId),
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

  for (let i = 0; i < 15; i++) {
    const stage = await getStage();

    if (stage === 'review_final' || stage === 'generate_confirm' || stage === 'cover_letter_review') {
      break;
    }

    if (stage === 'it_ai_skills') {
      const action = await waitEnabledAction(['SKILLS_TAILOR_ACCEPT', 'SKILLS_TAILOR_SKIP', 'SKILLS_TAILOR_RUN'], 20_000);
      if (!action) throw new Error('No enabled skills action in it_ai_skills stage');
      await clickAction(action.id);
      continue;
    }

    if (stage === 'skills_tailor_review') {
      const action = await waitEnabledAction(['SKILLS_TAILOR_ACCEPT', 'SKILLS_TAILOR_SKIP'], 20_000);
      if (!action) throw new Error('No enabled skills review action in skills_tailor_review stage');
      await clickAction(action.id);
      continue;
    }

    if (stage === 'contact' || stage === 'education') {
      const action = await waitEnabledAction(
        stage === 'contact' ? ['CONTACT_CONFIRM'] : ['EDUCATION_CONFIRM'],
        15_000
      );
      if (action) {
        await clickAction(action.id);
        continue;
      }
    }

    if (stage === 'job_posting' || stage === 'job_posting_paste') {
      const action = await waitEnabledAction(['JOB_OFFER_CONTINUE', 'JOB_OFFER_SKIP'], 15_000);
      if (action) {
        await clickAction(action.id);
        continue;
      }
    }

    if (stage === 'work_notes_edit') {
      const action = await waitEnabledAction(['WORK_NOTES_CANCEL'], 15_000);
      if (action) {
        await clickAction(action.id);
        continue;
      }
    }

    if (stage === 'work_experience') {
      const action = await waitEnabledAction(['WORK_TAILOR_SKIP'], 15_000);
      if (action) {
        await clickAction(action.id);
        continue;
      }
    }

    if (stage === 'further_experience') {
      const action = await waitEnabledAction(['FURTHER_TAILOR_SKIP'], 15_000);
      if (action) {
        await clickAction(action.id);
        continue;
      }
    }

    if (stage === 'language_selection') {
      const action = await waitEnabledAction(['LANGUAGE_SELECT_EN'], 15_000);
      if (action) {
        await clickAction(action.id);
        continue;
      }
    }

    if (stage === 'import_gate_pending') {
      const action = await waitEnabledAction(['CONFIRM_IMPORT_PREFILL_YES'], 15_000);
      if (action) {
        await clickAction(action.id);
        continue;
      }
    }

    break;
  }

  expect(['review_final', 'generate_confirm', 'cover_letter_review']).toContain(await getStage());

  const alreadyDownload = await stagePanel.getByRole('button', { name: 'Pobierz CV' }).first().isVisible().catch(() => false);
  if (alreadyDownload) {
    return;
  }

  await clickAction('REQUEST_GENERATE_PDF');

  const downloadButton = stagePanel.getByRole('button', { name: 'Pobierz CV' }).first();
  const directDownload = page.getByTestId('download-pdf');

  const hasLabeledAction = await downloadButton.isVisible().catch(() => false);
  const hasDirect = await directDownload.isVisible().catch(() => false);

  expect(hasLabeledAction || hasDirect).toBeTruthy();
});
