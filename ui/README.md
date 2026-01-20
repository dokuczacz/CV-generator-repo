# CV Generator UI

Minimal Next.js UI for CV Generator - connects directly to Azure Functions backend.

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
- ✅ Direct Azure Functions integration
- ✅ PDF download (base64 decode)
- ✅ Real-time status updates

## Environment

Copy `.env.local`:
```env
NEXT_PUBLIC_AZURE_FUNCTIONS_URL=https://cv-generator-6695.azurewebsites.net/api
NEXT_PUBLIC_AZURE_FUNCTIONS_KEY=cPAXdShMyzLGDhiwjeo9weDy2OZQfLrGpn-nmphSNh_WAzFuCloICA==
```

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
