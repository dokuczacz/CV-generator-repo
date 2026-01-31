const { spawn } = require('child_process');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');

const child = spawn('npm', ['run', 'dev'], {
  stdio: 'inherit',
  cwd: path.join(repoRoot, 'ui'),
  env: process.env,
  shell: process.platform === 'win32',
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
  process.exit(code ?? 0);
});
