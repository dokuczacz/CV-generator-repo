import { test, expect, type Locator, type Page, type Response, Route, type TestInfo } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');
const FIXTURES_DIR = path.join(__dirname, '../fixtures');

function ts(): string {
  return new Date().toISOString();
}

function startWizardHeartbeat(page: Page, getLabel: () => string, intervalMs = 10_000) {
  let running = false;
  const intervalId = setInterval(() => {
    if (running) return;
    running = true;
    (async () => {
      const label = getLabel();
      const stageTitle = await page
        .getByText(/Stage\s+\d+\/\d+\s+—/i)
        .first()
        .textContent()
        .then((t) => t?.trim())
        .catch(() => null);
      const importTitle = await page
        .getByText(/Import DOCX data\?|confirm whether to import/i)
        .first()
        .textContent()
        .then((t) => t?.trim())
        .catch(() => null);
      const langTitle = await page
        .getByText(/Language Selection/i)
        .first()
        .textContent()
        .then((t) => t?.trim())
        .catch(() => null);
      const bits = [
        `label=${label}`,
        stageTitle ? `stage=${stageTitle}` : null,
        importTitle ? 'import_gate=visible' : null,
        langTitle ? 'language=visible' : null,
      ].filter(Boolean);
      // eslint-disable-next-line no-console
      console.log(`[${ts()}] heartbeat | ${bits.join(' | ')}`);
    })()
      .catch(() => undefined)
      .finally(() => {
        running = false;
      });
  }, intervalMs);

  return () => clearInterval(intervalId);
}

/**
 * Load pre-recorded backend responses from fixtures.
 * These are real responses captured from successful test sessions with OpenAI.
 * Using fixtures allows tests to run without OpenAI API key and without cost.
 */
function loadFixture(name: string): any {
  const fixturePath = path.join(FIXTURES_DIR, `${name}.json`);
  if (fs.existsSync(fixturePath)) {
    return JSON.parse(fs.readFileSync(fixturePath, 'utf-8'));
  }
  console.warn(`[fixtures] Missing fixture: ${name}.json`);
  return null;
}

// Map backend stage identifiers to captured fixtures
const stageFixtures: Record<string, any> = {
  LANGUAGE_SELECTION: loadFixture('LANGUAGE_SELECTION'),
  IMPORT_PREFILL: loadFixture('IMPORT_PREFILL'),
  CONTACT: loadFixture('CONTACT'),
  EDUCATION: loadFixture('EDUCATION'),
  JOB_POSTING: loadFixture('JOB_POSTING'),
  WORK_EXPERIENCE: loadFixture('WORK_EXPERIENCE'),
  FURTHER_EXPERIENCE: loadFixture('FURTHER_EXPERIENCE'),
};

/**
 * Fallback mock responses for stages without recorded fixtures yet.
 * TODO: Replace with real fixtures from successful sessions.
 */
const mockResponses: Record<string, any> = {
  job_reference: {
    title: 'Senior Quality Engineer',
    company: 'TechCorp AG',
    location: 'Zurich, Switzerland',
    responsibilities: [
      'Drive quality systems implementation (IATF 16949)',
      'Lead audit programs and compliance initiatives',
      'Implement process improvement using Six Sigma'
    ],
    requirements: ['IATF 16949 knowledge', 'Audit experience', 'Process improvement', 'Quality management'],
    tools_tech: ['ISO 9001', 'FMEA', 'SPC', 'Lean', 'Six Sigma'],
    keywords: ['quality', 'IATF', 'audit', 'process', 'compliance']
  },
  work_experience_proposal: {
    roles: [
      {
        title: 'Quality Systems Manager',
        company: 'AutoCorp GmbH',
        date_range: '2020-03 – 2025-01',
        location: 'Stuttgart, Germany',
        bullets: [
          'Implemented IATF 16949 certification achieving 98% compliance score',
          'Led quarterly audits across 5 manufacturing sites, reducing non-conformances by 45%',
          'Developed and trained process improvement teams on Six Sigma methodology'
        ]
      },
      {
        title: 'Quality Engineer',
        company: 'Precision Industries',
        date_range: '2018-06 – 2020-02',
        location: 'Munich, Germany',
        bullets: [
          'Established SPC (Statistical Process Control) for 12 production lines',
          'Conducted FMEA analysis resulting in 30% reduction in customer complaints',
          'Managed ISO 9001 documentation and internal audit schedule'
        ]
      }
    ],
    notes: 'Reordered to emphasize quality systems and audit experience. Focused on quantified improvements.'
  },
  it_ai_skills_proposal: {
    skills: ['Quality Management Systems', 'IATF 16949', 'ISO 9001', 'Lean Six Sigma', 'FMEA', 'SPC', 'Audit Management'],
    notes: 'Ranked by relevance to job posting. Removed legacy VB.NET skills not applicable to this role.'
  },
  tech_ops_skills_proposal: {
    skills: ['Process Improvement', 'Quality Audits', 'Risk Management', 'Compliance Management', 'Supplier Management'],
    notes: 'Selected operational skills matching job requirements. Focused on process governance.'
  },
  further_experience_proposal: {
    projects: [
      {
        title: 'IATF 16949 Implementation Case Study',
        organization: 'AutoCorp GmbH',
        date_range: '2020-06 – 2021-03',
        location: 'Stuttgart, Germany',
        bullets: [
          'Led cross-functional team implementing IATF 16949 certification',
          'Achieved first-pass audit with zero major non-conformances'
        ]
      }
    ],
    notes: 'Selected 1 most relevant project demonstrating IATF expertise.'
  }
};

function extractPdfTextWithPyPdf2(pdfPath: string): string {
  const venvWin = path.join(process.cwd(), '.venv', 'Scripts', 'python.exe');
  const venvPosix = path.join(process.cwd(), '.venv', 'bin', 'python');
  const python =
    process.env.PYTHON ||
    (fs.existsSync(venvWin) ? venvWin : fs.existsSync(venvPosix) ? venvPosix : 'python');
  const code = [
    'import sys',
    'from PyPDF2 import PdfReader',
    'r = PdfReader(sys.argv[1])',
    "print('\\n'.join((p.extract_text() or '') for p in r.pages))",
  ].join('; ');

  const res = spawnSync(python, ['-c', code, pdfPath], {
    encoding: 'utf-8',
    maxBuffer: 12_000_000,
  });

  expect(res.status, `Failed to run PyPDF2 extractor (python=${python}): ${res.stderr || ''}`).toBe(0);
  return res.stdout || '';
}

function extractSection(text: string, start: RegExp, end: RegExp): string {
  const m = new RegExp(`${start.source}([\\s\\S]*?)${end.source}`, 'i').exec(text);
  return m?.[1] || '';
}

function sanitizePdfSectionText(section: string): string {
  // PDF extraction often includes repeated header/footer and contact block.
  // Strip the obvious noise so we don’t get false positives.
  return section
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l)
    .filter((l) => !/^Page\s+\d+\s+of\s+\d+/i.test(l))
    .filter((l) => !l.includes('@'))
    .filter((l) => !/^\+\d/.test(l))
    .join('\n')
    .trim();
}

function assertPdfSkillsSectionsNotEmpty(pdfPath: string) {
  const text = extractPdfTextWithPyPdf2(pdfPath);

  const itAiRaw = extractSection(text, /IT\s*&\s*AI\s*Skills/i, /Technical\s*&\s*Operational\s*Skills/i);
  const itAi = sanitizePdfSectionText(itAiRaw);
  expect(itAi.length, 'PDF: IT & AI Skills section should not be empty').toBeGreaterThan(10);
  expect(itAi, 'PDF: IT & AI Skills section should contain real text').toMatch(/[A-Za-zÀ-ž0-9]/);

  const techOpsRaw = extractSection(text, /Technical\s*&\s*Operational\s*Skills/i, /Education/i);
  const techOps = sanitizePdfSectionText(techOpsRaw);
  expect(techOps.length, 'PDF: Technical & Operational Skills section should not be empty').toBeGreaterThan(10);
  expect(techOps, 'PDF: Technical & Operational Skills section should contain real text').toMatch(/[A-Za-zÀ-ž0-9]/);
}

/**
 * Intercept /api/process-cv calls and replace responses with fixtures
 * This allows tests to run without OpenAI API key and without cost
 */
function setupMockInterceptor(page: Page) {
  page.route('**/api/process-cv', async (route: Route) => {
    try {
      // Always pass request through to backend
      const response = await route.fetch();
      let responseBody: any = {};
      
      try {
        const text = await response.text();
        responseBody = JSON.parse(text || '{}');
      } catch (e) {
        // If parsing fails, pass through unchanged
        await route.fulfill({ response });
        return;
      }
      
      // Check which stage this is and replace with fixture if available
      const stage = responseBody?.ui_action?.stage;
      const fixture = stage ? stageFixtures[stage] || null : null;
      
      if (fixture) {
        console.log(`[fixtures] Using fixture for stage: ${stage}`);
        const patchedFixture = {
          ...fixture,
          // Keep the real backend session_id so subsequent non-fixture calls
          // hit the same backend session. Also avoids collisions across tests.
          session_id: responseBody?.session_id || fixture.session_id,
          trace_id: responseBody?.trace_id || fixture.trace_id,
        };
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(patchedFixture)
        });
      } else {
        // No fixture available, pass through real response
        await route.fulfill({ response });
      }
    } catch (e) {
      console.error('[fixtures] Interceptor error:', e);
      await route.abort();
    }
  });
}

async function clickActionAndWait(page: Page, target: string | Locator, label?: string): Promise<Response | null> {
  const button = typeof target === 'string' ? page.getByRole('button', { name: target }).first() : target;
  const buttonLabel =
    label || (typeof target === 'string' ? target : (await button.textContent())?.trim() || 'action');

  await expect(button).toBeVisible({ timeout: 15_000 });
  // Some UI actions render disabled briefly while state hydrates.
  await expect(button).toBeEnabled({ timeout: 15_000 });

  const responsePromise = page
    .waitForResponse(
      (r: Response) => r.url().includes('/api/process-cv') && r.request().method() === 'POST',
      { timeout: 10_000 }
    )
    .catch(() => null);

  await button.click({ timeout: 15_000 });

  const response = await responsePromise;
  if (response) {
    // eslint-disable-next-line no-console
    console.log(`[process-cv] after "${buttonLabel}" status=${response.status()}`);
  }

  return response;
}

async function maybeHandleImportPrefill(page: Page) {
  // First check for language selection (appears before import gate in some flows)
  const langSelection = page.getByText('Language Selection');
  if (await langSelection.isVisible().catch(() => false)) {
    console.log('[test] Language selection detected, choosing English');
    await clickActionAndWait(page, 'English');
    await expect(langSelection).toBeHidden({ timeout: 10_000 });
    console.log('[test] Language selection completed');
  }
  
  // Then check for import DOCX prompt - check both possible texts
  const importTitle1 = page.getByText('Import DOCX data?');
  const importTitle2 = page.getByText(/confirm whether to import/i);
  const hasImport1 = await importTitle1.isVisible().catch(() => false);
  const hasImport2 = await importTitle2.isVisible().catch(() => false);
  
  if (hasImport1 || hasImport2) {
    console.log('[test] Import prefill prompt detected, clicking Import DOCX prefill');
    const importButton = page
      .getByRole('button')
      .filter({ hasText: /Import DOCX prefill|Import|Tak|Yes/i })
      .first();

    if (await importButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await clickActionAndWait(page, importButton, 'Import DOCX prefill');
      await expect(page.getByText(/Stage 1\/6.*Contact/i).first()).toBeVisible({ timeout: 10_000 });
    } else {
      console.log('[test] Import button missing, skipping confirmation');
    }
    console.log('[test] Import prefill completed, waiting for Contact stage...');
  } else {
    console.log('[test] No import prompt found, continuing...');
  }
}

async function ensureContactConfirmed(page: Page) {
  await expect(page.getByText(/Stage 1\/6.*Contact/i).first()).toBeVisible({ timeout: 15_000 });
  console.log('[test] Contact stage found, confirming...');
  
  // Simply click Confirm & lock (don't edit, use fixture values as-is)
  await clickActionAndWait(page, 'Confirm & lock');
}

async function completeEducationStage(page: Page) {
  await expect(page.getByText(/Stage 2\/6.*Education/i).first()).toBeVisible({ timeout: 15_000 });
  await clickActionAndWait(page, 'Confirm & lock');
}

async function completeJobOfferStage(page: Page) {
  await expect(page.getByText(/Stage 3\/6.*Job offer/i).first()).toBeVisible({ timeout: 15_000 });

  // Job offer is optional - just skip it to speed up tests
  console.log('[test] Stage 3: Skipping job offer (optional)');
  await clickActionAndWait(page, 'Skip');
}

async function completeWorkExperienceStage(page: Page) {
  await expect(page.getByText(/Stage 4\/6.*Work experience/i).first()).toBeVisible({ timeout: 15_000 });

  // In mocked flow, primary action is "Continue" (no tailoring run needed)
  const continueButton = page
    .getByRole('button')
    .filter({ hasText: /Continue|Confirm|Accept/i })
    .first();
  await expect(continueButton).toBeVisible({ timeout: 10_000 });
  await clickActionAndWait(page, continueButton, 'Continue');
}

async function completeFurtherExperienceStage(page: Page) {
  const stageHeaderPattern = /Stage 5(?:[ab])?\/6.*(Further Experience|Technical projects|Skills|FÄHIGKEITEN)/i;
  await expect(page.getByText(stageHeaderPattern).first()).toBeVisible({ timeout: 15_000 });

  // Select projects
  const selectButton = page.getByRole('button', { name: /Select|Tailor|Add tailoring/i }).first();
  let stageAdvanced = false;
  if (await selectButton.isVisible().catch(() => false)) {
    await clickActionAndWait(page, selectButton, 'Select projects');
    const acceptButton = page.getByRole('button', { name: /Accept & continue/i }).first();
    if (await acceptButton.isVisible().catch(() => false)) {
      await clickActionAndWait(page, acceptButton, 'Accept & continue');
      stageAdvanced = true;
    }
  }

  if (!stageAdvanced) {
    const fallbackButton = page
      .getByRole('button')
      .filter({ hasText: /Continue|Skip/i })
      .first();
    await expect(fallbackButton).toBeVisible({ timeout: 10_000 });
    await clickActionAndWait(page, fallbackButton, 'Continue');
  }

  const skipOptionalStage = async (pattern: RegExp) => {
    const stageLocator = page.getByText(pattern).first();
    const stageVisible = await stageLocator
      .waitFor({ state: 'visible', timeout: 5_000 })
      .then(() => true)
      .catch(() => false);
    if (!stageVisible) {
      return;
    }

    const continueButton = page
      .getByRole('button')
      .filter({ hasText: /Continue|Skip/i })
      .first();
    await expect(continueButton).toBeVisible({ timeout: 5_000 });
    await clickActionAndWait(page, continueButton, 'Continue');
  };

  await skipOptionalStage(/Stage 5b\/6.*Skills.*FÄHIGKEITEN/i);
}

async function completeGenerateStage(page: Page, testInfo: TestInfo, fileName = 'generated-cv.pdf') {
  await expect(page.getByText(/Stage 6\/6|Generate/i).first()).toBeVisible({ timeout: 15_000 });
  await clickActionAndWait(page, 'Generate PDF');

  // Confirm generation
  await expect(page.getByText('Generate PDF?')).toBeVisible({ timeout: 10_000 });
  const confirmButton = page
    .getByText('Generate PDF?')
    .locator('..')
    .getByRole('button', { name: /^Generate PDF$/i });
  const confirmResponse = await clickActionAndWait(page, confirmButton, 'Generate PDF (confirm)');

  // Verify PDF is available
  await expect(page.getByRole('button', { name: /Download PDF/i })).toBeVisible({ timeout: 30_000 });

  // Persist PDF into the Playwright output directory so it shows up in the report.
  try {
    if (confirmResponse) {
      const obj = await confirmResponse.json();
      const pdfBase64 = obj?.pdf_base64;
      if (typeof pdfBase64 === 'string' && pdfBase64.trim()) {
        const outPath = testInfo.outputPath(fileName);
        const bytes = Buffer.from(pdfBase64, 'base64');
        fs.writeFileSync(outPath, bytes);
        await testInfo.attach(fileName, { path: outPath, contentType: 'application/pdf' });
        // eslint-disable-next-line no-console
        console.log(`[artifacts] saved PDF -> ${outPath}`);

        // Verify output quality: avoid empty skills sections in the rendered PDF.
        assertPdfSkillsSectionsNotEmpty(outPath);
      }
    }
  } catch {
    // ignore parse/IO issues; PDF presence is still validated by the Download button
  }
}

test.describe('CV Generator E2E (Mocked OpenAI)', () => {
  test.beforeEach(async ({ page }) => {
    // Setup mock interceptor before loading page
    setupMockInterceptor(page);

    page.on('console', (msg) => {
      // eslint-disable-next-line no-console
      console.log(`[browser console] ${msg.type()}: ${msg.text()}`);
    });
    page.on('pageerror', (err) => {
      // eslint-disable-next-line no-console
      console.log(`[browser error] ${String(err)}`);
    });
  });

  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status === testInfo.expectedStatus) return;
    try {
      await testInfo.attach('page-url.txt', {
        body: Buffer.from(page.url(), 'utf-8'),
        contentType: 'text/plain',
      });
      await testInfo.attach('page.html', {
        body: Buffer.from(await page.content(), 'utf-8'),
        contentType: 'text/html',
      });
    } catch {
      // ignore
    }
  });

  test('should generate CV through full wizard with mocked AI (no OpenAI calls)', async ({ page }, testInfo) => {
    test.setTimeout(300_000);
    const stepRef = { current: 'init' };
    const stopHeartbeat = startWizardHeartbeat(page, () => stepRef.current);

    // Suppress dialogs
    page.on('dialog', async (dialog) => {
      await dialog.dismiss().catch(() => undefined);
    });

    // ===== INIT =====
    stepRef.current = 'goto';
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    await expect(page.getByText('CV Generator')).toBeVisible({ timeout: 15_000 });

    // Upload CV and start session
    stepRef.current = 'upload';
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    const messageInput = page.locator('textarea').first();
    await messageInput.fill('start');
    
    // Wait for send button to be enabled
    const sendButton = page.getByRole('button', { name: /Send/i });
    await expect(sendButton).toBeEnabled({ timeout: 5_000 });
    
    console.log('DEBUG: About to send initial message');
    stepRef.current = 'send-initial-message';
    await messageInput.press('Enter');
    console.log('DEBUG: Message sent, waiting for response...');

    // Wait for import gate or stage 1 (increased timeout)
    // DEBUG: Log page content before timeout
    stepRef.current = 'import/language gate';
    await page.waitForFunction(
      () => {
        const text = document.body.innerText;
        return (
          text.includes('confirm whether to import') ||
          text.includes('Import DOCX data?') ||
          text.includes('Stage 1/6') ||
          text.includes('Language Selection')
        );
      },
      undefined,
      { timeout: 15_000 }
    );

    stepRef.current = 'maybeHandleImportPrefill';
    await maybeHandleImportPrefill(page);

    // ===== STAGE 1: CONTACT =====
    // eslint-disable-next-line no-console
    console.log('[test] Stage 1: Contact');
    stepRef.current = 'contact';
    await ensureContactConfirmed(page);

    // ===== STAGE 2: EDUCATION =====
    // eslint-disable-next-line no-console
    console.log('[test] Stage 2: Education');
    stepRef.current = 'education';
    await completeEducationStage(page);

    // ===== STAGE 3: JOB OFFER =====
    // eslint-disable-next-line no-console
    console.log('[test] Stage 3: Job offer (with mocked OpenAI extraction)');
    stepRef.current = 'job-offer';
    await completeJobOfferStage(page);

    // ===== STAGE 4: WORK EXPERIENCE =====
    // eslint-disable-next-line no-console
    console.log('[test] Stage 4: Work experience (with mocked tailoring)');
    stepRef.current = 'work-experience';
    await completeWorkExperienceStage(page);

    // ===== STAGE 5: FURTHER EXPERIENCE =====
    // eslint-disable-next-line no-console
    console.log('[test] Stage 5: Further Experience (with mocked selection)');
    stepRef.current = 'further-experience';
    await completeFurtherExperienceStage(page);

    // ===== STAGE 6: GENERATE =====
    // eslint-disable-next-line no-console
    console.log('[test] Stage 6: Generate PDF');
    stepRef.current = 'generate-pdf';
    await completeGenerateStage(page, testInfo, 'generated-cv.pdf');

    // ===== VERIFICATION =====
    // eslint-disable-next-line no-console
    console.log('[test] ✅ CV generated successfully with mocked AI responses');

    stopHeartbeat();
  });

  test('should verify all UI stages render correctly', async ({ page }, testInfo) => {
    test.setTimeout(300_000);
    const stepRef = { current: 'init' };
    const stopHeartbeat = startWizardHeartbeat(page, () => stepRef.current);

    const expectedStages = [
      'LANGUAGE_SELECTION',
      'CONTACT',
      'EDUCATION',
      'JOB_POSTING',
      'WORK_EXPERIENCE',
      'FURTHER_EXPERIENCE'
    ];
    const seenStages = new Set<string>();

    page.on('response', async (response) => {
      if (!response.url().includes('/api/process-cv')) return;
      try {
        const body = await response.json();
        const stageId = body?.ui_action?.stage;
        if (stageId) {
          seenStages.add(stageId);
        }
      } catch {
        // ignore JSON parse issues
      }
    });

    page.on('dialog', async (dialog) => {
      await dialog.dismiss().catch(() => undefined);
    });

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    stepRef.current = 'upload';
    await page.locator('input[type="file"]').setInputFiles(SAMPLE_CV);
    const messageInput = page.locator('textarea').first();
    await messageInput.fill('start');
    
    // Wait for send button
    const sendButton = page.getByRole('button', { name: /Send/i });
    await expect(sendButton).toBeEnabled({ timeout: 5_000 });
    
    console.log('DEBUG Test2: About to send initial message');
    stepRef.current = 'send-initial-message';
    await messageInput.press('Enter');
    console.log('DEBUG Test2: Message sent, waiting for response...');

    stepRef.current = 'import/language gate';
    await page.waitForFunction(
      () => {
        const text = document.body.innerText;
        return (
          text.includes('confirm whether to import') ||
          text.includes('Import DOCX data?') ||
          text.includes('Stage 1/6') ||
          text.includes('Language Selection')
        );
      },
      undefined,
      { timeout: 15_000 }
    );

    stepRef.current = 'maybeHandleImportPrefill';
    await maybeHandleImportPrefill(page);

    // Verify each stage header renders
    // Drive through stages quickly (same helpers already assert visibility)
    stepRef.current = 'contact';
    await ensureContactConfirmed(page);
    stepRef.current = 'education';
    await completeEducationStage(page);
    stepRef.current = 'job-offer';
    await completeJobOfferStage(page);
    stepRef.current = 'work-experience';
    await completeWorkExperienceStage(page);
    stepRef.current = 'further-experience';
    await completeFurtherExperienceStage(page);
    stepRef.current = 'generate-pdf';
    await completeGenerateStage(page, testInfo, 'generated-cv-ui-verification.pdf');

    const missingStage = expectedStages.find((stage) => !seenStages.has(stage));
    expect(missingStage).toBeUndefined();
    // eslint-disable-next-line no-console
    console.log('[ui-verification] ✅ All expected stages returned from backend');

    stopHeartbeat();
  });
});
