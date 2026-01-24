import test from 'node:test';
import assert from 'node:assert/strict';

import * as capsule from '../lib/capsule';

test('capsule: buildUserContent includes snapshot + job posting and truncates job text to 6k', () => {
  const jobPostingUrl = 'https://example.com/job';
  const jobPostingText = 'J'.repeat(25000);
  const sessionSnapshot = JSON.stringify({ ok: true, session_id: 'sess_123', limit_risks: { work_entries: 5 } });

  const content = capsule.buildUserContent({
    userMessage: 'prepare cv please',
    hasDocx: true,
    hasSession: true,
    sessionId: 'sess_123',
    skipPhoto: false,
    sessionSnapshot,
    contextPack: { some: 'pack' },
    boundedCvText: 'cv text',
    jobPostingUrl,
    jobPostingText,
    language: 'en',
    stage: 'draft_proposal',
  });

  assert.match(content, /\[SESSION_SNAPSHOT_JSON\]/);
  assert.match(content, /\[CONTEXT_PACK_V2\]/);
  assert.match(content, new RegExp(`\\[Job posting text extracted from ${jobPostingUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
  assert.match(content, /truncated to 6000 chars/);
  assert.ok(content.includes('J'.repeat(6000)));
  assert.ok(!content.includes('J'.repeat(6001)));
});

test('capsule: buildUserContent emits missing markers when session/job artifacts are unavailable', () => {
  const content = capsule.buildUserContent({
    userMessage: 'go',
    hasDocx: false,
    hasSession: true,
    sessionId: 'sess_missing',
    skipPhoto: false,
    sessionSnapshot: null,
    contextPack: null,
    boundedCvText: null,
    jobPostingUrl: 'https://example.com/job',
    jobPostingText: null,
    language: 'en',
    stage: 'review_session',
  });

  assert.match(content, /\[SESSION_SNAPSHOT_JSON_MISSING\]/);
  assert.match(content, /\bMUST call get_cv_session\b/);
  assert.match(content, /\[JOB_POSTING_TEXT_MISSING\]/);
  assert.match(content, /\bAsk the user to paste\b/);
});

test('capsule: ContextPackV2 delimiters include docx_prefill_unconfirmed in preparation', () => {
  const content = capsule.buildUserContent({
    userMessage: 'go',
    hasDocx: true,
    hasSession: true,
    sessionId: 'sess_123',
    skipPhoto: false,
    sessionSnapshot: JSON.stringify({ ok: true }),
    contextPack: {
      schema_version: 'cvgen.context_pack.v2',
      phase: 'preparation',
      session_id: 'sess_123',
      language: 'en',
      cv_fingerprint: 'sha256:abc',
      preparation: {
        cv_data: { full_name: '' },
        docx_prefill_unconfirmed: {
          education: [{ institution: 'Uni', title: 'MSc', date_range: '2010–2015', details: [] }],
          email: 'a@example.com',
        },
      },
    },
    boundedCvText: null,
    jobPostingUrl: null,
    jobPostingText: null,
    language: 'en',
    stage: 'review_session',
  });

  assert.match(content, /<docx_prefill_unconfirmed>/);
  assert.match(content, /\"education\"/);
  assert.match(content, /\"institution\": \"Uni\"/);
  assert.match(content, /<\/docx_prefill_unconfirmed>/);
});

test('capsule: buildBaseInputList produces required system + user messages', () => {
  const userContent = 'hello';
  const input = capsule.buildBaseInputList({ hasDocx: true, systemPrompt: 'SYS', userContent });

  assert.equal(input[0]?.role, 'system');
  assert.match(String(input[0]?.content), /already uploaded/i);
  assert.equal(input.at(-1)?.role, 'user');
  assert.equal(input.at(-1)?.content, userContent);
});

test('capsule: buildBaseInputList omits systemPrompt when blank (dashboard prompt mode)', () => {
  const userContent = 'hello';
  const input = capsule.buildBaseInputList({ hasDocx: false, systemPrompt: '', userContent });

  // 3 baseline system messages + 1 user message.
  assert.equal(input.length, 4);
  assert.equal(input[0]?.role, 'system');
  assert.match(String(input[0]?.content), /session-based workflow/i);
  assert.equal(input[1]?.role, 'system');
  assert.match(String(input[1]?.content), /stateless/i);
  assert.equal(input[2]?.role, 'system');
  assert.match(String(input[2]?.content), /template note/i);
  assert.equal(input[3]?.role, 'user');
  assert.equal(input[3]?.content, userContent);
});

test('capsule: buildResponsesRequest keeps metadata contract (stage_seq string, truncation disabled)', () => {
  const req = capsule.buildResponsesRequest({
    promptId: undefined,
    modelOverride: undefined,
    stage: 'draft_proposal',
    stageSeq: 3,
    systemPrompt: 'SYS',
    stagePrompt: 'STAGE',
    inputList: [{ role: 'user', content: 'hi' }],
    tools: [],
  });

  assert.equal(req.truncation, 'disabled');
  assert.equal(req.metadata.stage, 'draft_proposal');
  assert.equal(req.metadata.stage_seq, '3');
  assert.equal(req.max_output_tokens, 1440);
  assert.equal(req.model, 'gpt-4o');
  assert.equal(Array.isArray(req.input), true);
  assert.equal(req.input.at(-1)?.role, 'system');
  assert.equal(req.input.at(-1)?.content, 'STAGE');
});

test('capsule: sanitizeToolOutputForModel(get_cv_session) returns limit_risks + required_present', () => {
  const toolOutput = JSON.stringify({
    success: true,
    session_id: 'sess_abc',
    expires_at: '2099-01-01T00:00:00Z',
    metadata: { language: 'en', extraction_method: 'docx_prefill', photo_blob: 'photos/sess_abc.jpg' },
    cv_data: {
      full_name: 'A B',
      email: 'a@example.com',
      phone: '+1 555 000',
      address_lines: ['Line 1', 'Line 2', 'Line 3 (ignored)'],
      profile: 'P'.repeat(1200),
      languages: ['English', 'German'],
      it_ai_skills: ['Python', 'Azure'],
      work_experience: [
        { date_range: '2020–2024', employer: 'ACME', location: 'X', title: 'Y', bullets: ['b1', 'b2', 'b3', 'b4', 'b5'] },
        { date_range: '2018–2020', employer: 'B', location: 'Y', title: 'Z', bullets: ['c1'] },
        { date_range: 'old', employer: 'C', location: 'Z', title: 'W', bullets: ['d1'] },
      ],
      education: [
        { date_range: '2010–2015', institution: 'Uni', title: 'MSc', details: ['d'.repeat(200), 'e'.repeat(200)] },
      ],
    },
  });

  const sanitized = capsule.sanitizeToolOutputForModel('get_cv_session', toolOutput);
  const parsed = JSON.parse(sanitized);

  assert.equal(parsed.ok, true);
  assert.equal(parsed.session_id, 'sess_abc');
  assert.equal(parsed.required_present.full_name, true);
  assert.equal(parsed.required_present.work_experience, true);
  assert.equal(parsed.required_present.education, true);

  assert.ok(typeof parsed.limit_risks.profile_chars === 'number');
  assert.equal(parsed.contact.address_lines.length, 2);
  assert.ok(typeof parsed.profile === 'string');
  // Profile is clamped to ~500 chars plus a short suffix that indicates truncation.
  assert.ok(parsed.profile.length <= 540);
  assert.match(parsed.profile, /\.\.\.\[\+\d+\]$/);
  assert.ok(Array.isArray(parsed.sample_work_experience));
  assert.ok(parsed.sample_work_experience.length <= 2);
  assert.ok(Array.isArray(parsed.work_experience_outline));
  assert.ok(parsed.work_experience_outline.length >= 1);
  assert.ok(Array.isArray(parsed.sample_education));
  assert.ok(parsed.sample_education.length <= 2);
  assert.ok(Array.isArray(parsed.education_outline));
  assert.ok(parsed.education_outline.length >= 1);
});

test('capsule: sanitizeToolOutputForModel(generate_cv_from_session) strips pdf_base64 but keeps length', () => {
  const toolOutput = JSON.stringify({
    success: false,
    session_id: 'sess_zzz',
    pdf_base64: 'X'.repeat(5000),
    validation_errors: ['DoD violation'],
  });

  const sanitized = capsule.sanitizeToolOutputForModel('generate_cv_from_session', toolOutput);
  const parsed = JSON.parse(sanitized);

  assert.equal(parsed.session_id, 'sess_zzz');
  assert.equal(typeof parsed.pdf_base64_length, 'number');
  assert.equal(parsed.pdf_base64, undefined);
});

test('capsule: roughInputChars accounts for message sizes (smoke)', () => {
  const input = [
    { role: 'system', content: 'a'.repeat(10) },
    { role: 'user', content: 'b'.repeat(20) },
    { role: 'assistant', arguments: 'c'.repeat(30) },
  ];
  assert.equal(capsule.roughInputChars(input), 60);
});
