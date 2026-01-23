import type { CVStage } from '@/lib/prompts';

const JOB_TEXT_MAX_CHARS = (() => {
  const parsed = Number.parseInt(process.env.CV_JOB_TEXT_MAX_CHARS || '6000', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 6000;
})();

export function roughInputChars(input: any[]): number {
  // Approximate size of the input we send to OpenAI.
  // Avoid JSON.stringify of big objects; focus on known large string fields.
  let total = 0;
  for (const item of input || []) {
    if (!item) continue;
    if (typeof item.content === 'string') total += item.content.length;
    if (Array.isArray(item.content)) {
      for (const c of item.content) {
        if (typeof c?.text === 'string') total += c.text.length;
      }
    }
    if (typeof item.output === 'string') total += item.output.length;
    if (typeof item.arguments === 'string') total += item.arguments.length;
  }
  return total;
}

export function sanitizeToolOutputForModel(toolName: string, toolOutput: string): string {
  // The model does not need base64 blobs (photo/pdf) which can bloat context.
  // Return a compact summary to keep the next call small.

  const maxLen = 4000;
  const clamp = (s: string) =>
    s.length <= maxLen ? s : `${s.slice(0, maxLen)}\n...[truncated ${s.length - maxLen} chars]`;

  let parsed: any = null;
  try {
    parsed = JSON.parse(toolOutput);
  } catch {
    return clamp(toolOutput);
  }

  if (!parsed || typeof parsed !== 'object') {
    return clamp(toolOutput);
  }

  if (toolName === 'extract_and_store_cv') {
    const sessionId = typeof parsed.session_id === 'string' ? parsed.session_id : undefined;
    const hasPhoto = parsed.photo_extracted === true;
    const summary = parsed.cv_data_summary;
    return JSON.stringify({
      ok: parsed.success !== false,
      session_id: sessionId,
      fields_populated: summary?.fields_populated?.length ?? undefined,
      fields_empty: summary?.fields_empty?.length ?? undefined,
      photo_extracted: hasPhoto,
      error: parsed.error,
    });
  }

  if (toolName === 'get_cv_session') {
    try {
      const parsed = JSON.parse(toolOutput);
      const cv = parsed?.cv_data || {};
      const meta = parsed?.metadata || {};
      const work = Array.isArray(cv?.work_experience) ? cv.work_experience : [];
      const edu = Array.isArray(cv?.education) ? cv.education : [];
      const langs = Array.isArray(cv?.languages) ? cv.languages : [];
      const skills = Array.isArray(cv?.it_ai_skills)
        ? cv.it_ai_skills
        : Array.isArray(cv?.skills)
        ? cv.skills
        : [];

      const clampStr = (s: any, n: number) =>
        typeof s === 'string' ? (s.length <= n ? s : `${s.slice(0, n)}...[+${s.length - n}]`) : '';

      const toLen = (v: any) => (typeof v === 'string' ? v.length : v == null ? 0 : String(v).length);

      // Compute limit/DoD risk signals so the model can self-fix in one pass.
      const workBulletCounts = work.map((j: any) => (Array.isArray(j?.bullets) ? j.bullets.length : 0));
      const workMaxBullets = workBulletCounts.length ? Math.max(...workBulletCounts) : 0;
      const workMaxBulletLen = work.length
        ? Math.max(
            0,
            ...work.flatMap((j: any) =>
              Array.isArray(j?.bullets) ? j.bullets.map((b: any) => toLen(b)) : [0]
            )
          )
        : 0;

      const langMaxLen = langs.length ? Math.max(...langs.map((x: any) => toLen(x))) : 0;
      const skillMaxLen = skills.length ? Math.max(...skills.map((x: any) => toLen(x))) : 0;

      const eduDetailsMaxCombined = edu.length
        ? Math.max(
            ...edu.map((e: any) =>
              Array.isArray(e?.details)
                ? e.details.map((d: any) => toLen(d)).reduce((a: number, b: number) => a + b, 0)
                : 0
            )
          )
        : 0;

      const sampleWork = work.slice(0, 2).map((j: any) => ({
        date_range: clampStr(j?.date_range, 40),
        employer: clampStr(j?.employer, 60),
        location: clampStr(j?.location, 60),
        title: clampStr(j?.title, 70),
        bullets: Array.isArray(j?.bullets)
          ? j.bullets.slice(0, 4).map((b: any) => clampStr(String(b ?? ''), 120))
          : [],
      }));
      const workOutline = work.slice(0, 10).map((j: any) => ({
        date_range: clampStr(j?.date_range, 40),
        employer: clampStr(j?.employer, 60),
        location: clampStr(j?.location, 60),
        title: clampStr(j?.title, 70),
        bullets_count: Array.isArray(j?.bullets) ? j.bullets.length : 0,
      }));
      const sampleEdu = edu.slice(0, 2).map((e: any) => ({
        date_range: clampStr(e?.date_range, 40),
        institution: clampStr(e?.institution, 80),
        title: clampStr(e?.title, 90),
        details: Array.isArray(e?.details) ? e.details.slice(0, 3).map((d: any) => clampStr(String(d ?? ''), 120)) : [],
      }));
      const eduOutline = edu.slice(0, 10).map((e: any) => ({
        date_range: clampStr(e?.date_range, 40),
        institution: clampStr(e?.institution, 80),
        title: clampStr(e?.title, 90),
        details_count: Array.isArray(e?.details) ? e.details.length : 0,
      }));

      const completeness = (() => {
        const required_present = {
          full_name: !!(cv?.full_name && String(cv.full_name).trim()),
          email: !!(cv?.email && String(cv.email).trim()),
          phone: !!(cv?.phone && String(cv.phone).trim()),
          work_experience: Array.isArray(work) && work.length > 0,
          education: Array.isArray(edu) && edu.length > 0,
        };
        const counts = {
          work_experience: work.length,
          education: edu.length,
          languages: langs.length,
          it_ai_skills: skills.length,
        };
        const templateOrder: Array<[string, any]> = [
          ['education', edu],
          ['work_experience', work],
          ['further_experience', Array.isArray(cv?.further_experience) ? cv.further_experience : []],
          ['languages', langs],
          ['it_ai_skills', skills],
          ['interests', typeof cv?.interests === 'string' ? cv.interests : ''],
          ['references', typeof cv?.references === 'string' ? cv.references : ''],
        ];
        let next_missing_section: string | null = null;
        for (const [name, val] of templateOrder) {
          if (Array.isArray(val) && val.length === 0) {
            next_missing_section = name;
            break;
          }
          if (typeof val === 'string' && val.trim().length === 0) {
            next_missing_section = name;
            break;
          }
        }
        return { required_present, counts, next_missing_section };
      })();

      return JSON.stringify({
        ok: parsed.success !== false,
        session_id: parsed.session_id,
        expires_at: parsed.expires_at,
        freshness: {
          version: parsed?._metadata?.version ?? undefined,
          updated_at: parsed?._metadata?.updated_at ?? undefined,
          content_signature: parsed?._metadata?.content_signature ?? undefined,
        },
        metadata: {
          language: meta?.language,
          extraction_method: meta?.extraction_method,
          has_photo_blob: !!meta?.photo_blob,
        },
        limit_risks: {
          profile_chars: toLen(cv?.profile || cv?.summary || ''),
          work_entries: work.length,
          work_max_bullets_per_entry: workMaxBullets,
          work_max_bullet_chars: workMaxBulletLen,
          education_entries: edu.length,
          education_max_details_combined_chars: eduDetailsMaxCombined,
          languages_items: langs.length,
          languages_max_item_chars: langMaxLen,
          it_ai_skills_items: skills.length,
          it_ai_skills_max_item_chars: skillMaxLen,
        },
        completeness,
        required_present: {
          full_name: !!(cv?.full_name && String(cv.full_name).trim()),
          email: !!(cv?.email && String(cv.email).trim()),
          phone: !!(cv?.phone && String(cv.phone).trim()),
          work_experience: Array.isArray(work) && work.length > 0,
          education: Array.isArray(edu) && edu.length > 0,
        },
        counts: {
          work_experience: work.length,
          education: edu.length,
          languages: langs.length,
          it_ai_skills: skills.length,
        },
        contact: {
          full_name: clampStr(cv?.full_name, 80),
          email: clampStr(cv?.email, 80),
          phone: clampStr(cv?.phone, 50),
          address_lines: Array.isArray(cv?.address_lines)
            ? cv.address_lines.slice(0, 2).map((x: any) => clampStr(String(x ?? ''), 80))
            : [],
        },
        profile: clampStr(cv?.profile || cv?.summary || '', 500),
        sample_work_experience: sampleWork,
        work_experience_outline: workOutline,
        sample_education: sampleEdu,
        education_outline: eduOutline,
        error: parsed.error,
      });
    } catch {
      return clamp(toolOutput);
    }
  }

  if (toolName === 'generate_cv_from_session') {
    const pdfLen = typeof parsed.pdf_base64 === 'string' ? parsed.pdf_base64.length : 0;
    return JSON.stringify({
      ok: parsed.success !== false && pdfLen > 0,
      success: parsed.success,
      pdf_generated: pdfLen > 0,
      pdf_base64_length: pdfLen || undefined,
      validation: parsed.validation,
      errors: parsed.validation_errors || parsed.error,
      last_validation_errors: parsed.validation_errors,
      last_validation_details: parsed.details,
      session_id: parsed.session_id,
    });
  }

  if (toolName === 'fetch_job_posting_text') {
    const text = typeof parsed.job_posting_text === 'string' ? parsed.job_posting_text : '';
    const bounded = text.length > JOB_TEXT_MAX_CHARS ? text.slice(0, JOB_TEXT_MAX_CHARS) : text;
    return JSON.stringify({
      ok: parsed.success !== false && !!bounded,
      success: parsed.success,
      url: parsed.url,
      job_posting_text_length: text.length || undefined,
      job_posting_text: bounded || '',
      error: parsed.error,
    });
  }

  // Generic sanitizer: drop known huge fields and clamp long strings.
  const out: Record<string, any> = { ...parsed };
  for (const key of ['photo_data_uri', 'pdf_base64', 'docx_base64', 'source_docx_base64']) {
    if (key in out) delete out[key];
  }

  for (const [k, v] of Object.entries(out)) {
    if (typeof v === 'string' && v.length > 1500) {
      out[k] = `${v.slice(0, 1500)}...[truncated ${v.length - 1500} chars]`;
    }
  }

  return clamp(JSON.stringify(out));
}

type Phase = 'preparation' | 'confirmation' | 'execution';

function detectUserApproval(userMessage: string): boolean {
  // Detect if user is giving explicit approval to proceed to execution
  const m = (userMessage || '').toLowerCase();
  const approvalKeywords = /\b(proceed|yes|looks? good|generate|go ahead|perfect|approved?|confirm|ok to generate)\b/i;
  const negativeKeywords = /\b(no|wait|change|modify|edit|fix|update|revise|not yet|hold on)\b/i;

  // Must have approval keywords AND no negative keywords
  return approvalKeywords.test(m) && !negativeKeywords.test(m);
}

function validatePhaseTransition(
  currentPhase: Phase,
  nextPhase: Phase,
  userApproved: boolean
): { allowed: boolean; reason?: string } {
  // Phase 1 → Phase 2: Allowed anytime (user can request confirmation)
  if (currentPhase === 'preparation' && nextPhase === 'confirmation') {
    return { allowed: true };
  }

  // Phase 2 → Phase 3: Only if user approved
  if (currentPhase === 'confirmation' && nextPhase === 'execution') {
    if (!userApproved) {
      return {
        allowed: false,
        reason: 'Cannot generate PDF without explicit user approval from confirmation phase',
      };
    }
    return { allowed: true };
  }

  // Phase 2 → Phase 1: Allowed (user provides feedback)
  if (currentPhase === 'confirmation' && nextPhase === 'preparation') {
    return { allowed: true };
  }

  // Phase 1 → Phase 3: BLOCKED (must go through confirmation)
  if (currentPhase === 'preparation' && nextPhase === 'execution') {
    return {
      allowed: false,
      reason: 'Must go through confirmation gate first. Cannot skip from preparation to execution.',
    };
  }

  // Same phase: Always allowed
  if (currentPhase === nextPhase) {
    return { allowed: true };
  }

  // Phase 3 → Phase 1: Allowed (if validation fails, return to preparation)
  if (currentPhase === 'execution' && nextPhase === 'preparation') {
    return { allowed: true };
  }

  // Any other transition: Allowed by default
  return { allowed: true };
}

function determineCurrentPhase(stage: CVStage): Phase {
  // Map 9 stages to 3 phases
  // Key insight: draft_proposal and apply_edits are CONFIRMATION (user reviewing/approving)
  // Only generate_pdf and final are true EXECUTION
  switch (stage) {
    case 'bootstrap':
    case 'extract':
    case 'review_session':
    case 'edits_only':
      return 'preparation';
    case 'draft_proposal':
    case 'apply_edits':
      return 'confirmation';  // User is reviewing proposals or we're fixing issues
    case 'fix_validation':
    case 'generate_pdf':
    case 'final':
      return 'execution';
    default:
      return 'preparation';
  }
}

export { determineCurrentPhase };

function getPhaseInstructions(phase: Phase): string {
  switch (phase) {
    case 'preparation':
      return `[PHASE: PREPARATION]
You are in the preparation phase—the default, dominant state. Your goal is to:
- Analyze the job offer deeply (explicit + implicit requirements)
- Map CV elements to job requirements
- Identify gaps, strengths, and positioning opportunities
- Propose narrative changes as hypotheses for discussion
- Encourage iterative dialog and refinement

DO NOT rush toward confirmation or generation. Remain in this phase until the user explicitly requests to review the final proposal.`;

    case 'confirmation':
      return `[PHASE: CONFIRMATION]
You are in the confirmation phase—an explicit approval gate. Your goal is to:
- Display the full proposed CV (section-by-section preview)
- Show changes diff with rationale for each change
- Wait for explicit user approval (keywords: "proceed", "yes", "looks good", "generate")
- If user provides feedback, return to preparation phase
- Only proceed to execution phase with explicit approval

DO NOT generate PDF without explicit user approval.`;

    case 'execution':
      return `[PHASE: EXECUTION]
You are in the execution phase—user has given explicit approval. Your goal is to:
- Run mandatory self-validation (hard limits)
- Call generate_cv_from_session(session_id)
- If validation fails: fix ALL errors in one pass, retry once
- Return final PDF to user

You are here because the user approved the proposal. Generate quickly and efficiently.`;

    default:
      return `[PHASE: PREPARATION]\nDefault to consultative preparation mode.`;
  }
}

function formatContextPackWithDelimiters(pack: any): string {
  // Format context pack with explicit XML-style delimiters (OpenAI best practice)
  if (!pack || typeof pack !== 'object') {
    return JSON.stringify(pack || {});
  }

  const phase = pack.phase || 'unknown';
  const lines: string[] = [
    '<CONTEXT_PACK_V2>',
    `<schema>${pack.schema_version || 'cvgen.context_pack.v2'}</schema>`,
    `<phase>${phase}</phase>`,
    '',
    '<session_metadata>',
    `session_id: ${pack.session_id || 'unknown'}`,
    `language: ${pack.language || 'en'}`,
    `cv_fingerprint: ${pack.cv_fingerprint || 'unknown'}`,
    '</session_metadata>',
    '',
  ];

  if (pack.confirmation_state) {
    lines.push('<confirmation_state>');
    lines.push(JSON.stringify(pack.confirmation_state, null, 2));
    lines.push('</confirmation_state>');
    lines.push('');
  }
  if (pack.readiness) {
    lines.push('<readiness>');
    lines.push(JSON.stringify(pack.readiness, null, 2));
    lines.push('</readiness>');
    lines.push('');
  }

  // Add phase-specific sections
  if (phase === 'preparation' && pack.preparation) {
    const prep = pack.preparation;

    if (prep.job_analysis) {
      lines.push('<job_analysis>');
      lines.push(prep.job_analysis.note || 'Analyze job offer deeply');
      if (prep.job_analysis.text_snippet) {
        lines.push('');
        lines.push(prep.job_analysis.text_snippet);
      }
      lines.push('</job_analysis>');
      lines.push('');
    }

    if (prep.cv_data) {
      lines.push('<cv_structured>');
      lines.push(JSON.stringify(prep.cv_data, null, 2));
      lines.push('</cv_structured>');
      lines.push('');
    }

    // Unconfirmed DOCX snapshot (reference-only): used to hydrate empty sessions quickly.
    if (prep.docx_prefill_unconfirmed) {
      lines.push('<docx_prefill_unconfirmed>');
      lines.push(JSON.stringify(prep.docx_prefill_unconfirmed, null, 2));
      lines.push('</docx_prefill_unconfirmed>');
      lines.push('');
    }

    if (prep.proposal_history && Array.isArray(prep.proposal_history)) {
      lines.push('<proposal_history>');
      lines.push(`Last ${prep.proposal_history.length} iterations:`);
      prep.proposal_history.forEach((proposal: any, idx: number) => {
        lines.push(`\nIteration ${idx + 1}:`);
        lines.push(JSON.stringify(proposal, null, 2));
      });
      lines.push('</proposal_history>');
      lines.push('');
    }
  } else if (phase === 'confirmation' && pack.confirmation) {
    const conf = pack.confirmation;

    if (conf.original_cv_summary) {
      lines.push('<original_cv_summary>');
      lines.push(JSON.stringify(conf.original_cv_summary, null, 2));
      lines.push('</original_cv_summary>');
      lines.push('');
    }

    if (conf.proposed_cv_summary) {
      lines.push('<proposed_cv_summary>');
      lines.push(JSON.stringify(conf.proposed_cv_summary, null, 2));
      lines.push('</proposed_cv_summary>');
      lines.push('');
    }

    if (conf.changes_diff && Array.isArray(conf.changes_diff)) {
      lines.push('<changes_diff>');
      lines.push('What changed and why:');
      conf.changes_diff.forEach((change: any) => {
        lines.push(`\n- Section: ${change.section}`);
        lines.push(`  Description: ${change.description}`);
        if (change.rationale) {
          lines.push(`  Rationale: ${change.rationale}`);
        }
      });
      lines.push('</changes_diff>');
      lines.push('');
    }

    if (conf.phase1_analysis) {
      lines.push('<phase1_analysis>');
      lines.push(JSON.stringify(conf.phase1_analysis, null, 2));
      lines.push('</phase1_analysis>');
      lines.push('');
    }
  } else if (phase === 'execution' && pack.execution) {
    const exec = pack.execution;

    if (exec.approved_cv_data) {
      lines.push('<approved_cv_data>');
      lines.push(JSON.stringify(exec.approved_cv_data, null, 2));
      lines.push('</approved_cv_data>');
      lines.push('');
    }

    if (exec.hard_limits) {
      lines.push('<hard_limits>');
      lines.push(JSON.stringify(exec.hard_limits, null, 2));
      lines.push('</hard_limits>');
      lines.push('');
    }

    if (exec.validation_checklist && Array.isArray(exec.validation_checklist)) {
      lines.push('<validation_checklist>');
      exec.validation_checklist.forEach((item: any) => {
        lines.push(`- ${item.check}: ${item.status}`);
      });
      lines.push('</validation_checklist>');
      lines.push('');
    }
  }

  lines.push('</CONTEXT_PACK_V2>');
  return lines.join('\n');
}

export function buildUserContent(args: {
  userMessage: string;
  hasDocx: boolean;
  hasSession: boolean;
  sessionId: string | null;
  skipPhoto: boolean;
  sessionSnapshot: string | null;
  contextPack: any | null;
  boundedCvText: string | null;
  jobPostingUrl: string | null;
  jobPostingText: string | null;
  language: string;
  stage: CVStage;
}): string {
  const boundedJobText = args.jobPostingText ? args.jobPostingText.slice(0, JOB_TEXT_MAX_CHARS) : null;
  const phase = determineCurrentPhase(args.stage);
  const phaseInstructions = getPhaseInstructions(phase);

  // Capsule invariants:
  // - If `hasSession`, always include either SESSION_SNAPSHOT_JSON or an explicit marker to force get_cv_session().
  // - If `jobPostingUrl` exists, always include either job posting text or an explicit marker to force paste-from-user.
  const sessionBlock = args.hasSession
    ? args.sessionSnapshot
      ? `\n\n[SESSION_SNAPSHOT_JSON]\n${args.sessionSnapshot}`
      : `\n\n[SESSION_SNAPSHOT_JSON_MISSING]\nCould not prefetch session snapshot. You MUST call get_cv_session(session_id) now and treat that output as source of truth.`
    : null;

  const jobBlock = args.jobPostingUrl
    ? boundedJobText
      ? `\n\n[Job posting text extracted from ${args.jobPostingUrl} (may be partial; truncated to ${boundedJobText.length} chars):]\n${boundedJobText}`
      : `\n\n[JOB_POSTING_TEXT_MISSING]\nCould not fetch the job posting text from ${args.jobPostingUrl}. Ask the user to paste the full job posting text.`
    : null;

  // Context pack formatting (use delimiters for ContextPackV2)
  const contextPackBlock = args.contextPack
    ? `\n\n[CONTEXT_PACK_V2]\n${formatContextPackWithDelimiters(args.contextPack)}`
    : args.boundedCvText
    ? `\n\n[CV text extracted from uploaded DOCX (may be partial):]\n${args.boundedCvText}`
    : null;

  const userContent = [
    phaseInstructions,
    '',
    args.userMessage,
    args.hasDocx
      ? '[CV DOCX is already uploaded in this chat. Do NOT ask the user to re-send it or paste base64. If you need file bytes, call tools; backend will inject docx_base64 for you.]'
      : null,
    args.hasSession && args.sessionId ? `[Session id: ${args.sessionId}]` : null,
    args.skipPhoto ? '[User requested: omit photo in the final CV. Do not extract photo.]' : null,
    sessionBlock,
    contextPackBlock,
    jobBlock,
    `\n\n[Output language: ${args.language}.]`,
  ]
    .filter(Boolean)
    .join('\n\n');

  return userContent;
}

export function buildBaseInputList(args: { hasDocx: boolean; systemPrompt: string; userContent: string }): any[] {
  const inputList: any[] = [];

  if (args.hasDocx) {
    inputList.push({
      role: 'system',
      content:
        'The user already uploaded a CV document. Never ask them to paste base64 or re-upload. If you need the file bytes, call extract_and_store_cv and the backend will inject docx_base64 for you.',
    });
  }

  // Ensure each request is self-contained (Responses API is stateless across HTTP requests).
  inputList.push({
    role: 'system',
    content:
      'Use session-based workflow only: extract_and_store_cv → get_cv_session → update_cv_field → generate_cv_from_session. Do NOT call legacy tools. Always reuse session_id, ask for missing required fields (full_name, email, phone, work_experience, education), then generate.',
  });
  inputList.push({
    role: 'system',
    content:
      'IMPORTANT: Do NOT rely on previous_response_id or chat history. Every HTTP request is stateless. If a session id is provided, start by calling get_cv_session(session_id) unless a SESSION_SNAPSHOT_JSON is already present.',
  });
  inputList.push({
    role: 'system',
    content:
      'TEMPLATE NOTE (fixed current PDF): There is NO dedicated Profile/Summary section rendered. The visible sections are: Education, Work experience, Further experience / commitment, Language Skills, IT & AI Skills, Interests, References. Optimize fields that are actually rendered.',
  });
  if (typeof args.systemPrompt === 'string' && args.systemPrompt.trim()) {
    inputList.push({
      role: 'system',
      content: args.systemPrompt,
    });
  }

  inputList.push({
    role: 'user',
    content: args.userContent,
  });

  return inputList;
}

export function maxOutputTokensForStage(stage: CVStage): number {
  // Give the agent enough output room to render a full preview (all work experience entries),
  // while still keeping bounded budgets per stage.
  // Original budgets were: draft_proposal=1200, fix_validation=800, generate_pdf=600, default=600.
  // Per request: increase to 120% of original budgets (reduce token explosion risk).
  return stage === 'draft_proposal' ? 1440 : stage === 'fix_validation' ? 960 : stage === 'generate_pdf' ? 720 : 720;
}

export function buildResponsesRequest(args: {
  promptId: string | undefined;
  modelOverride: string | undefined;
  stage: CVStage;
  stageSeq: number;
  systemPrompt: string;
  stagePrompt: string;
  inputList: any[];
  tools: any[];
}): any {
  // ZDR (Zero Data Retention) compliance: Don't store CV data on OpenAI servers
  // Default: store=false (disabled) for sensitive personal data
  // Override with OPENAI_STORE=1 if needed for debugging
  const shouldStore = process.env.OPENAI_STORE === '1';

  // Optional prompt caching (cost/latency optimization for repeated prefixes).
  // Note: prompt_cache_key replaces the legacy `user` field, so we only set it if explicitly configured.
  const promptCacheKey = process.env.OPENAI_PROMPT_CACHE_KEY;
  const promptCacheRetentionRaw = process.env.OPENAI_PROMPT_CACHE_RETENTION;
  const promptCacheRetention =
    promptCacheRetentionRaw === 'in_memory' || promptCacheRetentionRaw === '24h' ? promptCacheRetentionRaw : undefined;

  const req: any = {
    ...(args.promptId ? { prompt: { id: args.promptId } } : { instructions: args.systemPrompt }),
    input: [...args.inputList, { role: 'system', content: args.stagePrompt }],
    tools: args.tools,
    store: shouldStore,  // ZDR compliance: false by default
    truncation: 'disabled',
    max_output_tokens: maxOutputTokensForStage(args.stage),
    metadata: {
      app: 'cv-generator-ui',
      prompt_id: args.promptId || 'none',
      workflow: 'staged_v1',
      stage: args.stage,
      // OpenAI metadata values must be strings.
      stage_seq: String(args.stageSeq),
    },
  };

  if (promptCacheKey) {
    req.prompt_cache_key = promptCacheKey;
  }
  if (promptCacheRetention) {
    req.prompt_cache_retention = promptCacheRetention;
  }

  // For reasoning models (o1, o3), include encrypted content for ZDR
  const model = args.modelOverride || (args.promptId ? undefined : 'gpt-4o');
  if (model && (model.startsWith('o1') || model.startsWith('o3'))) {
    req.include = ['reasoning.encrypted_content'];
  }

  if (args.modelOverride) {
    req.model = args.modelOverride;
  } else if (!args.promptId) {
    req.model = 'gpt-4o';
  }

  return req;
}
