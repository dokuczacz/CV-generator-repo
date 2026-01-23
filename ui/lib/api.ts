// Azure Functions API client

const AZURE_URL = process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_URL!;
const AZURE_KEY = process.env.NEXT_PUBLIC_AZURE_FUNCTIONS_KEY!;

async function callAzure(endpoint: string, body: any) {
  const response = await fetch(`${AZURE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-functions-key': AZURE_KEY,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function extractPhoto(docxBase64: string): Promise<{ photo_data_uri: string }> {
  return callAzure('/extract-photo', { docx_base64: docxBase64 });
}

export async function validateCV(cvData: any): Promise<any> {
  return callAzure('/validate-cv', { cv_data: cvData });
}

export async function generateCV(
  cvData: any,
  language: 'en' | 'de' | 'pl' = 'en',
  sourceDocxBase64?: string
): Promise<any> {
  return callAzure('/generate-cv-action', {
    cv_data: cvData,
    language,
    source_docx_base64: sourceDocxBase64,
  });
}
