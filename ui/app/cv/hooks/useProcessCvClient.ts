import { useCallback } from 'react';

export function useProcessCvClient() {
  const postProcessCv = useCallback(async (requestBody: Record<string, unknown>) => {
    const response = await fetch('/api/process-cv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    const text = await response.text();
    let json: Record<string, unknown> = {};
    try {
      json = JSON.parse(text || '{}') as Record<string, unknown>;
    } catch {
      json = {};
    }

    return {
      ok: response.ok,
      status: response.status,
      text,
      json,
    };
  }, []);

  return { postProcessCv };
}
