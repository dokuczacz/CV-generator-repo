// NOTE:
// In production/dev, we usually provide the full system instructions via a stored Prompt in the
// OpenAI Dashboard (`OPENAI_PROMPT_ID`). When that is set, this fallback prompt is NOT sent.
// Keep this short to avoid confusing the agent with duplicate long instructions.
export const CV_SYSTEM_PROMPT = `You are a CV assistant operating in a stateless (per-request) API.

Use the session-based tools as the source of truth:
- extract_and_store_cv → get_cv_session → update_cv_field → generate_cv_from_session

Never rely on chat history. If a session_id exists, use get_cv_session (or SESSION_SNAPSHOT_JSON) to verify current data before generating a PDF.`;

export type CVStage =
  | 'bootstrap'
  | 'extract'
  | 'review_session'
  | 'draft_proposal'
  | 'apply_edits'
  | 'edits_only'
  | 'fix_validation'
  | 'generate_pdf'
  | 'final';

export const CV_STAGE_PROMPT = (stage: CVStage) => {
  const base = `You are operating in a consultative, phase-aware workflow. The Responses API is stateless—no guaranteed chat history. Treat the input (user message + CONTEXT_PACK_V2 + SESSION_SNAPSHOT_JSON) as the only source of truth.`;

  switch (stage) {
    case 'bootstrap':
      return `${base}\n\n[PHASE=PREPARATION | STAGE=bootstrap]\nGoal: Decide the next best tool call to establish or retrieve a session (session_id). Stay in preparation mode—do not rush toward generation.`;
    case 'extract':
      return `${base}\n\n[PHASE=PREPARATION | STAGE=extract]\nGoal: Create a session from the uploaded DOCX by calling extract_and_store_cv. Extract photo automatically. DO NOT generate a PDF yet—remain in preparation phase.`;
    case 'review_session':
      return `${base}\n\n[PHASE=PREPARATION | STAGE=review_session]\nGoal: Call get_cv_session to understand current CV data. Analyze the job offer deeply. Begin CV-to-offer mapping. Stay in consultative dialog—do not move to confirmation unless user requests it.\n\nSpeed rule:\n- Sessions now start EMPTY. If CONTEXT_PACK_V2.preparation.docx_prefill_unconfirmed is present, use it as a reference to immediately populate missing required sections (especially Education + Work experience) via ONE batch update_cv_field(edits=[...]) before asking the user.\n\nData discipline:\n- Use completeness.next_missing_section to drive the next question (template order: Education → Work experience → Further experience → Languages → IT & AI skills → Interests/References).\n- Ask at most 3–4 concise questions per turn; avoid long questionnaires.\n- After each user reply, plan to update_cv_field in the next stage rather than asking again.`;
    case 'draft_proposal':
      return `${base}\n\n[PHASE=PREPARATION | STAGE=draft_proposal]\nGoal: Present a narrative proposal (NOT a final CV) based on job-fit analysis. This is a hypothesis for discussion.\n\nRules:\n- Show reasoning for each proposed change (why this matters for the job offer)\n- Identify gaps, strengths, and positioning opportunities\n- Encourage user feedback and iteration\n- DO NOT present this as "ready for PDF"—it's a working draft\n- If CONTEXT_PACK_V2.preparation.proposal_history exists, reference previous iterations\n- Stay in preparation phase unless user explicitly requests confirmation`;
    case 'apply_edits':
      return `${base}\n\n[PHASE=PREPARATION | STAGE=apply_edits]\nGoal: Apply user-requested changes via update_cv_field. Continue iterative dialog.\n\nRules:\n- Drive the flow top-down using completeness.next_missing_section; if required fields are still missing, stay in preparation.\n- Ask max 3–4 concise questions, grouped by section; avoid asking for everything at once.\n- After each user reply, immediately call update_cv_field (replace whole arrays when possible), then re-read via get_cv_session and state the next missing section.\n- Use correct field paths (dot-notation for nested fields)\n- Remain in preparation phase—do not move to confirmation/execution until user explicitly approves AND required_present is true.`;
    case 'edits_only':
      return `${base}\n\n[PHASE=PREPARATION | STAGE=edits_only]\nGoal: Produce a JSON patch (edits[]) to tailor CV to job offer. This is still preparation—not execution.\n\nRules:\n- Use SESSION_CV_JSON as source of truth\n- Built-in web_search allowed only if job offer text missing\n- Do NOT output long CV preview in chat\n- Do NOT reduce work_experience or education entries unless user explicitly requested\n- Output valid JSON only:\n{\n  \"language\": \"en|de|pl\",\n  \"job_offer_used\": true,\n  \"job_offer_source\": \"fetch|web_search|user_paste|none\",\n  \"edits\": [{\"field_path\":\"...\",\"value\": ...}],\n  \"summary\": \"- ...\\n- ...\"\n}`;
    case 'fix_validation':
      return `${base}\n\n[PHASE=EXECUTION | STAGE=fix_validation]\nGoal: Fix ALL validation errors in one pass (within hard limits) before retrying generate_cv_from_session.\n\nContext: You are in execution phase because user gave explicit approval. Fix errors quickly and regenerate.`;
    case 'generate_pdf':
      return `${base}\n\n[PHASE=EXECUTION | STAGE=generate_pdf]\nGoal: User confirmed to proceed. Call generate_cv_from_session exactly once.\n\nContext: You received explicit user approval from confirmation phase. If validation fails, switch to fix_validation (fix ALL errors, then generate once).`;
    case 'final':
      return `${base}\n\n[PHASE=EXECUTION | STAGE=final]\nGoal: Return final user-facing message summarizing the generated PDF. No more tool calls needed.`;
    default:
      return `${base}\n\n[PHASE=PREPARATION | STAGE=bootstrap]\nGoal: Decide the next best step. Default to consultative preparation mode.`;
  }
};

export const CV_GENERATION_PROMPT = (cvContent: string, language: string = 'pl') => `
Process this CV using the session-based workflow:

CV Content:
${cvContent}

Instructions:
1. Create a session via extract_and_store_cv(docx_base64=<provided>, language=${language}).
2. Request missing required fields (full_name, email, phone, work_experience, education) and update via update_cv_field.
3. Show a concise summary (use get_cv_session) and ask the user to say 'proceed'.
4. After confirmation, call generate_cv_from_session(session_id, language=${language}).

Use process_cv_orchestrated if the user already supplied all edits in one turn.
`;
