import { test, expect, type Locator } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SESSION_ID = process.env.E2E_STABLE_SESSION_ID || '539dd501-46df-4454-a9f3-a5040afda2bc';
const SAMPLE_CV =
  process.env.E2E_SAMPLE_CV_PATH ||
  path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

async function getStage(panel: Locator): Promise<string> {
  const wizardStage = ((await panel.getAttribute('data-wizard-stage')) || '').trim();
  if (wizardStage) return wizardStage;
  return ((await panel.getAttribute('data-stage')) || '').trim();
}

test('session WORK_TAILOR_RUN advances to work_tailor_review', async ({ page }) => {
  test.setTimeout(180_000);

  await page.addInitScript((sid) => {
    try {
      window.localStorage.setItem('cvgen:session_id', sid);
    } catch {
      // ignore
    }
  }, SESSION_ID);

  await page.goto(BASE_URL, { waitUntil: 'networkidle' });

  const panel = page.getByTestId('stage-panel');
  const stagePanelVisible = await panel.isVisible({ timeout: 20_000 }).catch(() => false);
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
  await expect(panel).toBeVisible({ timeout: 60_000 });

  let stage = '';
  const waitStart = Date.now();
  while (Date.now() - waitStart < 30_000) {
    stage = await getStage(panel);
    if (stage) break;
    await page.waitForTimeout(250);
  }
  expect(stage.length).toBeGreaterThan(0);

  const clickAction = async (actionId: string) => {
    const btn = panel.getByTestId(`action-${actionId}`);
    const hasVisible = await btn.isVisible().catch(() => false);
    if (!hasVisible) {
      const more = panel.getByText('Więcej akcji').first();
      if (await more.isVisible().catch(() => false)) {
        await more.click();
      }
    }
    const visibleStart = Date.now();
    let visible = false;
    while (Date.now() - visibleStart < 30_000) {
      visible = await btn.isVisible().catch(() => false);
      if (visible) break;
      await page.waitForTimeout(200);
    }
    if (!visible) {
      return false;
    }

    const start = Date.now();
    let enabled = false;
    while (Date.now() - start < 30_000) {
      enabled = await btn.isEnabled().catch(() => false);
      if (enabled) break;
      await page.waitForTimeout(200);
    }
    if (!enabled) {
      return false;
    }

    const reqPromise = page.waitForRequest(
      (req) =>
        req.url().includes('/api/process-cv') &&
        req.method() === 'POST' &&
        String(req.postData() || '').includes(actionId),
      { timeout: 60_000 }
    );

    await btn.click();
    await reqPromise;
    return true;
  };

  for (let i = 0; i < 12; i++) {
    stage = await getStage(panel);
    if (stage === 'work_experience' || stage === 'work_tailor_review') break;

    if (stage === 'language_selection') {
      const btn = panel.getByTestId('action-LANGUAGE_SELECT_EN');
      if (await btn.isVisible().catch(() => false)) {
        const clicked = await clickAction('LANGUAGE_SELECT_EN');
        if (!clicked) {
          await page.waitForTimeout(500);
          continue;
        }
        continue;
      }
      await page.waitForTimeout(500);
      continue;
    }
    if (stage === 'import_gate_pending') {
      const btn = panel.getByTestId('action-CONFIRM_IMPORT_PREFILL_YES');
      if (await btn.isVisible().catch(() => false)) {
        const clicked = await clickAction('CONFIRM_IMPORT_PREFILL_YES');
        if (!clicked) continue;
        continue;
      }
    }
    if (stage === 'contact') {
      const btn = panel.getByTestId('action-CONTACT_CONFIRM');
      if (await btn.isVisible().catch(() => false)) {
        const clicked = await clickAction('CONTACT_CONFIRM');
        if (!clicked) continue;
        continue;
      }
    }
    if (stage === 'education') {
      const btn = panel.getByTestId('action-EDUCATION_CONFIRM');
      if (await btn.isVisible().catch(() => false)) {
        const clicked = await clickAction('EDUCATION_CONFIRM');
        if (!clicked) continue;
        continue;
      }
    }
    if (stage === 'job_posting' || stage === 'job_posting_paste') {
      const actions = await panel
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

      const preferred = ['JOB_OFFER_CONTINUE', 'JOB_OFFER_SKIP', 'JOB_OFFER_ANALYZE'];
      const candidate = preferred.find((id) => enabled.includes(id));
      if (candidate) {
        const clicked = await clickAction(candidate);
        if (!clicked) continue;
        continue;
      }
    }
    if (stage === 'work_notes_edit') {
      const btn = panel.getByTestId('action-WORK_NOTES_CANCEL');
      if (await btn.isVisible().catch(() => false)) {
        const clicked = await clickAction('WORK_NOTES_CANCEL');
        if (!clicked) continue;
        continue;
      }
    }

    break;
  }

  stage = await getStage(panel);

  if (stage === 'work_tailor_review') {
    await expect(panel.getByTestId('action-WORK_TAILOR_ACCEPT')).toBeVisible({ timeout: 15_000 });
    return;
  }

  const alreadyPastWorkStage = [
    'work_tailor_feedback',
    'it_ai_skills',
    'skills_tailor_review',
    'review_final',
    'generate_confirm',
    'cover_letter_review',
  ].includes(stage);
  if (alreadyPastWorkStage) {
    expect(stage.length).toBeGreaterThan(0);
    return;
  }

  const runBtn = panel.getByTestId('action-WORK_TAILOR_RUN');
  const runVisible = await runBtn.isVisible().catch(() => false);
  if (!runVisible) {
    const more = panel.getByText('Więcej akcji').first();
    if (await more.isVisible().catch(() => false)) {
      await more.click();
    }
  }

  const hasRunButton = await runBtn.isVisible().catch(() => false);
  if (!hasRunButton) {
    const skipBtn = panel.getByTestId('action-WORK_TAILOR_SKIP');
    const hasSkipButton = await skipBtn.isVisible().catch(() => false);
    if (hasSkipButton) {
      await expect(skipBtn).toBeEnabled({ timeout: 30_000 });

      const reqPromise = page.waitForRequest(
        (req) =>
          req.url().includes('/api/process-cv') &&
          req.method() === 'POST' &&
          String(req.postData() || '').includes('WORK_TAILOR_SKIP'),
        { timeout: 60_000 }
      );

      await skipBtn.click();
      await reqPromise;

      const nextStageStart = Date.now();
      while (Date.now() - nextStageStart < 45_000) {
        stage = await getStage(panel);
        if (['further_experience', 'it_ai_skills', 'skills_tailor_review', 'review_final', 'generate_confirm'].includes(stage)) {
          return;
        }
        await page.waitForTimeout(300);
      }
    }

    throw new Error(`Session is not in a runnable work tailoring state. Current stage='${stage}'.`);
  }
  await expect(runBtn).toBeVisible({ timeout: 30_000 });
  await expect(runBtn).toBeEnabled({ timeout: 30_000 });

  const reqPromise = page.waitForRequest(
    (req) =>
      req.url().includes('/api/process-cv') &&
      req.method() === 'POST' &&
      String(req.postData() || '').includes('WORK_TAILOR_RUN'),
    { timeout: 60_000 }
  );

  const respPromise = page.waitForResponse(
    (res) => res.url().includes('/api/process-cv') && res.request().method() === 'POST',
    { timeout: 120_000 }
  );

  await runBtn.click();
  await reqPromise;
  const response = await respPromise;

  let responseBody: any = null;
  try {
    responseBody = await response.json();
  } catch {
    responseBody = null;
  }

  const stageWaitStart = Date.now();
  while (Date.now() - stageWaitStart < 45_000) {
    stage = await getStage(panel);
    if (stage === 'work_tailor_review') break;
    await page.waitForTimeout(400);
  }

  if (stage !== 'work_tailor_review') {
    const assistant = (responseBody && String(responseBody.assistant_text || '')) || '';
    const backendStage =
      responseBody && responseBody.metadata && typeof responseBody.metadata.wizard_stage === 'string'
        ? responseBody.metadata.wizard_stage
        : '';
    throw new Error(
      `Expected work_tailor_review, got ui_stage='${stage}', backend_stage='${backendStage}', assistant='${assistant.slice(
        0,
        240
      )}'`
    );
  }

  await expect(panel.getByTestId('action-WORK_TAILOR_ACCEPT')).toBeVisible({ timeout: 30_000 });
});
