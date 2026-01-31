import fs from 'fs';
import path from 'path';

/**
 * Parse capture-responses.jsonl into individual fixture files
 * Run: npx ts-node tests/parse-capture.ts
 */

const CAPTURE_FILE = path.join(__dirname, 'capture-responses.jsonl');
const FIXTURES_DIR = path.join(__dirname, 'fixtures');

if (!fs.existsSync(CAPTURE_FILE)) {
  console.error(`❌ No capture file found: ${CAPTURE_FILE}`);
  console.error('Run: npm test -- tests/e2e/capture-fixtures.spec.ts');
  process.exit(1);
}

console.log(`📂 Reading captures from: ${CAPTURE_FILE}`);

const lines = fs.readFileSync(CAPTURE_FILE, 'utf-8').split('\n').filter(l => l.trim());
const responses = lines.map((line, idx) => {
  try {
    return JSON.parse(line);
  } catch (e) {
    console.warn(`⚠️  Line ${idx + 1} invalid JSON, skipping`);
    return null;
  }
}).filter(Boolean);

console.log(`✅ Parsed ${responses.length} responses\n`);

// Group by action ID
const byAction = responses.reduce((acc: Record<string, any>, item: any) => {
  const actionId = item.response?.ui_action?.id || 'unknown';
  acc[actionId] = item.response;
  return acc;
}, {});

// Save each as fixture
let saved = 0;
for (const [actionId, response] of Object.entries(byAction)) {
  const filename = actionId
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '-')
    .replace(/-+/g, '-');

  const filepath = path.join(FIXTURES_DIR, `${filename}.json`);
  
  fs.writeFileSync(filepath, JSON.stringify(response, null, 2));
  console.log(`💾 Saved: ${filename}.json`);
  saved++;
}

console.log(`\n✨ Complete! Saved ${saved} fixtures to ${FIXTURES_DIR}`);
console.log('\n📝 Next: Update tests/e2e/cv-generator-mocked.spec.ts with new fixtures');
console.log('   const fixtures = {');
Object.keys(byAction).forEach(actionId => {
  const filename = actionId
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '-')
    .replace(/-+/g, '-');
  console.log(`     ${actionId}: loadFixture('${filename}'),`);
});
console.log('   };');
