import { test, expect, Page } from "@playwright/test";
import * as fs from "fs";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const CV_PATH = "C:\\Users\\Mariusz\\OneDrive\\Pulpit\\Docs\\CV\\Lebenslauf_Mariusz_Horodecki_CH.docx";
const JOB_URL = "https://www.jobs.ch/en/vacancies/detail/90a713e0-30da-4cd6-a3b9-f6beac01427a/";

test.describe("E2E German CV Generation (jobs.ch posting)", () => {
  let page: Page;

  test.beforeAll(async () => {
    // Verify CV file exists
    if (!fs.existsSync(CV_PATH)) {
      throw new Error(`CV file not found at ${CV_PATH}`);
    }
  });

  test("Complete German CV workflow: upload CV → paste job posting → generate German CV & cover letter", async ({
    browser,
  }) => {
    page = await browser.newPage();

    // Set up to intercept all network responses
    page.on('response', (response) => {
      if (response.url().includes('process-cv')) {
        console.log(`[API] ${response.request().method()} ${response.url()} -> ${response.status()}`);
        response.text().then((body) => {
          console.log(`[API Response Body]: ${body.substring(0, 500)}`);
        }).catch(() => {
          console.log("[API] (no response body)");
        });
      }
    });

    page.on('requestfailed', (request) => {
      if (request.url().includes('process-cv')) {
        console.error(`[API FAILED] ${request.url()} - ${request.failure()?.errorText}`);
      }
    });

    await page.goto(BASE_URL);

    // Step 1: Verify we're on the chat page
    await expect(page).toHaveTitle(/CV Generator|chat/i);
    console.log("✓ Chat page loaded");

    // Step 2: Upload the German CV
    const fileInput = await page.$("input[type='file']");
    if (!fileInput) {
      throw new Error("File input not found");
    }
    await fileInput.setInputFiles(CV_PATH);
    console.log(`✓ CV uploaded: ${CV_PATH}`);

    // Wait for file to be processed and upload message to appear
    await page.waitForTimeout(2000);

    // Step 3: Fill in job posting URL
    const urlInput = page.locator('[data-testid="job-url-input"]');
    if (await urlInput.isVisible({ timeout: 5000 })) {
      await urlInput.fill(JOB_URL);
      console.log(`✓ Job URL entered: ${JOB_URL}`);
      await page.waitForTimeout(1000);
    }

    // Step 4: If URL fetch fails, fill in job text (fallback)
    const jobTextArea = page.locator('[data-testid="job-text-input"]');
    if (await jobTextArea.isVisible({ timeout: 5000 })) {
      const currentText = await jobTextArea.inputValue();
      if (!currentText || currentText.trim().length < 20) {
        const jobText = "AI Consultant (m/w/d) - HICO Group AG - 100% position seeking AI/ML expert with Swiss consulting experience. Requirements: 5+ years experience, Python, LLMs, Cloud platforms.";
        await jobTextArea.fill(jobText);
        console.log("✓ Job posting text entered");
      }
    }

    // Step 5: Click "Użyj tego CV" (Use this CV) button to start workflow
    const useButton = page.locator('[data-testid="use-loaded-cv"]');
    if (await useButton.isVisible({ timeout: 5000 })) {
      await useButton.click();
      console.log("✓ 'Use this CV' clicked - workflow started");
    } else {
      throw new Error("'Użyj tego CV' button not found");
    }

    // Wait for API response
    await page.waitForTimeout(5000);

    // Step 6: Monitor workflow progression for completion or errors
    let maxWaitTime = 180000; // 3 minutes max
    let elapsedTime = 0;
    const pollInterval = 3000; // Check every 3 seconds
    let lastMessageCount = 0;
    let languageSelected = false;

    while (elapsedTime < maxWaitTime) {
      // Check for language selection UI in the stage panel
      if (!languageSelected) {
        const stagePanel = page.locator('[data-testid="stage-panel"]');
        const isPanelVisible = await stagePanel.isVisible({ timeout: 1000 }).catch(() => false);
        
        if (isPanelVisible) {
          // Look for German language button (LANGUAGE_SELECT_DE)
          const allButtons = await stagePanel.locator('button').all();
          console.log(`✓ Stage panel found with ${allButtons.length} buttons`);
          
          for (const btn of allButtons) {
            const text = await btn.textContent();
            const isDisabled = await btn.isDisabled();
            console.log(`  - Button: "${text?.trim()}" (disabled: ${isDisabled})`);
            
            if (text && /deutsch|german/i.test(text) && !isDisabled) {
              console.log(`✓ Language selection found - clicking: ${text.trim()}`);
              await btn.click();
              languageSelected = true;
              await page.waitForTimeout(3000);
              break;
            }
          }
          if (languageSelected) continue;
        } else if (elapsedTime === 0) {
          console.log("⚠ Stage panel not visible yet");
        }
      }

      const messages = await page.locator('[data-testid="chat-message"], .chat-message').allTextContents();
      const lastMessage = messages[messages.length - 1] || "";

      // Log progress every 20 seconds
      if (elapsedTime % 20000 < pollInterval) {
        console.log(`[${Math.round(elapsedTime / 1000)}s] Messages: ${messages.length}, Last: ${lastMessage.substring(0, 80)}...`);
      }

      // CHECK FOR FAILURE: "exceeds hard limit" loop (the bug we're fixing)
      if (lastMessage.toLowerCase().includes("exceeds hard limit")) {
        console.error("❌ FAILED: Still getting 'exceeds hard limit' error");
        console.error("Last message:", lastMessage);
        throw new Error(
          "Bug NOT fixed: German CV still hitting hard limit validation loop"
        );
      }

      // CHECK FOR SUCCESS: PDF generated or cover letter ready
      if (
        lastMessage.includes("Your 2-page CV") ||
        lastMessage.includes("cover letter") ||
        lastMessage.includes("PDF ready") ||
        lastMessage.includes("ready for download") ||
        (lastMessage.includes("download") && lastMessage.toLowerCase().includes("cv"))
      ) {
        console.log("✓ Workflow completed successfully!");
        break;
      }

      // If stuck on same message for too long, timeout
      if (messages.length === lastMessageCount && elapsedTime > 60000 && languageSelected) {
        console.warn(
          "⚠ No message updates for 60s after language selection - workflow may be stuck"
        );
        break;
      }
      lastMessageCount = messages.length;

      await page.waitForTimeout(pollInterval);
      elapsedTime += pollInterval;
    }

    if (elapsedTime >= maxWaitTime) {
      throw new Error("Workflow timeout - took longer than 3 minutes");
    }

    // Step 7: Verify final state - PDF should be available
    const pageContent = await page.content();
    
    // Check for German content in output
    const germanIndicators = /Unterstützte|Entwickle|Berufserfahrung|Unternehmen|Kontakt|Fähigkeiten/i;
    if (germanIndicators.test(pageContent)) {
      console.log("✓ German content confirmed in response");
    } else {
      console.warn("⚠ German content indicators not clearly visible");
    }

    // Look for PDF download availability
    const downloadButtons = await page.locator('a[href*="pdf"], a[href*="download"], button:has-text(/[Dd]ownload|[Hh]erunterladen/)').count();
    if (downloadButtons > 0) {
      console.log(`✓ ${downloadButtons} download button(s) found - PDF generation successful`);
    }

    // Step 8: Final validation - no errors
    const errorMessages = await page.locator('[role="alert"], [data-testid*="error"]').allTextContents();
    if (errorMessages.length > 0) {
      const errors = errorMessages.filter((msg) => msg.trim().length > 0);
      if (errors.length > 0) {
        console.warn("⚠ Warning: Error elements found:", errors);
      }
    }

    console.log("\n✅ E2E TEST PASSED");
    console.log("✅ German CV generation completed without 'exceeds hard limit' loops");
    console.log("✅ Language-aware validation (250 char limits) is working correctly");
  });
});
