# CV Generator - Testing & Deployment Guide

## 🎯 Project Overview

This CV generator enables a **Custom GPT** to send CV data as JSON to a backend API, which:
1. Receives JSON with CV fields
2. Renders HTML using Jinja2 template
3. Generates PDF via Playwright/Chromium
4. Returns PDF file for download

## 📁 Project Structure

```
CV-generator-repo/
├── src/
│   └── render.py              # Core rendering logic (HTML & PDF)
├── templates/
│   ├── CV_template_2pages_2025.spec.md  # Layout specification
│   └── html/
│       ├── cv_template_2pages_2025.html  # Jinja2 template
│       └── cv_template_2pages_2025.css   # Styling
├── tests/
│   ├── cv-visual.spec.ts      # Playwright visual regression tests
│   └── generate_test_artifacts.py  # Generate test HTML/PDF
├── samples/
│   └── reference_output.pdf   # Reference for comparison
├── wzory/
│   └── CV_template_2pages_2025.docx  # Original DOCX template
├── api.py                     # Flask API endpoint
├── requirements.txt           # Python dependencies
├── package.json              # Node.js dependencies (Playwright)
└── playwright.config.ts      # Playwright configuration
```

## 🚀 Setup Instructions

### 1. Install Python Dependencies
```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Install Node.js Dependencies (for Playwright tests)
```powershell
npm install
```

### 3. Generate Test Artifacts
```powershell
python tests/generate_test_artifacts.py
```

This creates:
- `test-output/preview.html` - Rendered HTML
- `test-output/preview.pdf` - Generated PDF
- `samples/reference_output.pdf` - Reference PDF for comparison

### 4. Run Visual Regression Tests
```powershell
npm test                # Run all tests
npm run test:headed     # Run with browser visible
npm run test:ui         # Interactive UI mode
npm run test:debug      # Debug mode
npm run show-report     # View test report
```

## 🌐 API Usage

### Start the API Server
```powershell
python api.py
```

Server runs on `http://localhost:5000`

### API Endpoints

#### 1. Health Check
```http
GET /health
```

Response:
```json
{"status": "healthy"}
```

#### 2. Generate CV PDF
```http
POST /generate-cv
Content-Type: application/json

{
  "full_name": "John Doe",
  "email": "john@example.com",
  "address_lines": ["Street 123", "City"],
  "phone": "+1234567890",
  "nationality": "American",
  "profile": "Professional summary...",
  "work_experience": [
    {
      "date_range": "2020-2024",
      "employer": "Company Inc",
      "location": "New York",
      "title": "Senior Engineer",
      "bullets": ["Achievement 1", "Achievement 2"]
    }
  ],
  "education": [...],
  "languages": ["English", "Spanish"],
  "it_ai_skills": [...],
  "trainings": [...],
  "interests": "...",
  "data_privacy": "..."
}
```

Response: PDF file download

#### 3. Preview HTML
```http
POST /preview-html
Content-Type: application/json

{...same CV data...}
```

Response: HTML content

### Example cURL Request
```bash
curl -X POST http://localhost:5000/generate-cv \
  -H "Content-Type: application/json" \
  -d @sample_cv.json \
  --output cv_output.pdf
```

## 🤖 Custom GPT Integration

### GPT Configuration

**Instructions for Custom GPT:**
```
You are a CV generator assistant. When the user provides their CV information:

1. Collect all required fields:
   - full_name, email (required)
   - address_lines, phone, nationality
   - profile (summary)
   - work_experience (list of jobs with date_range, employer, title, bullets)
   - education (list with date_range, institution, title, details)
   - languages, it_ai_skills, trainings
   - interests, data_privacy

2. Format as JSON matching the schema

3. Send POST request to: https://your-backend-url.com/generate-cv

4. Provide download link to the user
```

**Actions Schema (for GPT):**
```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "CV Generator API",
    "version": "1.0.0"
  },
  "servers": [
    {"url": "https://your-backend-url.com"}
  ],
  "paths": {
    "/generate-cv": {
      "post": {
        "operationId": "generateCV",
        "summary": "Generate CV PDF from JSON data",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["full_name", "email"],
                "properties": {
                  "full_name": {"type": "string"},
                  "email": {"type": "string"},
                  "address_lines": {"type": "array", "items": {"type": "string"}},
                  "phone": {"type": "string"},
                  "nationality": {"type": "string"},
                  "profile": {"type": "string"},
                  "work_experience": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "date_range": {"type": "string"},
                        "employer": {"type": "string"},
                        "location": {"type": "string"},
                        "title": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}}
                      }
                    }
                  },
                  "education": {"type": "array"},
                  "languages": {"type": "array", "items": {"type": "string"}},
                  "it_ai_skills": {"type": "array", "items": {"type": "string"}},
                  "trainings": {"type": "array", "items": {"type": "string"}},
                  "interests": {"type": "string"},
                  "data_privacy": {"type": "string"}
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "PDF file",
            "content": {
              "application/pdf": {}
            }
          }
        }
      }
    }
  }
}
```

## 🧪 Playwright Testing

### What Tests Check

1. **Layout Structure**
   - Page margins (20mm, 22.4mm, 20mm, 25mm)
   - Section order and presence
   - Grid layout (42.5mm + 1fr columns)

2. **Visual Styling**
   - Section titles: blue (#0000FF), bold, small-caps
   - Font family: Arial
   - Bullet indentation: 6mm padding-left

3. **Visual Regression**
   - Screenshot comparison of full page
   - Header section snapshot
   - Work experience entry snapshot

4. **PDF Output**
   - PDF file generation
   - File size validation

### Running Specific Tests
```powershell
# Run only visual tests
npx playwright test cv-visual

# Run specific test
npx playwright test -g "header section renders correctly"

# Update snapshots (after intentional changes)
npx playwright test --update-snapshots
```

## 📊 Comparison Workflow

### Comparing Template vs Output

1. **Generate reference output:**
   ```powershell
   python tests/generate_test_artifacts.py
   ```

2. **Run visual tests:**
   ```powershell
   npm test
   ```

3. **Review differences:**
   - Check `test-results/` for failure screenshots
   - Compare `test-output/preview.pdf` with `samples/reference_output.pdf`
   - Use Playwright Test extension in VS Code to see visual diffs

4. **Manual PDF comparison:**
   - Open both PDFs side-by-side
   - Check layout alignment
   - Verify fonts, colors, spacing

### Using VS Code Playwright Extension

The **Playwright Test for VSCode** extension is installed. Usage:

1. Open Testing sidebar (beaker icon)
2. See all tests from `tests/cv-visual.spec.ts`
3. Click play button to run tests
4. See visual diffs directly in VS Code
5. Accept/reject snapshot changes

## 🔧 Development Workflow

### Making Template Changes

1. Edit `templates/html/cv_template_2pages_2025.html` or `.css`
2. Regenerate test artifacts:
   ```powershell
   python tests/generate_test_artifacts.py
   ```
3. Run tests to see differences:
   ```powershell
   npm test
   ```
4. Update snapshots if changes are intentional:
   ```powershell
   npx playwright test --update-snapshots
   ```

### Adding New Sections

1. Update template HTML
2. Update sample data in `tests/generate_test_artifacts.py`
3. Add test cases in `tests/cv-visual.spec.ts`
4. Regenerate and test

## 🚀 Deployment

### Option 1: Local Server
```powershell
python api.py
# Runs on http://localhost:5000
```

### Option 2: Production Server (e.g., Railway, Render, Fly.io)

**Procfile:**
```
web: gunicorn api:app
```

**Additional requirement:**
```
gunicorn>=21.0.0
```

**Environment variables:**
```
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
```

### Option 3: Serverless (AWS Lambda, Azure Functions)

Requires additional setup for Playwright in serverless environment.

## 📝 JSON Schema Example

Complete example in `samples/sample_cv.json`:
```json
{
  "full_name": "John Doe",
  "address_lines": ["Street 123", "12345 City"],
  "phone": "+1 234 567 890",
  "email": "john.doe@example.com",
  "nationality": "American",
  "profile": "Experienced professional with...",
  "work_experience": [
    {
      "date_range": "2020-01 – Present",
      "employer": "Tech Corp",
      "location": "New York, USA",
      "title": "Senior Software Engineer",
      "bullets": [
        "Led team of 5 developers",
        "Implemented CI/CD pipeline",
        "Reduced deployment time by 50%"
      ]
    }
  ],
  "education": [
    {
      "date_range": "2015-2019",
      "institution": "University of Tech",
      "title": "Bachelor of Science in Computer Science",
      "details": ["GPA: 3.8/4.0", "Dean's List"]
    }
  ],
  "languages": ["English (native)", "Spanish (fluent)"],
  "it_ai_skills": [
    "Python, JavaScript, TypeScript",
    "React, Node.js, Django",
    "AWS, Docker, Kubernetes"
  ],
  "trainings": [
    "2023 – AWS Certified Solutions Architect",
    "2022 – Docker & Kubernetes Masterclass"
  ],
  "interests": "Open source contribution, hiking, photography",
  "data_privacy": "I consent to the processing of my personal data for recruitment purposes."
}
```

## ✅ Definition of Done

- [x] Backend renders HTML from JSON
- [x] Backend generates PDF via Playwright
- [x] Flask API with `/generate-cv` endpoint
- [x] Playwright tests for visual regression
- [x] Test artifacts generation script
- [ ] Deploy API to production server
- [ ] Configure Custom GPT with API endpoint
- [ ] Test end-to-end flow (GPT → API → PDF)

## 🐛 Troubleshooting

### Playwright Browser Issues
```powershell
python -m playwright install chromium --with-deps
```

### PDF Not Generating
- Check Chromium installation
- Verify CSS is inlined
- Check for JavaScript errors in console

### Tests Failing
- Regenerate test artifacts
- Update snapshots if changes are intentional
- Check screen resolution (tests use specific dimensions)

## 📚 Additional Resources

- [Playwright Documentation](https://playwright.dev)
- [Jinja2 Template Guide](https://jinja.palletsprojects.com)
- [Flask Documentation](https://flask.palletsprojects.com)
- [Custom GPT Actions Guide](https://platform.openai.com/docs/actions)
