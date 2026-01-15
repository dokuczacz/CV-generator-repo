import { test, expect } from '@playwright/test';
import { existsSync, readdirSync } from 'fs';
import { resolve } from 'path';

const TEST_HTML = resolve(__dirname, 'test-output', 'preview.html');
const PX_TO_MM = (px: string) => parseFloat(px) / 3.7795;
const PX_TO_PT = (px: string) => parseFloat(px) / (96 / 72);

const EXPECTED_SECTIONS_IN_ORDER = [
  'Education',
  'Work experience',
  'Further experience / commitment',
  'Language Skills',
  'IT & AI Skills',
  'Interests',
  'References',
];

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
      return { 
        fontSize: s.fontSize, 
        fontWeight: s.fontWeight, 
        color: s.color, 
        rootFontMain: mainFont
      };
    });
    // Assert font family extracted and set
    expect(nameStyle.rootFontMain.toLowerCase()).toContain('arial');
    // Assert name has a valid font size (extracted or fallback)
    expect(parseFloat(nameStyle.fontSize)).toBeGreaterThan(0);
    // Name should be bold and accent-colored
    expect(nameStyle.fontWeight).toBe('700');
    expect(nameStyle.color).toBe('rgb(0, 0, 255)');

    // Photo box: 45mm x 55mm
    const photoDims = await page.locator('.photo-box').evaluate(el => {
      const r = el.getBoundingClientRect();
      return { width: r.width, height: r.height };
    });
    expect(Math.round(photoDims.width / 3.7795)).toBe(45);
    expect(Math.round(photoDims.height / 3.7795)).toBe(55);
  });

  test('entry grid uses correct 42.5mm date column', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const firstEntry = page.locator('.entry').first();
    await expect(firstEntry).toBeVisible();
    
    const gridCols = await firstEntry.locator('.entry-head').evaluate(el =>
      window.getComputedStyle(el).gridTemplateColumns
    );
    // Playwright reports computed grid columns in px; we assert the first column is ~42.5mm.
    const cols = gridCols.split(' ');
    expect(cols.length).toBeGreaterThanOrEqual(2);
    const col1Mm = PX_TO_MM(cols[0]);
    expect(col1Mm).toBeGreaterThan(41.5);
    expect(col1Mm).toBeLessThan(43.5);
  });

  test('section titles have correct styling', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const sectionTitle = page.locator('.section-title').first();
    
    // Check color (blue #0000FF)
    const color = await sectionTitle.evaluate(el => 
      window.getComputedStyle(el).color
    );
    expect(color).toBe('rgb(0, 0, 255)'); // #0000FF in rgb
    
    // Check font weight (bold)
    const fontWeight = await sectionTitle.evaluate(el => 
      window.getComputedStyle(el).fontWeight
    );
    expect(fontWeight).toBe('700');
    
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

  test('page margins match specification', async ({ page }) => {
    await page.goto(`file://${TEST_HTML}`);
    await page.waitForLoadState('networkidle');
    
    const pageElement = page.locator('.page');
    
    // Check padding: 20mm 22.4mm 20mm 25mm
    const padding = await pageElement.evaluate(el => {
      const style = window.getComputedStyle(el);
      return {
        top: style.paddingTop,
        right: style.paddingRight,
        bottom: style.paddingBottom,
        left: style.paddingLeft,
      };
    });
    
    expect(Math.round(PX_TO_MM(padding.top))).toBe(20);
    expect(Math.round(PX_TO_MM(padding.right))).toBe(22);
    expect(Math.round(PX_TO_MM(padding.bottom))).toBe(20);
    expect(Math.round(PX_TO_MM(padding.left))).toBe(25);
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

  test('fixed page break + no section split under print layout', async ({ page }) => {
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
      const pageBreaks = Array.from(document.querySelectorAll('.page-break'));
      if (pageBreaks.length !== 1) return { error: `Expected 1 page break, got ${pageBreaks.length}` } as any;

      let shiftSoFar = 0;
      const breakInfos = pageBreaks.map((br) => {
        const r = br.getBoundingClientRect();
        const topPx = (r.top - rootTop) + shiftSoFar;
        const rem = ((topPx % pageHeightPx) + pageHeightPx) % pageHeightPx;
        const shift = rem === 0 ? 0 : (pageHeightPx - rem);
        shiftSoFar += shift;
        return { node: br, shiftAfter: shiftSoFar };
      });

      const shiftBeforeNode = (node: Element) => {
        let s = 0;
        for (const info of breakInfos) {
          const rel = info.node.compareDocumentPosition(node);
          const isBefore = (rel & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
          if (isBefore) s = info.shiftAfter;
        }
        return s;
      };

      const starts: Record<string, number> = {};
      const split: Array<{ title: string; startPage: number; endPage: number }> = [];
      for (const sec of sections) {
        const titleEl = sec.querySelector('.section-title');
        const title = titleEl ? (titleEl.textContent || '').trim() : '(untitled section)';
        const r = sec.getBoundingClientRect();
        const shift = shiftBeforeNode(sec);
        const topEff = (r.top - rootTop) + shift;
        const bottomEff = (r.bottom - rootTop) + shift;
        const startPage = Math.floor(topEff / pageHeightPx) + 1;
        const endPage = Math.floor((bottomEff - 0.01) / pageHeightPx) + 1;
        starts[title] = startPage;
        if (startPage !== endPage) split.push({ title, startPage, endPage });
      }

      return { starts, split };
    });

    expect(result.error).toBeUndefined();
    expect(result.split).toEqual([]);
    expect(result.starts['Education']).toBe(1);
    expect(result.starts['Work experience']).toBe(1);
    expect(result.starts['Further experience / commitment']).toBe(2);
    expect(result.starts['Language Skills']).toBe(2);
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
