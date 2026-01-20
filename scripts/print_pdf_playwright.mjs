import { chromium } from 'playwright';
import path from 'path';
import process from 'process';
import { pathToFileURL } from 'url';

const [,, htmlPathArg, pdfPathArg] = process.argv;

if (!htmlPathArg || !pdfPathArg) {
  console.error('Usage: node scripts/print_pdf_playwright.mjs <input.html> <output.pdf>');
  process.exit(2);
}

const htmlPath = path.resolve(htmlPathArg);
const pdfPath = path.resolve(pdfPathArg);

const url = pathToFileURL(htmlPath).toString();

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.emulateMedia({ media: 'print' });

  await page.pdf({
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    margin: {
      top: '0mm',
      right: '0mm',
      bottom: '0mm',
      left: '0mm',
    },
  });
} finally {
  await browser.close();
}
