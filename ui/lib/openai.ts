// OpenAI API client for CV data extraction

import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const PROMPT_ID = process.env.OPENAI_PROMPT_ID!;

export async function extractCVFromPrompt(userInput: string): Promise<any> {
  try {
    const completion = await openai.chat.completions.create({
      model: 'gpt-4o-2024-08-06',
      messages: [
        {
          role: 'user',
          content: userInput,
        },
      ],
      // Use stored prompt if available
      store: true,
      metadata: {
        prompt_id: PROMPT_ID,
      },
    });

    const responseText = completion.choices[0]?.message?.content || '{}';
    
    // Try to parse JSON from response
    try {
      return JSON.parse(responseText);
    } catch {
      // If not JSON, return as-is
      return { raw_response: responseText };
    }
  } catch (error: any) {
    console.error('OpenAI API error:', error);
    throw new Error(`Failed to extract CV data: ${error.message}`);
  }
}
