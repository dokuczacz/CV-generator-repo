import { test, expect } from '@playwright/test';
import { existsSync, readdirSync } from 'fs';
import { resolve } from 'path';

const TEST_HTML = resolve(__dirname, 'test-output', 'preview.html');
const FUNCTIONS_BASE_URL = process.env.CV_FUNCTIONS_BASE_URL || 'http://localhost:7071/api';
const PX_TO_MM = (px: string) => parseFloat(px) / 3.7795;
const PX_TO_PT = (px: string) => parseFloat(px) / (96 / 72);

const EXPECTED_SECTIONS_IN_ORDER = [
  'Work experience',
  'IT & AI Skills',
  'Technical & Operational Skills',
  'Education',
  'Language Skills',
  'Interests',
  'References',
];

test.describe('Local Functions API Smoke', () => {
  test('health endpoint responds', async ({ request }) => {
    const res = await request.get(`${FUNCTIONS_BASE_URL}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe('healthy');
  });

  test('cv-tool-call-handler rejects missing tool_name', async ({ request }) => {
    const res = await request.post(`${FUNCTIONS_BASE_URL}/cv-tool-call-handler`, {
      data: { tool_name: '', session_id: '', params: {} },
    });
    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(body.error).toBe('tool_name is required');
  });
});

test.describe('CV Template Visual Regression', () => {
  
  test('rendered HTML loads', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
  });

  test('header geometry and typography match template', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    // Check header elements
    await expect(page.locator('.name')).toBeVisible();
    await expect(page.locator('.contact')).toBeVisible();
    await expect(page.locator('.photo-box')).toBeVisible();
    await expect(page.locator('.photo-box img')).toBeVisible();

    const imgSrc = await page.locator('.photo-box img').getAttribute('src');
    expect(imgSrc || '').toContain('data:image/');

    // Name: verify extracted styles injected via CSS variables and direct styles
    const nameStyle = await page.locator('.name').evaluate(el => {
      const s = window.getComputedStyle(el);
      const root = window.getComputedStyle(document.documentElement);
      const mainFont = root.getPropertyValue('--font-main');
      const rootText = root.getPropertyValue('--text');

      // Convert a CSS color (hex or var) to computed rgb(...) via a temporary element.
      const toRgb = (value: string) => {
        const tmp = document.createElement('div');
        tmp.style.color = value;
        document.body.appendChild(tmp);
        const rgb = window.getComputedStyle(tmp).color;
        tmp.remove();
        return rgb;
      };

      const expectedTextRgb = toRgb(rootText);
      return { 
        fontSize: s.fontSize, 
        fontWeight: s.fontWeight, 
        color: s.color, 
        rootFontMain: mainFont,
        expectedTextRgb,
      };
    });
    // Assert font family extracted and set
    expect(nameStyle.rootFontMain.toLowerCase()).toContain('arial');
    // Assert name has a valid font size (extracted or fallback)
    expect(parseFloat(nameStyle.fontSize)).toBeGreaterThan(0);
    // Name should be bold and use the template's --text color
    expect(nameStyle.fontWeight).toBe('700');
    expect(nameStyle.color).toBe(nameStyle.expectedTextRgb);

    // Photo box: 45mm x 55mm
    const photoDims = await page.locator('.photo-box').evaluate(el => {
      const r = el.getBoundingClientRect();
      return { width: r.width, height: r.height };
    });
    expect(Math.round(photoDims.width / 3.7795)).toBe(45);
    expect(Math.round(photoDims.height / 3.7795)).toBe(55);
  });

  test('entry layout uses correct 42.5mm date column (flexbox)', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');

    const firstEntry = page.locator('.entry').first();
    await expect(firstEntry).toBeVisible();

    // Check flexbox layout with date column width
    const dateWidth = await firstEntry.locator('.entry-head .entry-date').evaluate(el => {
      const style = window.getComputedStyle(el);
      return style.width;
    });

    // Date column should be 42.5mm (migrated from grid to flexbox)
    const dateWidthMm = PX_TO_MM(dateWidth);
    expect(dateWidthMm).toBeGreaterThan(41.5);
    expect(dateWidthMm).toBeLessThan(43.5);

    // Verify flexbox layout
    const display = await firstEntry.locator('.entry-head').evaluate(el =>
      window.getComputedStyle(el).display
    );
    expect(display).toBe('flex');
  });

  test('section titles have correct styling', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const sectionTitle = page.locator('.section-title').first();
    
    const { color, expectedAccentRgb } = await sectionTitle.evaluate(el => {
      const root = window.getComputedStyle(document.documentElement);
      const accent = root.getPropertyValue('--accent');

      const toRgb = (value: string) => {
        const tmp = document.createElement('div');
        tmp.style.color = value;
        document.body.appendChild(tmp);
        const rgb = window.getComputedStyle(tmp).color;
        tmp.remove();
        return rgb;
      };

      return {
        color: window.getComputedStyle(el).color,
        expectedAccentRgb: toRgb(accent),
      };
    });
    expect(color).toBe(expectedAccentRgb);
    
    // Check font weight
    const fontWeight = await sectionTitle.evaluate(el => 
      window.getComputedStyle(el).fontWeight
    );
    expect(fontWeight).toBe('600');
    
    // Check small caps
    const fontVariant = await sectionTitle.evaluate(el => 
      window.getComputedStyle(el).fontVariant
    );
    expect(fontVariant).toContain('small-caps');
  });

  test('PDF artifact exists (preview or locked-fallback)', async () => {
    const outputDir = resolve(__dirname, 'test-output');
    const testPdf = resolve(outputDir, 'preview.pdf');
    const altTestPdf = resolve(outputDir, 'preview.generated.pdf');
    const anyGenerated = readdirSync(outputDir).some(name => name.startsWith('preview.generated-') && name.endsWith('.pdf'));
    expect(existsSync(testPdf) || existsSync(altTestPdf) || anyGenerated).toBeTruthy();
  });

  test('page container has no padding (margins handled by @page)', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');

    const pageElement = page.locator('.page').first();

    // In the new natural flow layout, .page has no padding
    // Margins are controlled by @page rules (20mm 22.4mm 20mm 25mm)
    // which are applied by WeasyPrint during PDF generation
    const padding = await pageElement.evaluate(el => {
      const style = window.getComputedStyle(el);
      return {
        top: style.paddingTop,
        right: style.paddingRight,
        bottom: style.paddingBottom,
        left: style.paddingLeft,
      };
    });

    // All padding should be 0 (or very close to 0)
    expect(Math.round(PX_TO_MM(padding.top))).toBe(0);
    expect(Math.round(PX_TO_MM(padding.right))).toBe(0);
    expect(Math.round(PX_TO_MM(padding.bottom))).toBe(0);
    expect(Math.round(PX_TO_MM(padding.left))).toBe(0);

    // Verify .page is only a width container
    const width = await pageElement.evaluate(el => {
      return window.getComputedStyle(el).width;
    });
    expect(Math.round(PX_TO_MM(width))).toBe(210); // A4 width
  });

  test('bullets use correct indentation', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const bullets = page.locator('.bullets');
    await expect(bullets.first()).toBeVisible();
    
    // Check padding-left (~5mm, per Golden Rules)
    const paddingLeft = await bullets.first().evaluate(el => 
      window.getComputedStyle(el).paddingLeft
    );
    expect(Math.round(PX_TO_MM(paddingLeft))).toBe(5);
  });

  test('document contains expected sections in exact order', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const sections = await page.locator('.section-title').allTextContents();
    expect(sections.map(s => s.trim())).toEqual(EXPECTED_SECTIONS_IN_ORDER);
  });

  test('natural flow pagination - sections on expected pages', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    await page.emulateMedia({ media: 'print' });

    const result = await page.evaluate(() => {
      const MM_TO_PX = 3.7795275591;
      const pageHeightPx = 297 * MM_TO_PX;

      const root = document.querySelector('.page');
      if (!root) return { error: 'Missing .page root' } as any;
      const rootTop = root.getBoundingClientRect().top;

      const sections = Array.from(document.querySelectorAll('section.section'));

      const starts: Record<string, number> = {};
      const sectionInfo: Array<{ title: string; startPage: number; endPage: number; height: number }> = [];

      for (const sec of sections) {
        const titleEl = sec.querySelector('.section-title');
        const title = titleEl ? (titleEl.textContent || '').trim() : '(untitled section)';
        const r = sec.getBoundingClientRect();
        const topPx = r.top - rootTop;
        const bottomPx = r.bottom - rootTop;
        const heightPx = r.height;

        // Calculate which page(s) this section appears on
        // Note: @page margins are handled by WeasyPrint, not included in getBoundingClientRect
        const startPage = Math.floor(topPx / pageHeightPx) + 1;
        const endPage = Math.floor((bottomPx - 0.01) / pageHeightPx) + 1;

        starts[title] = startPage;
        sectionInfo.push({ title, startPage, endPage, height: Math.round(heightPx) });
      }

      return { starts, sectionInfo };
    });

    expect(result.error).toBeUndefined();

    // Core sections should start on page 1
    expect(result.starts['Education']).toBe(1);
    expect(result.starts['Work experience']).toBe(1);

    // Later sections typically start on page 2 (but may vary based on content length)
    // We don't enforce exact page numbers for all sections since natural flow allows flexibility

    // Log section info for debugging
    console.log('Section layout:', JSON.stringify(result.sectionInfo, null, 2));
  });
});

test.describe('CV Content Validation', () => {
  
  test('full name is visible in header', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const nameElement = page.locator('.name');
    await expect(nameElement).toBeVisible();
    
    const nameText = await nameElement.textContent();
    expect(nameText).toBeTruthy();
    expect(nameText?.length).toBeGreaterThan(0);
  });

  test('contact information is displayed', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const contact = page.locator('.contact');
    await expect(contact).toBeVisible();
    
    const contactText = await contact.textContent();
    expect(contactText).toContain('@'); // email
  });

  test('work experience entries are visible', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const entries = page.locator('.entry');
    const count = await entries.count();
    
    expect(count).toBeGreaterThan(0);
  });

  test('education entries are visible', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const educationSection = page.locator('text=Education').first();
    await expect(educationSection).toBeVisible();
  });
});
