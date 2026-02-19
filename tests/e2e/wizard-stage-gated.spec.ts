import { test, expect } from '@playwright/test';
import path from 'path';
import {
  clickAction,
  enforceNoStuck,
  getWizardStage,
  waitForStageOneOf,
  waitForStagePanel,
} from './helpers/wizard-stage-runner';
import { writeStageProgressArtifact, type StageProgressEntry } from './helpers/wizard-artifacts';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV =
  process.env.E2E_SAMPLE_CV_PATH ||
  path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');
const JOB_URL = process.env.E2E_JOB_URL || 'https://lonza.talent-community.com/app/project/61784';
const JOB_TEXT =
  process.env.E2E_JOB_TEXT ||
  [
    'Operational Excellence Manager role in regulated manufacturing.',
    'Responsibilities include lean deployment, KPI improvement, and cross-functional leadership.',
    'Requirements include process optimization, change management, and audit-ready quality systems.',
  ].join(' ');

const MAX_STEPS = Number(process.env.E2E_MAX_STEPS || '20');
const MAX_SAME_STAGE_VISITS = Number(process.env.E2E_MAX_SAME_STAGE_VISITS || '5');

test.describe('Wizard stage-gated E2E (normal flow)', () => {
  test('fails fast and follows deterministic stage flow', async ({ page }, testInfo) => {
    test.setTimeout(180_000);

    const progress: StageProgressEntry[] = [];
    let sessionId = '';
    let importRefreshAttempts = 0;
    let importGateEnteredAt: number | null = null;

    page.on('request', (req) => {
      if (!req.url().includes('/api/process-cv') || req.method() !== 'POST') return;
      const post = String(req.postData() || '');
      try {
        const body = JSON.parse(post);
        if (!sessionId && typeof body?.session_id === 'string' && body.session_id.trim()) {
          sessionId = body.session_id.trim();
        }
      } catch {
        // ignore malformed payload in telemetry hook
      }
    });

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    const fastPath = page.getByRole('checkbox', { name: /Fast path:/i });
    if (await fastPath.isVisible().catch(() => false)) {
      if (await fastPath.isChecked()) await fastPath.uncheck();
    }

    await page.getByTestId('job-url-input').fill(JOB_URL);
    await page.getByTestId('job-text-input').fill(JOB_TEXT);
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);

    const useLoadedCv = page.getByTestId('use-loaded-cv');
    await expect(useLoadedCv).toBeVisible({ timeout: 30_000 });
    await useLoadedCv.click();
    await waitForStagePanel(page, 60_000);

    const stageAtStart = await getWizardStage(page);
    if (stageAtStart === 'import_gate_pending') {
      const panel = page.getByTestId('stage-panel');
      const importBtn = panel.getByRole('button', { name: /Import DOCX prefill/i });
      const refreshBtn = panel.locator('button:has-text("Odśwież"), button:has-text("Refresh")').first();
      const refreshText = panel.getByText(/Odśwież|Refresh/i).first();

      let imported = false;
      for (let i = 0; i < 8; i++) {
        const canImport = await importBtn
          .isVisible()
          .then(async (visible) => visible && (await importBtn.isEnabled().catch(() => false)))
          .catch(() => false);

        if (canImport) {
          await importBtn.click();
          imported = true;
          break;
        }

        if (await refreshBtn.isVisible().catch(() => false)) {
          await refreshBtn.click({ timeout: 10_000 }).catch(async () => {
            await refreshBtn.click({ force: true, timeout: 10_000 });
          });
        } else if (await refreshText.isVisible().catch(() => false)) {
          await refreshText.click({ timeout: 10_000 }).catch(async () => {
            await refreshText.click({ force: true, timeout: 10_000 });
          });
        }

        await page.waitForTimeout(1000);
      }

      if (!imported) {
        throw new Error('Import gate blocked: `Import DOCX prefill` did not become enabled after refresh retries');
      }
    }

    const stageGuard = { lastStage: '', sameStageCount: 0 };

    for (let step = 1; step <= MAX_STEPS; step++) {
      const stageBefore = await getWizardStage(page);

      if (stageBefore === 'import_gate_pending') {
        if (!importGateEnteredAt) importGateEnteredAt = Date.now();
        if (Date.now() - importGateEnteredAt > 120_000) {
          throw new Error('Import gate blocked: stage remained import_gate_pending for over 120s');
        }
        if (importRefreshAttempts >= 5) {
          throw new Error('Import gate blocked: prefill did not unlock after 5 deterministic refresh attempts');
        }
      } else {
        importGateEnteredAt = null;
      }

      if (stageBefore === 'import_gate_pending' && importRefreshAttempts < 5) {
        const importBtn = page.getByTestId('stage-panel').getByRole('button', { name: /Import DOCX prefill/i });
        const canImport = await importBtn
          .isVisible()
          .then(async (visible) => visible && (await importBtn.isEnabled().catch(() => false)))
          .catch(() => false);

        if (canImport) {
          const started = Date.now();
          await importBtn.click();

          const stageAfter = await waitForStageOneOf(
            page,
            [
              'import_gate_pending',
              'contact',
              'education',
              'job_posting',
              'job_posting_paste',
              'work_notes_edit',
              'work_experience',
              'further_experience',
              'it_ai_skills',
              'skills_tailor_review',
              'review_final',
              'generate_confirm',
              'cover_letter_review',
            ],
            60_000
          );

          progress.push({
            step,
            stageBefore,
            actionId: 'IMPORT_DOCX_PREFILL_UI',
            stageAfter,
            elapsedMs: Date.now() - started,
          });
          continue;
        }

        const panel = page.getByTestId('stage-panel');
        const refreshBtn = panel.locator('button:has-text("Odśwież"), button:has-text("Refresh")').first();
        const refreshText = panel.getByText(/Odśwież|Refresh/i).first();
        const canRefresh =
          (await refreshBtn.isVisible().catch(() => false)) ||
          (await refreshText.isVisible().catch(() => false));

        if (canRefresh) {
          const started = Date.now();
          if (await refreshBtn.isVisible().catch(() => false)) {
            await refreshBtn.click({ timeout: 10_000 }).catch(async () => {
              await refreshBtn.click({ force: true, timeout: 10_000 });
            });
          } else {
            await refreshText.click({ timeout: 10_000 }).catch(async () => {
              await refreshText.click({ force: true, timeout: 10_000 });
            });
          }
          await page.waitForTimeout(300);

          const stageAfter = await waitForStageOneOf(
            page,
            [
              'import_gate_pending',
              'contact',
              'education',
              'job_posting',
              'job_posting_paste',
              'work_notes_edit',
              'work_experience',
              'further_experience',
              'it_ai_skills',
              'skills_tailor_review',
              'review_final',
              'generate_confirm',
              'cover_letter_review',
            ],
            60_000
          );

          progress.push({
            step,
            stageBefore,
            actionId: 'REFRESH_IMPORT_GATE',
            stageAfter,
            elapsedMs: Date.now() - started,
          });
          importRefreshAttempts += 1;
          continue;
        }
      }

      const actions = await page
        .getByTestId('stage-panel')
        .locator('[data-testid^="action-"]')
        .evaluateAll((nodes) =>
          nodes
            .map((n) => {
              const element = n as HTMLButtonElement;
              const raw = (element.dataset.testid || '').replace('action-', '');
              return { id: raw, enabled: !element.disabled };
            })
            .filter((x) => Boolean(x.id))
        );
      const actionIds = actions.map((a) => a.id);
      const enabledActionIds = actions.filter((a) => a.enabled).map((a) => a.id);

      let actionId: string | null = null;
      if (stageBefore === 'language_selection') {
        if (enabledActionIds.includes('LANGUAGE_SELECT_EN')) actionId = 'LANGUAGE_SELECT_EN';
      } else if (stageBefore === 'contact') {
        if (enabledActionIds.includes('CONTACT_CONFIRM')) actionId = 'CONTACT_CONFIRM';
      } else if (stageBefore === 'education') {
        if (enabledActionIds.includes('EDUCATION_CONFIRM')) actionId = 'EDUCATION_CONFIRM';
      } else if (stageBefore === 'job_posting' || stageBefore === 'job_posting_paste') {
        if (enabledActionIds.includes('JOB_OFFER_CONTINUE')) actionId = 'JOB_OFFER_CONTINUE';
      } else if (stageBefore === 'work_notes_edit') {
        if (enabledActionIds.includes('WORK_NOTES_CANCEL')) actionId = 'WORK_NOTES_CANCEL';
      } else if (stageBefore === 'work_experience') {
        if (enabledActionIds.includes('WORK_TAILOR_SKIP')) actionId = 'WORK_TAILOR_SKIP';
      } else if (stageBefore === 'further_experience') {
        if (enabledActionIds.includes('FURTHER_TAILOR_SKIP')) actionId = 'FURTHER_TAILOR_SKIP';
      } else if (stageBefore === 'it_ai_skills') {
        if (enabledActionIds.includes('SKILLS_TAILOR_RUN')) actionId = 'SKILLS_TAILOR_RUN';
      } else if (stageBefore === 'skills_tailor_review') {
        if (enabledActionIds.includes('SKILLS_TAILOR_ACCEPT')) actionId = 'SKILLS_TAILOR_ACCEPT';
      } else if (stageBefore === 'review_final' || stageBefore === 'generate_confirm') {
        if (enabledActionIds.includes('REQUEST_GENERATE_PDF')) actionId = 'REQUEST_GENERATE_PDF';
        else if (enabledActionIds.includes('DOWNLOAD_PDF')) actionId = 'DOWNLOAD_PDF';
      } else {
        if (enabledActionIds.includes('REQUEST_GENERATE_PDF')) actionId = 'REQUEST_GENERATE_PDF';
        else if (enabledActionIds.includes('DOWNLOAD_PDF')) actionId = 'DOWNLOAD_PDF';
      }

      if (!actionId) {
        if (actionIds.length > 0 && enabledActionIds.length === 0) {
          await page.waitForTimeout(400);
          if (stageBefore !== 'import_gate_pending') {
            await enforceNoStuck(page, stageGuard, MAX_SAME_STAGE_VISITS);
          }
          continue;
        }
        throw new Error(`No deterministic normal-flow action available at stage='${stageBefore}'`);
      }

      const started = Date.now();
      await clickAction(page, actionId, 45_000);

      const expectedStagesByAction: Record<string, string[]> = {
        LANGUAGE_SELECT_EN: ['import_gate_pending', 'contact', 'education', 'job_posting', 'job_posting_paste'],
        CONFIRM_IMPORT_PREFILL_YES: ['contact', 'education', 'job_posting', 'job_posting_paste'],
        CONFIRM_IMPORT_PREFILL_NO: ['contact', 'education', 'job_posting', 'job_posting_paste'],
        CONTACT_CONFIRM: ['education', 'job_posting', 'job_posting_paste', 'work_notes_edit', 'work_experience'],
        EDUCATION_CONFIRM: ['job_posting', 'job_posting_paste', 'work_notes_edit', 'work_experience'],
        JOB_OFFER_CONTINUE: ['work_notes_edit', 'work_experience'],
        WORK_NOTES_CANCEL: ['work_experience', 'further_experience', 'it_ai_skills'],
        WORK_TAILOR_SKIP: ['further_experience', 'it_ai_skills', 'skills_tailor_review', 'review_final'],
        FURTHER_TAILOR_SKIP: ['it_ai_skills', 'skills_tailor_review', 'review_final'],
        SKILLS_TAILOR_RUN: ['skills_tailor_review', 'review_final'],
        SKILLS_TAILOR_ACCEPT: ['review_final', 'generate_confirm'],
        REQUEST_GENERATE_PDF: ['generate_confirm', 'review_final', 'cover_letter_review'],
        DOWNLOAD_PDF: ['generate_confirm', 'review_final', 'cover_letter_review'],
      };
      const expectedStages = expectedStagesByAction[actionId] || [
        'language_selection',
        'import_gate_pending',
        'contact',
        'education',
        'job_posting',
        'job_posting_paste',
        'work_notes_edit',
        'work_experience',
        'further_experience',
        'it_ai_skills',
        'skills_tailor_review',
        'review_final',
        'generate_confirm',
        'cover_letter_review',
      ];

      const stageAfter = await waitForStageOneOf(page, expectedStages, 60_000);

      progress.push({
        step,
        stageBefore,
        actionId,
        stageAfter,
        elapsedMs: Date.now() - started,
      });
      await enforceNoStuck(page, stageGuard, MAX_SAME_STAGE_VISITS);

      if (actionId === 'REQUEST_GENERATE_PDF' || actionId === 'DOWNLOAD_PDF') {
        const downloadBtn = page.getByTestId('download-pdf');
        if (await downloadBtn.isVisible().catch(() => false)) {
          await writeStageProgressArtifact(testInfo, sessionId || 'unknown', progress);
          return;
        }
      }
    }

    await writeStageProgressArtifact(testInfo, sessionId || 'unknown', progress);
    throw new Error(`Max steps exceeded (${MAX_STEPS}) without reaching PDF-ready state`);
  });
});
