import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const SAMPLE_CV = path.join(__dirname, '../samples/Lebenslauf_Mariusz_Horodecki_CH.docx');

test.describe('CV Generator E2E', () => {
  
  test('should load chat interface', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Check for main elements
    await expect(page.locator('h1')).toContainText('CV Generator');
    await expect(page.locator('input[type="file"]')).toBeVisible();
    await expect(page.locator('textarea')).toBeVisible();
  });

  test('should upload CV and create session', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Upload file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_CV);
    
    // Wait for upload to complete
    await expect(page.locator('text=/Session created|Uploaded|Processing/')).toBeVisible({ timeout: 30000 });
    
    // Check for session indicator
    await expect(page.locator('text=/session|Session ID/')).toBeVisible();
  });

  test('should generate PDF through chat', async ({ page }) => {
    test.setTimeout(120000); // 2 minutes for full flow
    
    await page.goto(BASE_URL);
    
    // Upload CV
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_CV);
    await page.waitForTimeout(3000);
    
    // Send generate message
    const messageInput = page.locator('textarea');
    await messageInput.fill('Generate the PDF now');
    await messageInput.press('Enter');
    
    // Wait for PDF generation
    await expect(page.locator('text=/PDF generated|Download PDF|generated successfully/')).toBeVisible({ 
      timeout: 90000 
    });
    
    // Check for download button or link
    const downloadLink = page.locator('a[href*="pdf"], button:has-text("Download")');
    await expect(downloadLink.first()).toBeVisible();
  });

  test('should handle edit intent', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Upload CV
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(SAMPLE_CV);
    await page.waitForTimeout(3000);
    
    // Send edit request
    const messageInput = page.locator('textarea');
    await messageInput.fill('Change my work experience');
    await messageInput.press('Enter');
    
    // Should transition to review mode
    await expect(page.locator('text=/review|Review|edit mode|Edit Mode/')).toBeVisible({ 
      timeout: 30000 
    });
  });

  test('should validate error handling', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Try to generate without uploading
    const messageInput = page.locator('textarea');
    await messageInput.fill('Generate PDF');
    await messageInput.press('Enter');
    
    // Should show error or instruction to upload
    await expect(page.locator('text=/upload|Upload|session|Session/')).toBeVisible({ 
      timeout: 10000 
    });
  });

});

test.describe('CV Generator API Integration', () => {
  
  test('should call health endpoint', async ({ request }) => {
    const response = await request.get(`${process.env.AZURE_FUNCTIONS_URL || 'http://localhost:7071'}/api/health`);
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(data.status).toBe('healthy');
  });

  test('should handle cleanup endpoint', async ({ request }) => {
    const response = await request.post(
      `${process.env.AZURE_FUNCTIONS_URL || 'http://localhost:7071'}/api/cv-tool-call-handler`,
      {
        data: {
          tool_name: 'cleanup_expired_sessions',
          params: {}
        }
      }
    );
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.success).toBeTruthy();
  });

});
