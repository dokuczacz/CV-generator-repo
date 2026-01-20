# 🎯 CV Generator UI Migration Plan
## Custom GPT → Standalone Next.js UI

**Problem**: Custom GPT eksportuje uszkodzone pliki PDF  
**Rozwiązanie**: Standalone Next.js UI z bezpośrednim wywołaniem Azure Functions

---

## 📊 Analiza Dostępnych UI Templates

### Option A: `ui_next` (Minimalistic)
**Lokalizacja**: `C:\Users\Mariusz\OneDrive\Dokumenty\GitHub\OmniFlowBeta\ui_next`

✅ **Zalety**:
- Bardzo prosty (~462B package.json, tylko Next.js 14 + React 18)
- Gotowy layout z sidebar + main panel + right panel
- Obsługa multi-user via `X-User-Id` header
- Real-time status messages i error handling
- Historia interakcji z tool calls
- Backend URL configurable via `.env`

❌ **Wady**:
- Brak file upload/download UI (wymaga dodania)
- Brak komponentów UI (trzeba dodać shadcn/ui)
- Minimalna stylizacja

**Stack**:
```json
{
  "next": "14.2.5",
  "react": "18.3.1",
  "react-dom": "18.3.1"
}
```

---

### Option B: `ai-chatbot` (Full-featured)
**Lokalizacja**: `C:\AI memory\NewHope\OmniFlowBeta\ai-chatbot`

✅ **Zalety**:
- Pełny stack UI komponentów (Radix UI, shadcn/ui)
- File upload/download built-in
- Auth system (NextAuth)
- Code editor (CodeMirror)
- Markdown rendering (prosemirror)
- Data grid (react-data-grid)
- Real-time collaboration
- Vercel AI SDK integration

❌ **Wady**:
- Ogromny package (~100+ dependencies)
- Over-engineered dla prostego CV generatora
- Wymaga cleanup niepotrzebnych features

**Stack**:
```json
{
  "next": "16.0.10",
  "react": "19.0.1",
  "@ai-sdk/react": "3.0.0-beta.162",
  "@radix-ui/*": "latest",
  "next-auth": "5.0.0-beta.25"
}
```

---

## 🎯 Rekomendacja: **Option A (ui_next) + Customization**

**Uzasadnienie**:
1. ✅ Czysty start - dodajemy tylko to co potrzebne
2. ✅ Architektura zgodna z OmniFlow pattern (sidebar + main + right)
3. ✅ Już ma backend integration via fetch + X-User-Id
4. ✅ Łatwy do utrzymania (mniej dependencies = mniej problemów)
5. ✅ Szybka migracja (~4-6h)

---

## 📋 Wymagania Funkcjonalne

### Must-Have (MVP):
1. **Upload DOCX/PDF** - Drag & drop lub file input
2. **CV Data Form** - Pola dla full_name, email, work_experience, etc.
3. **Backend Call** - POST do Azure Functions `/generate-cv-action`
4. **Download PDF** - Dekodowanie base64 → blob → download
5. **Error Handling** - Validation errors z backendu
6. **Status Feedback** - "Generating...", "Success", "Error"

### Nice-to-Have (Future):
7. **Photo Upload** - Separate photo upload → `/extract-photo`
8. **Preview HTML** - Preview przed generowaniem PDF
9. **Multi-language** - Switch EN/DE/PL
10. **History** - Lista wygenerowanych CVs (local storage)
11. **Templates** - Wybór template (gdy będzie więcej niż zurich)

---

## 🏗️ Architecture Plan

```
CV Generator UI (Next.js 14)
├── app/
│   ├── layout.tsx           # Root layout (global styles)
│   ├── page.tsx              # Main CV generator page
│   └── api/
│       └── proxy.ts          # Optional: proxy dla Azure Functions
├── components/
│   ├── CVForm.tsx            # Form do edycji CV data
│   ├── FileUpload.tsx        # Drag & drop DOCX upload
│   ├── PDFPreview.tsx        # Preview generated PDF
│   ├── StatusBanner.tsx      # Status messages
│   └── ui/                   # shadcn/ui components (button, input, etc.)
├── lib/
│   ├── api.ts                # Azure Functions API client
│   ├── types.ts              # CVData TypeScript types
│   └── utils.ts              # Helper functions
├── public/
│   └── samples/              # Sample CV JSON files
└── .env.local                # Backend URL config
```

---

## 🔄 Data Flow

```
User Action               UI Component          Backend Call
────────────────────────────────────────────────────────────
1. Upload DOCX         → FileUpload.tsx    → POST /extract-photo
   ↓ Extract photo       ↓ Returns data URI
   
2. Fill CV form        → CVForm.tsx        → (validation local)
   ↓ Edit fields         ↓ Real-time validation
   
3. Click "Generate"    → page.tsx          → POST /generate-cv-action
   ↓ Show loading        ↓ Body: cv_data + language + photo
   ↓ Backend processes   ↓ Azure Functions validates + renders
   ↓ Receive base64 PDF  ↓ Response: { success, pdf_base64 }
   
4. Download PDF        → PDFPreview.tsx    → base64 → Blob → download
   ✓ Save as file
```

---

## 📦 Package Modifications

**Base** (from ui_next):
```json
{
  "next": "14.2.5",
  "react": "18.3.1",
  "react-dom": "18.3.1"
}
```

**Add**:
```json
{
  "typescript": "^5.3.3",
  "@types/react": "^18.2.48",
  "@types/node": "^20.11.5",
  
  "tailwindcss": "^3.4.1",
  "autoprefixer": "^10.4.17",
  "postcss": "^8.4.33",
  
  "@radix-ui/react-dialog": "^1.0.5",
  "@radix-ui/react-dropdown-menu": "^2.0.6",
  "@radix-ui/react-label": "^2.0.2",
  "@radix-ui/react-select": "^2.0.0",
  "@radix-ui/react-toast": "^1.1.5",
  
  "class-variance-authority": "^0.7.0",
  "clsx": "^2.1.0",
  "tailwind-merge": "^2.2.0",
  
  "react-dropzone": "^14.2.3",
  "zod": "^3.22.4"
}
```

**Total**: ~20 dependencies (vs 100+ w ai-chatbot)

---

## 🚀 Implementation Phases

### Phase 1: Setup (1h)
- [x] Kopiuj `ui_next` jako base
- [ ] Setup TypeScript + Tailwind CSS
- [ ] Dodaj shadcn/ui components (button, input, label, toast)
- [ ] Stwórz `.env.local` z AZURE_FUNCTIONS_URL

### Phase 2: Core UI (2h)
- [ ] CVForm component - wszystkie pola z CVData schema
- [ ] FileUpload component - drag & drop DOCX
- [ ] StatusBanner - loading/success/error states
- [ ] Basic layout (zachowaj ui_next 3-column)

### Phase 3: Backend Integration (2h)
- [ ] API client (`lib/api.ts`) - fetch wrappers
- [ ] POST /extract-photo integration
- [ ] POST /generate-cv-action integration
- [ ] Error handling z backend validation errors

### Phase 4: File Handling (1h)
- [ ] DOCX upload → base64 encoding
- [ ] PDF download - base64 → Blob → saveAs
- [ ] File size validation (max 10MB)

### Phase 5: Polish & Testing (1h)
- [ ] Responsive design
- [ ] Form validation (required fields)
- [ ] Success toast notifications
- [ ] Sample data preload button
- [ ] Local testing z Azure backend

---

## 🔐 Security Considerations

### Authentication:
```typescript
// lib/api.ts
const AZURE_FUNCTIONS_KEY = process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_KEY;

async function callAzure(endpoint: string, body: any) {
  const response = await fetch(`${AZURE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-functions-key': AZURE_FUNCTIONS_KEY, // Auth header
    },
    body: JSON.stringify(body),
  });
  return response.json();
}
```

### File Upload Safety:
- Max file size: 10MB
- Allowed extensions: `.docx`, `.pdf` (dla source CV)
- Client-side validation przed wysyłką
- Server-side validation w Azure Functions (już jest)

---

## 📝 Key Files to Create

### 1. `lib/api.ts` - Azure Functions Client
```typescript
const AZURE_URL = process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_URL!;
const AZURE_KEY = process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_KEY!;

export async function extractPhoto(docxBase64: string) {
  return callAzure('/extract-photo', { docx_base64: docxBase64 });
}

export async function generateCV(cvData: CVData, language: string, photoBase64?: string) {
  return callAzure('/generate-cv-action', {
    cv_data: cvData,
    language,
    source_docx_base64: photoBase64,
  });
}

export async function validateCV(cvData: CVData) {
  return callAzure('/validate-cv', { cv_data: cvData });
}
```

### 2. `lib/types.ts` - TypeScript Definitions
```typescript
// Copy from openapi_cv_actions.yaml schemas
export interface CVData {
  full_name: string;
  email: string;
  phone?: string;
  address_lines: string[];
  profile?: string;
  work_experience: WorkExperience[];
  education: Education[];
  languages?: Language[];
  it_ai_skills?: string[];
  certifications?: string[];
  interests?: string;
  photo_url?: string;
  data_privacy_consent?: string;
}

export interface WorkExperience {
  date_range: string;
  employer: string;
  title: string;
  bullets: string[];
}

// ... rest from schema
```

### 3. `components/CVForm.tsx` - Main Form
```typescript
'use client';

import { useState } from 'react';
import { CVData } from '@/lib/types';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

export function CVForm({ onSubmit }: { onSubmit: (data: CVData) => void }) {
  const [cvData, setCVData] = useState<CVData>({
    full_name: '',
    email: '',
    address_lines: [],
    work_experience: [],
    education: [],
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(cvData); }}>
      <Input
        label="Full Name"
        value={cvData.full_name}
        onChange={(e) => setCVData({ ...cvData, full_name: e.target.value })}
        required
      />
      {/* ... rest of fields */}
    </form>
  );
}
```

### 4. `app/page.tsx` - Main Page
```typescript
'use client';

import { useState } from 'react';
import { CVForm } from '@/components/CVForm';
import { FileUpload } from '@/components/FileUpload';
import { generateCV, extractPhoto } from '@/lib/api';
import { downloadPDF } from '@/lib/utils';

export default function CVGenerator() {
  const [photoDataUri, setPhotoDataUri] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [status, setStatus] = useState('');

  const handleGenerateCV = async (cvData: CVData) => {
    setIsGenerating(true);
    setStatus('Generating PDF...');
    
    try {
      const result = await generateCV(cvData, 'en', photoDataUri);
      if (result.success) {
        downloadPDF(result.pdf_base64, `${cvData.full_name}_CV.pdf`);
        setStatus('PDF downloaded successfully!');
      }
    } catch (error) {
      setStatus(`Error: ${error.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <main className="container">
      <h1>CV Generator</h1>
      <FileUpload onPhotoExtracted={setPhotoDataUri} />
      <CVForm onSubmit={handleGenerateCV} />
      {status && <StatusBanner message={status} />}
    </main>
  );
}
```

---

## ⏱️ Time Estimate

| Phase | Task | Time |
|-------|------|------|
| 1 | Setup (TS, Tailwind, shadcn) | 1h |
| 2 | Core UI (Form, Upload, Status) | 2h |
| 3 | Backend Integration (API client) | 2h |
| 4 | File Handling (upload/download) | 1h |
| 5 | Polish & Testing | 1h |
| **Total** | **MVP Ready** | **6-7h** |

---

## 🎯 Success Criteria

✅ **MVP Complete When**:
1. User może upload DOCX → extract photo
2. User może wypełnić CV form
3. User może kliknąć "Generate" → otrzymać PDF
4. PDF nie jest uszkodzony (problem z Custom GPT rozwiązany)
5. Error handling działa (pokazuje backend validation errors)

---

## 🚦 Next Steps

**Immediate**:
1. Skopiuj `ui_next` do `CV-generator-repo/ui`
2. Setup package.json z dependencies
3. Stwórz `.env.local` z Azure Functions URL + key
4. Dodaj shadcn/ui components

**Gotowy do startu?** 🚀
