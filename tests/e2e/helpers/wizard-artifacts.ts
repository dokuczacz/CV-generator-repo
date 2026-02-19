import fs from 'fs';
import path from 'path';
import type { TestInfo } from '@playwright/test';

export type StageProgressEntry = {
  step: number;
  stageBefore: string;
  actionId: string;
  stageAfter: string;
  elapsedMs: number;
};

export async function writeStageProgressArtifact(
  testInfo: TestInfo,
  sessionId: string,
  entries: StageProgressEntry[]
): Promise<void> {
  const outDir = path.join(process.cwd(), 'artifacts', 'e2e');
  fs.mkdirSync(outDir, { recursive: true });

  const outPath = path.join(outDir, `playwright_stage_progress_${sessionId || 'unknown'}.json`);
  const payload = {
    session_id: sessionId,
    generated_at_utc: new Date().toISOString(),
    steps: entries,
  };

  fs.writeFileSync(outPath, JSON.stringify(payload, null, 2), 'utf-8');
  await testInfo.attach('stage-progress', {
    path: outPath,
    contentType: 'application/json',
  });
}
