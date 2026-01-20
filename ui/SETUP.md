# CV Generator UI - Environment Variables

## Required Configuration

### 1. Add your OpenAI API Key

Edit `ui/.env.local` and replace the empty `OPENAI_API_KEY`:

```env
OPENAI_API_KEY=sk-proj-...your-key-here...
```

Get your API key from: https://platform.openai.com/api-keys

### 2. Azure Functions (Already Configured)

```env
NEXT_PUBLIC_AZURE_FUNCTIONS_URL=https://cv-generator-6695.azurewebsites.net/api
NEXT_PUBLIC_AZURE_FUNCTIONS_KEY=cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==
```

### 3. OpenAI Prompt ID (Already Set)

```env
OPENAI_PROMPT_ID=pmpt_696f593c42148195ab41b3a3aaeaa55d029c2c08c553971f
```

## How to Run

```bash
cd ui
npm install  # Already done
npm run dev  # Start dev server
```

Open http://localhost:3000

## Features Now Available

✅ **AI-Powered CV Extraction** - Paste CV text → AI extracts structured data  
✅ **Manual Form Input** - Fill fields manually  
✅ **DOCX Photo Upload** - Extract photo from uploaded DOCX  
✅ **PDF Generation** - Azure Functions backend  
✅ **Direct Download** - No corrupted files!

## Usage Flow

1. **Option A: AI Extraction**
   - Paste CV text in prompt field
   - Click "Extract CV Data with AI"
   - AI fills the form automatically

2. **Option B: Manual Input**
   - Fill form fields manually
   - Skip AI extraction

3. **Generate PDF**
   - (Optional) Upload DOCX for photo
   - Click "Generate CV PDF"
   - Download starts automatically
