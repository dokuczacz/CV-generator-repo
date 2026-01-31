import { test, expect, type Page, type Route } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

const INPUT_DOCX = path.join(
  __dirname,
  '../../archive/wzory/Lebenslauf_Mariusz_Horodecki_CH.docx'
);

const JOB_URL = 'https://www.jobs.ch/en/vacancies/detail/faa45fb1-e562-43b3-a4dd-be9717ed2074/';

const TAILORING_NOTES = `ok in GL i created from scratches construction company capable to deliver 30-40k eur jobs, also for public sector,

in expondo: technically solved issue with 3 years old company headache - good seller - bad quality, claims reduced by 70%, improved multiple workflows, eg. reduction number of steps in warehouse by half by rearranging the locations, after 3 months got rid of old department leftovers (no high-level overdue actions), introduced work classification --> simple job, agency staff, technical work --> technician

in sumitomo, basically from scraches build quality team taking care of product being actually send to oem production lines, capable to deliver right quality, IATF passed at first try, passed many customer audits, build team from local people, hand over process of position planned and started 6 months ahead, this refer to job positon in moldova quality manager

Summitomo process improvement:
- around 60% of time in production plants in random locations,
- fire-fighter - i was being sent to critical status plants to put down fires, usually customer-high-level concerns (eg. lack of output, very bad quality),
- managed international project of shop floor standardisation and KAIZEN implementation, highest level expert in concern-wide, eg. agreeing which of japanese shareholders applies to our business branch (technically), agreeing concern audits schedule, being main contact person, advicing implementation ideas,
- leaded very company wide improvements, training systems, production managment

this is refering to Sumitomo Electric Bordnetze SE — Global Process Improvement Specialist (2011-03 – 2016-07)`;

type ConfirmedFlags = {
  contact_confirmed: boolean;
  education_confirmed: boolean;
};

type MockState = {
  session_id: string | null;
  language: 'en' | null;
  docx_base64_len: number;
  job_posting_url: string | null;
  job_reference: Record<string, any> | null;
  work_tailoring_notes: string;
  confirmed_flags: ConfirmedFlags;
  cv_data: {
    full_name: string;
    email: string;
    phone: string;
    education: Array<{ institution: string; title: string; date_range: string }>;
    work_experience: Array<{ employer: string; title: string; date_range: string; bullets: string[] }>;
    further_experience: Array<{ title: string; bullets: string[] }>;
    it_ai_skills: string[];
  };
  counters: {
    job_offer_analyze: number;
    work_tailor_run: number;
    skills_tailor_run: number;
    generate_pdf: number;
  };
};

function makeBase64StubPdf(): string {
  // Minimal, non-empty base64 (UI only uses it for download).
  return Buffer.from('%PDF-1.4\n%mock\n', 'utf-8').toString('base64');
}

function makeDefaultState(): MockState {
  return {
    session_id: null,
    language: null,
    docx_base64_len: 0,
    job_posting_url: null,
    job_reference: null,
    work_tailoring_notes: '',
    confirmed_flags: {
      contact_confirmed: false,
      education_confirmed: false,
    },
    cv_data: {
      full_name: 'Mariusz Horodecki',
      email: 'mariusz@example.com',
      phone: '+41 00 000 0000',
      education: [
        {
          institution: 'Example University',
          title: 'MSc Engineering',
          date_range: '2008 – 2010',
        },
      ],
      work_experience: [
        {
          employer: 'Sumitomo Electric Bordnetze SE',
          title: 'Global Process Improvement Specialist',
          date_range: '2011-03 – 2016-07',
          bullets: ['(un-tailored placeholder)'],
        },
      ],
      further_experience: [],
      it_ai_skills: ['Lean', 'Kaizen', 'Process standardization', 'Audit readiness'],
    },
    counters: {
      job_offer_analyze: 0,
      work_tailor_run: 0,
      skills_tailor_run: 0,
      generate_pdf: 0,
    },
  };
}

function createProcessCvSoTMock() {
  const state = makeDefaultState();

  const respond = async (route: Route, body: any, status = 200) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  };

  const setup = async (page: Page) => {
    await page.route('**/api/process-cv', async (route) => {
      const raw = route.request().postData() || '';
      let req: any = {};
      try {
        req = JSON.parse(raw || '{}');
      } catch {
        await respond(route, { success: false, error: 'invalid_json' }, 400);
        return;
      }

      const isFirstTurn = !req.session_id;
      const isUserMessage = typeof req.message === 'string' && req.message.trim().length > 0;
      const hasDocx = typeof req.docx_base64 === 'string' && req.docx_base64.length > 1000;

      if (isFirstTurn && isUserMessage) {
        if (!hasDocx) {
          await respond(
            route,
            {
              success: false,
              error: 'missing_docx_base64',
            },
            400
          );
          return;
        }

        state.session_id = 'session-mocked-001';
        state.docx_base64_len = req.docx_base64.length;
        state.job_posting_url = typeof req.job_posting_url === 'string' ? req.job_posting_url : null;

        await respond(route, {
          success: true,
          response: 'Please confirm whether to import the DOCX prefill.',
          session_id: state.session_id,
          job_posting_url: state.job_posting_url || '',
          ui_action: {
            kind: 'review_form',
            stage: 'LANGUAGE_SELECTION',
            title: 'Language Selection',
            text: 'Choose output language.',
            fields: [],
            actions: [
              { id: 'LANGUAGE_SELECT_EN', label: 'English', style: 'primary' },
            ],
            disable_free_text: true,
          },
        });
        return;
      }

      // All actions require a session.
      if (!req.session_id || req.session_id !== state.session_id) {
        await respond(
          route,
          {
            success: false,
            error: 'invalid_or_missing_session',
          },
          409
        );
        return;
      }

      const actionId = req?.user_action?.id;
      const actionPayload = req?.user_action?.payload || {};

      switch (actionId) {
        case 'LANGUAGE_SELECT_EN': {
          state.language = 'en';
          await respond(route, {
            success: true,
            response: 'Great — English selected. Import the DOCX prefill?',
            session_id: state.session_id,
            job_posting_url: state.job_posting_url || '',
            ui_action: {
              kind: 'review_form',
              stage: 'IMPORT_PREFILL',
              title: 'Import DOCX data?',
              text: 'Please confirm whether to import the DOCX prefill.',
              fields: [
                { key: 'docx_stats', label: 'DOCX received', value: `base64_len=${state.docx_base64_len}` },
              ],
              actions: [
                { id: 'IMPORT_PREFILL_YES', label: 'Import DOCX prefill', style: 'primary' },
                { id: 'IMPORT_PREFILL_NO', label: 'Skip import', style: 'secondary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'IMPORT_PREFILL_YES': {
          // In real backend this merges docx_prefill_unconfirmed into cv_data.
          // Here we assert SoT: canonical cv_data is now populated (we use stable test values).
          await respond(route, {
            success: true,
            response: 'Imported DOCX prefill. Review your contact details below.',
            session_id: state.session_id,
            job_posting_url: state.job_posting_url || '',
            ui_action: {
              kind: 'review_form',
              stage: 'CONTACT',
              title: 'Stage 1/6 — Contact',
              text: 'Review your contact details below.',
              fields: [
                { key: 'full_name', label: 'Full name', value: state.cv_data.full_name },
                { key: 'email', label: 'Email', value: state.cv_data.email },
                { key: 'phone', label: 'Phone', value: state.cv_data.phone },
              ],
              actions: [{ id: 'CONTACT_CONFIRM', label: 'Confirm & lock', style: 'primary' }],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'IMPORT_PREFILL_NO': {
          await respond(route, {
            success: true,
            response: 'Skipped import. Review your contact details below.',
            session_id: state.session_id,
            job_posting_url: state.job_posting_url || '',
            ui_action: {
              kind: 'review_form',
              stage: 'CONTACT',
              title: 'Stage 1/6 — Contact',
              text: 'Review your contact details below.',
              fields: [
                { key: 'full_name', label: 'Full name', value: state.cv_data.full_name },
                { key: 'email', label: 'Email', value: state.cv_data.email },
              ],
              actions: [{ id: 'CONTACT_CONFIRM', label: 'Confirm & lock', style: 'primary' }],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'CONTACT_CONFIRM': {
          state.confirmed_flags.contact_confirmed = true;
          await respond(route, {
            success: true,
            response: 'Review your education below.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'EDUCATION',
              title: 'Stage 2/6 — Education',
              text: 'Review your education below.',
              fields: state.cv_data.education.map((e, idx) => ({
                key: `education_${idx}`,
                label: `Education ${idx + 1}`,
                value: `${e.date_range} — ${e.institution} — ${e.title}`,
              })),
              actions: [{ id: 'EDUCATION_CONFIRM', label: 'Confirm & lock', style: 'primary' }],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'EDUCATION_CONFIRM': {
          state.confirmed_flags.education_confirmed = true;
          await respond(route, {
            success: true,
            response: 'Optionally add a job offer for tailoring (or skip).',
            session_id: state.session_id,
            job_posting_url: state.job_posting_url || '',
            ui_action: {
              kind: 'review_form',
              stage: 'JOB_POSTING',
              title: 'Stage 3/6 — Job offer',
              text: 'Analyze job posting URL to create job reference (stored once).',
              fields: [
                { key: 'job_posting_url', label: 'Job offer URL', value: state.job_posting_url || '' },
              ],
              actions: [
                { id: 'JOB_OFFER_ANALYZE', label: 'Analyze', style: 'primary' },
                { id: 'JOB_OFFER_SKIP', label: 'Skip', style: 'secondary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'JOB_OFFER_ANALYZE': {
          if (state.job_reference) {
            await respond(route, { success: false, error: 'job_reference_already_set' }, 400);
            return;
          }

          state.counters.job_offer_analyze += 1;

          state.job_reference = {
            title: 'Quality / Process Improvement Manager',
            company: 'N/A',
            location: 'CH',
            keywords: ['IATF 16949', 'audits', 'process improvement', 'quality management'],
          };

          await respond(route, {
            success: true,
            response: 'Job offer analyzed. Moving to work experience.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'WORK_EXPERIENCE',
              title: 'Stage 4/6 — Work experience',
              text: 'Review your work experience roles below.',
              fields: [
                { key: 'job_reference', label: 'Job summary', value: JSON.stringify(state.job_reference) },
                {
                  key: 'skills_preview',
                  label: 'Your skills (FÄHIGKEITEN & KOMPETENZEN)',
                  value: state.cv_data.it_ai_skills.join(', '),
                },
              ],
              actions: [
                { id: 'WORK_NOTES_EDIT', label: 'Add tailoring notes', style: 'secondary' },
                { id: 'JOB_OFFER_ANALYZE', label: 'Re-analyze job offer', style: 'secondary' },
                { id: 'WORK_TAILOR_RUN', label: 'Run tailoring', style: 'primary' },
                { id: 'WORK_TAILOR_SKIP', label: 'Skip', style: 'secondary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'JOB_OFFER_SKIP': {
          await respond(route, {
            success: true,
            response: 'Skipped job offer. Moving to work experience (no job context).',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'WORK_EXPERIENCE',
              title: 'Stage 4/6 — Work experience',
              text: 'No job reference available. Tailoring runs should fail closed.',
              fields: [],
              actions: [
                { id: 'WORK_NOTES_EDIT', label: 'Add tailoring notes', style: 'secondary' },
                { id: 'WORK_TAILOR_RUN', label: 'Run tailoring', style: 'primary' },
                { id: 'WORK_TAILOR_SKIP', label: 'Skip', style: 'secondary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'WORK_NOTES_EDIT': {
          await respond(route, {
            success: true,
            response: 'Add tailoring notes for work experience.',
            session_id: state.session_id,
            ui_action: {
              kind: 'edit_form',
              stage: 'WORK_NOTES_EDIT',
              title: 'Work tailoring notes',
              text: 'Provide achievements/metrics to emphasize (SoT: meta.work_tailoring_notes).',
              fields: [
                {
                  key: 'work_tailoring_notes',
                  label: 'Tailoring notes',
                  value: state.work_tailoring_notes,
                  type: 'textarea',
                },
              ],
              actions: [
                { id: 'WORK_NOTES_SAVE', label: 'Save notes', style: 'primary' },
                { id: 'WORK_NOTES_CANCEL', label: 'Cancel', style: 'secondary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'WORK_NOTES_SAVE': {
          const notes = String(actionPayload.work_tailoring_notes || '').trim();
          state.work_tailoring_notes = notes;
          await respond(route, {
            success: true,
            response: 'Saved notes. Back to work experience.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'WORK_EXPERIENCE',
              title: 'Stage 4/6 — Work experience',
              text: 'Now run work tailoring (requires job_reference).',
              fields: [
                { key: 'work_notes', label: 'Work tailoring context', value: state.work_tailoring_notes },
              ],
              actions: [
                { id: 'WORK_TAILOR_RUN', label: 'Run tailoring', style: 'primary' },
                { id: 'WORK_TAILOR_SKIP', label: 'Skip', style: 'secondary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'WORK_NOTES_CANCEL': {
          await respond(route, {
            success: true,
            response: 'Canceled.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'WORK_EXPERIENCE',
              title: 'Stage 4/6 — Work experience',
              text: 'Review your work experience roles below.',
              fields: [],
              actions: [
                { id: 'WORK_NOTES_EDIT', label: 'Add tailoring notes', style: 'secondary' },
                { id: 'WORK_TAILOR_RUN', label: 'Run tailoring', style: 'primary' },
                { id: 'WORK_TAILOR_SKIP', label: 'Skip', style: 'secondary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'WORK_TAILOR_RUN': {
          state.counters.work_tailor_run += 1;
          if (!state.job_reference) {
            await respond(
              route,
              {
                success: false,
                response: '',
                pdf_base64: '',
                session_id: null,
                trace_id: null,
                stage: null,
                run_summary: null,
                turn_trace: null,
                ui_action: null,
                job_posting_url: state.job_posting_url || '',
                job_posting_text: '',
              },
              500
            );
            return;
          }

          state.cv_data.work_experience[0].bullets = [
            'Reduced claims by 70% by stabilizing quality processes and workflows.',
            'Passed IATF audits at first attempt; led customer audit readiness.',
            'Delivered KAIZEN / shop-floor standardization across multiple plants.',
          ];

          await respond(route, {
            success: true,
            response: 'Work tailoring complete. Moving to technical projects.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'FURTHER_EXPERIENCE',
              title: 'Stage 5a/6 — Technical projects',
              text: 'Tailor technical projects to the job offer (recommended), or skip.',
              fields: [
                {
                  key: 'projects_preview',
                  label: 'Technical projects (0 total)',
                  value: '(no technical projects detected in CV)',
                },
                {
                  key: 'work_notes',
                  label: 'Work tailoring context',
                  value: state.work_tailoring_notes || '(none)',
                },
              ],
              actions: [
                { id: 'FURTHER_TAILOR_SKIP', label: 'Continue', style: 'primary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'WORK_TAILOR_SKIP': {
          await respond(route, {
            success: true,
            response: 'Skipped work tailoring. Moving to technical projects.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'FURTHER_EXPERIENCE',
              title: 'Stage 5a/6 — Technical projects',
              text: 'Tailor your technical projects to the job offer (recommended), or skip.',
              fields: [],
              actions: [{ id: 'FURTHER_TAILOR_SKIP', label: 'Continue', style: 'primary' }],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'FURTHER_TAILOR_SKIP': {
          await respond(route, {
            success: true,
            response: 'Moving to IT/AI skills.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'IT_AI_SKILLS',
              title: 'Stage 5b/6 — Skills (FÄHIGKEITEN & KOMPETENZEN)',
              text: 'Rank your skills by job relevance (recommended), or skip.',
              fields: [
                {
                  key: 'skills_preview',
                  label: `Your skills (FÄHIGKEITEN & KOMPETENZEN) (${state.cv_data.it_ai_skills.length} total)`,
                  value: state.cv_data.it_ai_skills.join(', '),
                },
              ],
              actions: [
                { id: 'SKILLS_TAILOR_RUN', label: 'Generate ranked skills', style: 'secondary' },
                { id: 'SKILLS_TAILOR_SKIP', label: 'Continue', style: 'primary' },
              ],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'SKILLS_TAILOR_RUN': {
          state.counters.skills_tailor_run += 1;
          if (!state.job_reference) {
            await respond(route, { success: false, error: 'missing_job_reference' }, 400);
            return;
          }
          state.cv_data.it_ai_skills = ['Audit management', 'Lean / Kaizen', 'Process governance', 'Quality systems'];
          await respond(route, {
            success: true,
            response: 'Skills ranked. Ready to generate PDF.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'GENERATE',
              title: 'Stage 6/6 — Generate',
              text: 'Generate final PDF.',
              fields: [],
              actions: [{ id: 'GENERATE_PDF', label: 'Generate PDF', style: 'primary' }],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'SKILLS_TAILOR_SKIP': {
          await respond(route, {
            success: true,
            response: 'Skipped. Ready to generate PDF.',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'GENERATE',
              title: 'Stage 6/6 — Generate',
              text: 'Generate final PDF.',
              fields: [],
              actions: [{ id: 'GENERATE_PDF', label: 'Generate PDF', style: 'primary' }],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'GENERATE_PDF': {
          state.counters.generate_pdf += 1;
          await respond(route, {
            success: true,
            response: 'Generate PDF?',
            session_id: state.session_id,
            ui_action: {
              kind: 'review_form',
              stage: 'GENERATE_CONFIRM',
              title: 'Generate PDF?',
              text: 'Confirm PDF generation.',
              fields: [],
              actions: [{ id: 'GENERATE_PDF_CONFIRM', label: 'Generate PDF', style: 'primary' }],
              disable_free_text: true,
            },
          });
          return;
        }

        case 'GENERATE_PDF_CONFIRM': {
          if (!state.confirmed_flags.contact_confirmed || !state.confirmed_flags.education_confirmed) {
            await respond(route, { success: false, error: 'readiness_not_met' }, 400);
            return;
          }
          await respond(route, {
            success: true,
            response: 'PDF generated.',
            session_id: state.session_id,
            pdf_base64: makeBase64StubPdf(),
            ui_action: null,
          });
          return;
        }

        default: {
          await respond(route, { success: false, error: `unknown_action:${String(actionId)}` }, 400);
        }
      }
    });
  };

  return { setup, state };
}

test.describe('Stage SoT scenarios (mocked backend state machine)', () => {
  test('happy path: job offer + notes + tailoring runs + pdf', async ({ page }) => {
    test.setTimeout(120_000);

    test.skip(!fs.existsSync(INPUT_DOCX), `Missing input DOCX: ${INPUT_DOCX}`);

    const mock = createProcessCvSoTMock();
    await mock.setup(page);

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    // Upload CV (this also clears any previously-entered job URL in UI).
    await page.locator('input[type="file"]').setInputFiles(INPUT_DOCX);

    // Provide job URL (stored by UI and sent in payload).
    await page.getByPlaceholder('https://...').fill(JOB_URL);

    // Start message.
    await page.locator('textarea').first().fill('przygotuj moje cv pod te oferte pracy (all in english)');
    await page.locator('textarea').first().press('Enter');

    // Language selection.
    await expect(page.getByText('Language Selection')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: 'English' }).click();
    expect(mock.state.language).toBe('en');
    expect(mock.state.docx_base64_len).toBeGreaterThan(1000);
    expect(mock.state.job_posting_url).toBe(JOB_URL);

    // Import.
    await expect(page.getByText('Import DOCX data?')).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Import DOCX prefill/i }).click();

    // Contact + Education.
    await expect(page.getByText(/Stage 1\/6.*Contact/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Confirm & lock/i }).click();
    expect(mock.state.confirmed_flags.contact_confirmed).toBe(true);

    await expect(page.getByText(/Stage 2\/6.*Education/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Confirm & lock/i }).click();
    expect(mock.state.confirmed_flags.education_confirmed).toBe(true);

    // Job offer analyze.
    await expect(page.getByText(/Stage 3\/6.*Job offer/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Analyze/i }).click();
    expect(mock.state.counters.job_offer_analyze).toBe(1);
    expect(mock.state.job_reference).toBeTruthy();

    // Work notes edit + save.
    await expect(page.getByText(/Stage 4\/6.*Work experience/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Add tailoring notes/i }).click();

    await expect(page.getByText('Work tailoring notes')).toBeVisible({ timeout: 10_000 });
    await page.locator('textarea').first().fill(TAILORING_NOTES);
    await page.getByRole('button', { name: /Save notes/i }).click();
    expect(mock.state.work_tailoring_notes).toContain('claims reduced by 70%');

    // Work tailoring run.
    await expect(page.getByText(/Stage 4\/6.*Work experience/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Run tailoring/i }).click();
    expect(mock.state.counters.work_tailor_run).toBe(1);
    expect(mock.state.cv_data.work_experience[0].bullets[0]).toMatch(/Reduced claims by 70%/i);

    // Stage 5a → 5b.
    await expect(page.getByText(/Stage 5a\/6.*Technical projects/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Continue/i }).click();

    await expect(page.getByText(/Stage 5b\/6.*Skills.*FÄHIGKEITEN/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Generate ranked skills/i }).click();
    expect(mock.state.counters.skills_tailor_run).toBe(1);
    expect(mock.state.cv_data.it_ai_skills.length).toBeGreaterThan(0);

    // Generate PDF.
    await expect(page.getByText(/Stage 6\/6.*Generate/i)).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /Generate PDF/i }).click();
    await expect(page.getByText('Generate PDF?').first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /^Generate PDF$/i }).click();

    await expect(page.getByRole('button', { name: /Download PDF/i })).toBeVisible({ timeout: 10_000 });
  });

  test('error path: WORK_TAILOR_RUN fails closed without job reference', async ({ page }) => {
    test.setTimeout(120_000);

    test.skip(!fs.existsSync(INPUT_DOCX), `Missing input DOCX: ${INPUT_DOCX}`);

    const mock = createProcessCvSoTMock();
    await mock.setup(page);

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    await page.locator('input[type="file"]').setInputFiles(INPUT_DOCX);
    await page.getByPlaceholder('https://...').fill(JOB_URL);

    await page.locator('textarea').first().fill('przygotuj moje cv pod te oferte pracy (all in english)');
    await page.locator('textarea').first().press('Enter');

    await page.getByRole('button', { name: 'English' }).click();
    await page.getByRole('button', { name: /Import DOCX prefill/i }).click();
    await page.getByRole('button', { name: /Confirm & lock/i }).click();
    await page.getByRole('button', { name: /Confirm & lock/i }).click();

    // Skip job offer, then try work tailoring.
    await page.getByRole('button', { name: /Skip/i }).click();
    await expect(page.getByText(/Stage 4\/6.*Work experience/i)).toBeVisible({ timeout: 10_000 });

    await page.getByRole('button', { name: /Run tailoring/i }).click();

    // UI displays server error message.
    await expect(page.getByText(/❌ Error: Server error: 500/i)).toBeVisible({ timeout: 10_000 });
    expect(mock.state.counters.work_tailor_run).toBe(1);
    expect(mock.state.job_reference).toBeNull();
  });

  test('SoT guard: job offer is parsed once (second analyze rejected)', async ({ page }) => {
    test.setTimeout(120_000);

    test.skip(!fs.existsSync(INPUT_DOCX), `Missing input DOCX: ${INPUT_DOCX}`);

    const mock = createProcessCvSoTMock();
    await mock.setup(page);

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });

    await page.locator('input[type="file"]').setInputFiles(INPUT_DOCX);
    await page.getByPlaceholder('https://...').fill(JOB_URL);

    await page.locator('textarea').first().fill('przygotuj moje cv pod te oferte pracy (all in english)');
    await page.locator('textarea').first().press('Enter');

    await page.getByRole('button', { name: 'English' }).click();
    await page.getByRole('button', { name: /Import DOCX prefill/i }).click();
    await page.getByRole('button', { name: /Confirm & lock/i }).click();
    await page.getByRole('button', { name: /Confirm & lock/i }).click();

    await page.getByRole('button', { name: /Analyze/i }).click();
    expect(mock.state.counters.job_offer_analyze).toBe(1);

    // Try to re-run parse from the next stage; mock must reject and UI must show error.
    await page.getByRole('button', { name: /Re-analyze job offer/i }).click();
    await expect(page.getByText(/❌ Error: Server error: 400/i)).toBeVisible({ timeout: 10_000 });
    expect(mock.state.counters.job_offer_analyze).toBe(1);
  });
});
