import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SESSION_ID = process.env.E2E_STABLE_SESSION_ID || '566a4a2c-9558-4fe7-839d-a21416a64663';

test.describe('Session resume button behavior', () => {
  test('resumes provided session and keeps actionable PDF/Cover controls stable', async ({ page }) => {
    test.setTimeout(180_000);

    await page.addInitScript((sid) => {
      try {
        window.localStorage.setItem('cvgen:session_id', sid);
      } catch {
        // ignore
      }
    }, SESSION_ID);

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    const stagePanel = page.getByTestId('stage-panel');
    await expect(stagePanel).toBeVisible({ timeout: 60_000 });

    let stage = '';
    const waitStarted = Date.now();
    while (Date.now() - waitStarted < 90_000) {
      stage = ((await stagePanel.getAttribute('data-wizard-stage')) || '').trim();
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

    const getAvailableActions = async () => {
      return stagePanel
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
    };

    const waitForEnabledActions = async (timeoutMs = 45_000) => {
      const started = Date.now();
      while (Date.now() - started < timeoutMs) {
        const actions = await getAvailableActions();
        const enabled = actions.filter((a) => a.enabled).map((a) => a.id);
        if (enabled.length > 0) return { actions, enabled };
        await page.waitForTimeout(250);
      }
      const actions = await getAvailableActions();
      return { actions, enabled: actions.filter((a) => a.enabled).map((a) => a.id) };
    };

    for (let i = 0; i < 12; i++) {
      const currentStage = ((await stagePanel.getAttribute('data-wizard-stage')) || '').trim();
      const { actions, enabled } = await waitForEnabledActions();

      if (enabled.includes('REQUEST_GENERATE_PDF') || enabled.includes('COVER_LETTER_GENERATE')) {
        break;
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
      if ((currentStage === 'job_posting' || currentStage === 'job_posting_paste') && enabled.includes('JOB_OFFER_ANALYZE')) {
        await clickAction('JOB_OFFER_ANALYZE');
        continue;
      }
      if ((currentStage === 'job_posting' || currentStage === 'job_posting_paste') && enabled.includes('JOB_OFFER_INVALID_CONTINUE_NO_SUMMARY')) {
        await clickAction('JOB_OFFER_INVALID_CONTINUE_NO_SUMMARY');
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

    const requestGenerate = stagePanel.getByTestId('action-REQUEST_GENERATE_PDF');
    const coverGenerate = stagePanel.getByTestId('action-COVER_LETTER_GENERATE');

    const hasRequestGenerate = await requestGenerate.isVisible().catch(() => false);
    const hasCoverGenerate = await coverGenerate.isVisible().catch(() => false);

    if (!(hasRequestGenerate || hasCoverGenerate)) {
      const finalStage = ((await stagePanel.getAttribute('data-wizard-stage')) || '').trim();
      const actions = await getAvailableActions();
      throw new Error(
        `Did not reach PDF/Cover controls. finalStage='${finalStage}', actions=${JSON.stringify(actions)}`
      );
    }

    if (hasRequestGenerate) {
      await expect(requestGenerate).toBeEnabled();

      const reqPromise = page.waitForRequest(
        (req) =>
          req.url().includes('/api/process-cv') &&
          req.method() === 'POST' &&
          String(req.postData() || '').includes('REQUEST_GENERATE_PDF'),
        { timeout: 60_000 }
      );

      await requestGenerate.click();
      await reqPromise;

      const directDownload = page.getByTestId('download-pdf');
      const hasDirectDownload = await directDownload.isVisible().catch(() => false);

      const sameActionAsDownload = stagePanel.getByRole('button', { name: 'Pobierz PDF' });
      const hasActionDownloadLabel = await sameActionAsDownload.first().isVisible().catch(() => false);

      expect(hasDirectDownload || hasActionDownloadLabel).toBeTruthy();
    }

    if (hasCoverGenerate) {
      await expect(coverGenerate).toBeEnabled();

      const reqPromise = page.waitForRequest(
        (req) =>
          req.url().includes('/api/process-cv') &&
          req.method() === 'POST' &&
          String(req.postData() || '').includes('COVER_LETTER_GENERATE'),
        { timeout: 60_000 }
      );

      await coverGenerate.click();
      await reqPromise;

      await expect(stagePanel).toBeVisible();
    }
  });
});
