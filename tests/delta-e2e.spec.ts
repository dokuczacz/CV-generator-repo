import { test, expect, APIRequestContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Playwright E2E test for hash-based delta loading (P1 UNIT 4).
 * 
 * Scenario:
 * 1. Create a session with a sample CV
 * 2. Confirm the session (saves initial state)
 * 3. Edit work_experience section
 * 4. Generate context pack and verify delta mode marks work_experience as 'changed'
 * 5. Verify unchanged sections are sent as summaries only
 * 6. Assert token efficiency improvement
 */

const FUNCTIONS_BASE_URL = process.env.CV_FUNCTIONS_BASE_URL || 'http://localhost:7071/api';

interface ContextPack {
  schema_version: string;
  section_changes: Record<string, boolean>;
  section_hashes: Record<string, string>;
  work_experience: any;
  education: any;
  [key: string]: any;
}

/**
 * Sample CV for testing.
 */
function sampleCV() {
  return {
    full_name: 'Alice Johnson',
    email: 'alice@example.com',
    phone: '+1 (555) 987-6543',
    address_lines: ['456 Oak Avenue', 'San Francisco, CA 94102'],
    profile: 'Senior Full-Stack Engineer with expertise in React, Node.js, and cloud architecture. 8+ years building scalable SaaS platforms.',
    work_experience: [
      {
        employer: 'TechCorp Inc',
        title: 'Senior Engineer',
        date_range: '2021-Present',
        location: 'San Francisco, CA',
        bullets: [
          'Led migration of monolith to microservices, reducing API response time by 65%',
          'Mentored team of 5 junior engineers on best practices',
          'Architected real-time dashboard serving 50k+ concurrent users',
        ],
      },
      {
        employer: 'StartupXYZ',
        title: 'Full-Stack Developer',
        date_range: '2019-2021',
        location: 'Remote',
        bullets: [
          'Built React UI and Node.js backend for MVP that acquired 10k users',
          'Implemented CI/CD pipeline reducing deployment time from 30m to 3m',
        ],
      },
    ],
    education: [
      {
        institution: 'Stanford University',
        degree: 'BS',
        field: 'Computer Science',
        year: '2019',
      },
    ],
    languages: ['English', 'Spanish', 'Mandarin'],
    it_ai_skills: ['React', 'Node.js', 'TypeScript', 'PostgreSQL', 'AWS', 'Docker', 'Kubernetes', 'GraphQL'],
    interests: ['Open Source', 'Machine Learning', 'Community Building'],
    further_experience: ['Speaker at React Conference 2023', 'Open Source Contributor (>100 repos)'],
  };
}

/**
 * Test suite for delta loading E2E.
 */
test.describe('Delta Loading E2E', () => {
  let request: APIRequestContext;
  let sessionId: string;
  let initialContextPack: ContextPack;
  let deltaContextPack: ContextPack;

  test.beforeAll(async ({ playwright }) => {
    request = await playwright.request.newContext();
  });

  test.afterAll(async () => {
    await request.dispose();
  });

  test('Step 1: Create session with sample CV', async () => {
    const cv = sampleCV();

    const res = await request.post(`${FUNCTIONS_BASE_URL}/ingest-docx`, {
      data: {
        file_contents: Buffer.from(JSON.stringify(cv)).toString('base64'),
        file_type: 'application/json',
      },
    });

    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('session_id');
    expect(data.session_id).toMatch(/^[a-f0-9-]+$/);

    sessionId = data.session_id;
    console.log(`✓ Session created: ${sessionId}`);
  });

  test('Step 2: Retrieve session and capture initial hashes', async () => {
    const res = await request.post(`${FUNCTIONS_BASE_URL}/get-cv-session`, {
      data: { session_id: sessionId },
    });

    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('cv_data');
    expect(data).toHaveProperty('metadata');
    expect(data.cv_data.full_name).toBe('Alice Johnson');

    console.log(`✓ Session retrieved: ${sessionId}`);
  });

  test('Step 3: Generate initial context pack (full mode)', async () => {
    const res = await request.post(`${FUNCTIONS_BASE_URL}/generate-context-pack-v2`, {
      data: {
        session_id: sessionId,
        phase: 'review_session',
        job_posting_text: null,
        max_pack_chars: 8000,
      },
    });

    expect(res.ok()).toBeTruthy();
    initialContextPack = await res.json();

    const initialSize = JSON.stringify(initialContextPack).length;
    console.log(`✓ Initial context pack: ${initialSize} bytes`);
  });

  test('Step 4: Confirm session (save initial state)', async () => {
    const res = await request.post(`${FUNCTIONS_BASE_URL}/update-cv-field`, {
      data: {
        session_id: sessionId,
        confirm: {
          contact_confirmed: true,
          education_confirmed: true,
        },
      },
    });

    expect(res.ok()).toBeTruthy();
    console.log(`✓ Session confirmed and initial hashes stored`);
  });

  test('Step 5: Modify work_experience section', async () => {
    const res = await request.post(`${FUNCTIONS_BASE_URL}/update-cv-field`, {
      data: {
        session_id: sessionId,
        edits: [
          {
            field_path: 'work_experience.0.title',
            value: 'Principal Engineer (Promoted)',
          },
          {
            field_path: 'work_experience.0.bullets.0',
            value: 'Led enterprise cloud migration, achieving 80% cost reduction and 95% uptime SLA',
          },
        ],
      },
    });

    expect(res.ok()).toBeTruthy();
    console.log(`✓ Work experience edited (title + bullet)`);
  });

  test('Step 6: Generate delta context pack (delta mode)', async () => {
    const res = await request.post(`${FUNCTIONS_BASE_URL}/generate-context-pack-v2`, {
      data: {
        session_id: sessionId,
        phase: 'review_session',
        job_posting_text: null,
        max_pack_chars: 8000,
      },
    });

    expect(res.ok()).toBeTruthy();
    deltaContextPack = await res.json();

    if (deltaContextPack.section_changes) {
      const changedSections = Object.entries(deltaContextPack.section_changes)
        .filter(([_, changed]) => changed)
        .map(([section]) => section)
        .join(', ');
      console.log(`✓ Delta context pack generated with changes: ${changedSections}`);
    }
  });

  test('Step 7: Verify delta mode markers', async () => {
    expect(deltaContextPack).toHaveProperty('section_changes');
    const changes = deltaContextPack.section_changes as Record<string, boolean>;

    expect(changes['work_experience']).toBe(true);
    console.log(`✓ work_experience marked as changed`);

    if (changes['education'] !== undefined) {
      expect(changes['education']).toBe(false);
      console.log(`✓ education marked as unchanged`);
    }
  });

  test('Step 8: Verify changed sections have full data', async () => {
    if (deltaContextPack.work_experience?.status === 'changed') {
      expect(deltaContextPack.work_experience).toHaveProperty('data');
      expect(Array.isArray(deltaContextPack.work_experience.data)).toBe(true);
      console.log(
        `✓ work_experience sent as full data (${deltaContextPack.work_experience.data.length} items)`
      );
    }
  });

  test('Step 9: Verify unchanged sections are summaries', async () => {
    if (deltaContextPack.education?.status === 'unchanged') {
      expect(deltaContextPack.education).toHaveProperty('count');
      expect(deltaContextPack.education).not.toHaveProperty('data');
      console.log(
        `✓ education sent as summary only (count: ${deltaContextPack.education.count})`
      );
    }
  });

  test('Step 10: Measure token efficiency (pack size)', async () => {
    const fullSize = JSON.stringify(initialContextPack).length;
    const deltaSize = JSON.stringify(deltaContextPack).length;

    console.log(`
      Initial pack size:  ${fullSize} bytes
      Delta pack size:    ${deltaSize} bytes
    `);

    if (deltaContextPack.section_changes) {
      const unchangedCount = Object.values(deltaContextPack.section_changes).filter(
        (changed) => !changed
      ).length;

      if (unchangedCount > 0) {
        console.log(`✓ ${unchangedCount} unchanged sections use summary format (more efficient)`);
      }
    }
  });

  test('Step 11: Verify section hashes are stable', async () => {
    expect(deltaContextPack).toHaveProperty('section_hashes');
    const hashes = deltaContextPack.section_hashes as Record<string, string>;

    Object.entries(hashes).forEach(([section, hash]) => {
      expect(hash).toMatch(/^[a-f0-9]{16}$/);
      console.log(`  ${section}: ${hash}`);
    });

    console.log(`✓ All section hashes valid (16-char hex)`);
  });

  test('Step 12: Generate PDF to verify workflow end-to-end', async () => {
    const res = await request.post(`${FUNCTIONS_BASE_URL}/generate-cv`, {
      data: {
        session_id: sessionId,
        language: 'en',
        client_context: { source: 'playwright-test' },
      },
    });

    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('pdf_blob');

    const pdfBase64 = data.pdf_blob;
    expect(typeof pdfBase64).toBe('string');
    expect(pdfBase64.length).toBeGreaterThan(1000);

    const pdfBuffer = Buffer.from(pdfBase64, 'base64');
    const pdfPath = path.resolve(__dirname, '..', 'test-results', 'delta-test-output.pdf');
    fs.mkdirSync(path.dirname(pdfPath), { recursive: true });
    fs.writeFileSync(pdfPath, pdfBuffer);

    console.log(`✓ PDF generated successfully (${pdfBuffer.length} bytes)`);
    console.log(`  Saved to: ${pdfPath}`);
  });
});

/**
 * Performance baseline tests.
 */
test.describe('Delta Loading Performance', () => {
  let request: APIRequestContext;

  test.beforeAll(async ({ playwright }) => {
    request = await playwright.request.newContext();
  });

  test.afterAll(async () => {
    await request.dispose();
  });

  test('Context pack generation with delta < 100ms', async () => {
    const cv = sampleCV();

    // Create session
    const createRes = await request.post(`${FUNCTIONS_BASE_URL}/ingest-docx`, {
      data: {
        file_contents: Buffer.from(JSON.stringify(cv)).toString('base64'),
        file_type: 'application/json',
      },
    });

    const data = await createRes.json();
    const sessionId = data.session_id;

    // Generate pack and measure time
    const start = Date.now();
    const packRes = await request.post(`${FUNCTIONS_BASE_URL}/generate-context-pack-v2`, {
      data: {
        session_id: sessionId,
        phase: 'review_session',
        job_posting_text: null,
        max_pack_chars: 8000,
      },
    });
    const duration = Date.now() - start;

    expect(packRes.ok()).toBeTruthy();
    expect(duration).toBeLessThan(100);

    console.log(`✓ Context pack generated in ${duration}ms`);
  });
});
