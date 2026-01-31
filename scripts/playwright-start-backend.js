const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const repoRoot = path.resolve(__dirname, '..');

const PORT = process.env.AZURE_FUNCTIONS_PORT || '7071';

const venvPythonWin = path.join(repoRoot, '.venv', 'Scripts', 'python.exe');
const venvPythonPosix = path.join(repoRoot, '.venv', 'bin', 'python');
const venvPython = fs.existsSync(venvPythonWin) ? venvPythonWin : fs.existsSync(venvPythonPosix) ? venvPythonPosix : null;
const venvBinDir = venvPython ? path.dirname(venvPython) : null;

// Make mocked runs deterministic and free.
// For real OpenAI E2E runs (RUN_OPENAI_E2E=1), default to AI enabled.
// (You can always override explicitly via CV_ENABLE_AI=0/1.)
const env = {
  ...process.env,
  CV_ENABLE_AI: process.env.CV_ENABLE_AI ?? (process.env.RUN_OPENAI_E2E === '1' ? '1' : '0'),
  ...(venvPython
    ? {
        // Azure Functions Core Tools doesn’t support Python 3.13 yet.
        // Force it to use the repo virtualenv (3.11) instead of `python` on PATH.
        languageWorkers__python__defaultExecutablePath: venvPython,
        VIRTUAL_ENV: path.join(repoRoot, '.venv'),
        // Ensure `python` resolves to the venv interpreter for Core Tools preflight checks.
        PATH: `${venvBinDir}${path.delimiter}${process.env.PATH || ''}`,
      }
    : {}),
};

const args = ['start', '--port', PORT];

const logDir = path.join(repoRoot, 'tmp', 'logs');
try {
  fs.mkdirSync(logDir, { recursive: true });
} catch {
  // ignore
}
const logPath = path.join(logDir, `func_playwright_${Date.now()}.log`);
const logStream = fs.createWriteStream(logPath, { flags: 'a' });

console.log(`[pw] starting Azure Functions on :${PORT} (logs: ${logPath})`);

const child = spawn('func', args, {
  stdio: ['ignore', 'pipe', 'pipe'],
  env,
  cwd: repoRoot,
  shell: process.platform === 'win32',
});

child.stdout.on('data', (d) => {
  process.stdout.write(d);
  try {
    logStream.write(d);
  } catch {
    // ignore
  }
});

child.stderr.on('data', (d) => {
  process.stderr.write(d);
  try {
    logStream.write(d);
  } catch {
    // ignore
  }
});

const shutdown = (signal) => {
  try {
    child.kill(signal);
  } catch {
    // ignore
  }
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

child.on('exit', (code) => {
  try {
    logStream.end();
  } catch {
    // ignore
  }
  process.exit(code ?? 0);
});
