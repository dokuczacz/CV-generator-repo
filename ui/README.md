# CV Generator UI

Minimal Next.js UI for CV Generator. The UI calls the local Next.js API route, which proxies to the Python Azure Functions backend.

## Quick Start

```bash
cd ui
npm install
npm run dev
```

Open http://localhost:3000

## Features

- ✅ Minimal UI (only essential fields)
- ✅ DOCX upload for photo extraction
- ✅ Thin API proxy to Azure Functions
- ✅ PDF download (base64 decode)
- ✅ Real-time status updates

## Environment

Use server-side environment variables for backend endpoints and secrets:
```env
AZURE_FUNCTIONS_BASE_URL=http://127.0.0.1:7071/api
OPENAI_API_KEY=your-openai-api-key
OPENAI_PROMPT_ID=your-openai-prompt-id
```

Do not expose Azure Functions keys with `NEXT_PUBLIC_`.

## Structure

```
ui/
├── app/
│   ├── page.tsx          # Main CV generator page
│   ├── layout.tsx        # Root layout
│   └── globals.css       # Minimal styles
├── lib/
│   ├── api.ts            # Azure Functions client
│   ├── types.ts          # TypeScript types from OpenAPI
│   └── utils.ts          # Helper functions
└── .env.local            # Environment config
```

## Why This Approach?

Custom GPT was exporting corrupted PDFs. This standalone UI:
- ✅ Direct file handling (no base64 corruption)
- ✅ Proper blob → download flow
- ✅ Full control over upload/download
- ✅ Local development friendly
