import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('wizard UI: language options are visible (disabled via UI) and stepper can request back navigation', () => {
  const src = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf-8');
  const stageSrc = readFileSync(new URL('../app/cv/sections/WizardStageSection.tsx', import.meta.url), 'utf-8');

  assert.ok(stageSrc.includes('LANGUAGE_SELECTION'), 'Expected LANGUAGE_SELECTION stage handling in UI');
  assert.ok(stageSrc.includes('LANGUAGE_SELECT_DE'), 'Expected DE language action to be present');
  assert.ok(!stageSrc.includes('Coming soon'), 'Expected no Coming soon copy for language actions');
  assert.ok(stageSrc.includes('WIZARD_GOTO_STAGE'), 'Expected stepper to call WIZARD_GOTO_STAGE for back navigation');
  assert.ok(stageSrc.includes('Nowa wersja'), 'Expected Start over / New version button label');
  assert.ok(stageSrc.includes('COVER_LETTER_GENERATE'), 'Expected cover letter generate/download action plumbing');
  assert.ok(stageSrc.includes('Pobierz CV'), 'Expected final CV download label plumbing');
});

