import { expect, type Page } from '@playwright/test';

export type StageStep = {
  name: string;
  actionId: string;
  expectedStages: string[];
  timeoutMs?: number;
  beforeAction?: () => Promise<void>;
};

export async function getWizardStage(page: Page): Promise<string> {
  return page
    .getByTestId('stage-panel')
    .getAttribute('data-wizard-stage')
    .then((v) => (v || '').trim())
    .catch(() => '');
}

export async function waitForStagePanel(page: Page, timeoutMs = 30_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const panel = page.getByTestId('stage-panel');
    if (await panel.isVisible().catch(() => false)) {
      const stage = await panel.getAttribute('data-wizard-stage').then((v) => (v || '').trim()).catch(() => '');
      if (stage) return;
    }
    await page.waitForTimeout(150);
  }
  throw new Error('Timed out waiting for active stage panel (data-wizard-stage is empty)');
}

export async function waitForStageOneOf(page: Page, stages: string[], timeoutMs = 30_000): Promise<string> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const stage = await getWizardStage(page);
    if (stage && stages.includes(stage)) return stage;
    await page.waitForTimeout(150);
  }
  throw new Error(`Timed out waiting for stage in: ${stages.join(', ')}`);
}

export async function clickAction(page: Page, actionId: string, timeoutMs = 30_000): Promise<void> {
  const panel = page.getByTestId('stage-panel');
  const button = panel.getByTestId(`action-${actionId}`);

  if (!(await button.isVisible().catch(() => false))) {
    const more = panel.getByText('Więcej akcji').first();
    if (await more.isVisible().catch(() => false)) {
      await more.click();
    }
  }

  await expect(button).toBeVisible({ timeout: timeoutMs });
  await expect(button).toBeEnabled({ timeout: timeoutMs });

  const reqPromise = page.waitForRequest(
    (req) =>
      req.url().includes('/api/process-cv') &&
      req.method() === 'POST' &&
      String(req.postData() || '').includes(actionId),
    { timeout: timeoutMs }
  );

  await button.scrollIntoViewIfNeeded().catch(() => undefined);
  await button.click();
  await reqPromise;
}

export async function enforceNoStuck(
  page: Page,
  state: { lastStage: string; sameStageCount: number },
  maxSameStage: number
): Promise<void> {
  const currentStage = await getWizardStage(page);
  if (!currentStage) return;

  if (currentStage === state.lastStage) {
    state.sameStageCount += 1;
  } else {
    state.lastStage = currentStage;
    state.sameStageCount = 1;
  }

  if (state.sameStageCount > maxSameStage) {
    throw new Error(`No progress: stage '${currentStage}' repeated ${state.sameStageCount} times`);
  }
}
