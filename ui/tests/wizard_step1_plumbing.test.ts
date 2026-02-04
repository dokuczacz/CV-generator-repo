import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('wizard step1: upload call includes job_posting_url/text (no hardcoded empty)', () => {
  const src = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf-8');

  const hasJobUrl = /job_posting_url:\s*jobPostingUrl\s*\|\|\s*''/.test(src);
  const hasJobText = /job_posting_text:\s*jobPostingText\s*\|\|\s*''/.test(src);
  const hasClientContext =
    /client_context\s*:\s*\{[\s\S]*fast_path_profile\s*:\s*fastPathProfile/.test(src);

  assert.ok(hasJobUrl, 'Expected startWizardFromUpload to pass job_posting_url from state');
  assert.ok(hasJobText, 'Expected startWizardFromUpload to pass job_posting_text from state');
  assert.ok(hasClientContext, 'Expected startWizardFromUpload to pass client_context.fast_path_profile');
});
