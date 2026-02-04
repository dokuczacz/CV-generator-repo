import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('wizard UI: language options are visible (disabled via UI) and stepper can request back navigation', () => {
  const src = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf-8');

  assert.ok(src.includes('LANGUAGE_SELECTION'), 'Expected LANGUAGE_SELECTION stage handling in UI');
  assert.ok(src.includes('Coming soon'), 'Expected Coming soon copy for disabled languages');
  assert.ok(src.includes('WIZARD_GOTO_STAGE'), 'Expected stepper to call WIZARD_GOTO_STAGE for back navigation');
  assert.ok(src.includes('Nowa wersja'), 'Expected Start over / New version button label');
});

