export const CV_TOOLS = [
  {
    type: 'function' as const,
    function: {
      name: 'extract_and_store_cv',
      description:
        'Extracts CV data from uploaded DOCX and stores it in a session. Returns session_id for follow-up calls.',
      parameters: {
        type: 'object' as const,
        properties: {
          docx_base64: {
            type: 'string',
            description: 'Base64 encoded DOCX file content',
          },
          language: {
            type: 'string',
            enum: ['en', 'de', 'pl'],
            description: 'CV language (default: en)',
          },
          extract_photo: {
            type: 'boolean',
            description: 'Whether to extract the embedded photo (default: true)',
          },
        },
        required: ['docx_base64'],
        additionalProperties: false,
      },
    },
  },
  {
    type: 'function' as const,
    function: {
      name: 'get_cv_session',
      description: 'Retrieves CV data from an existing session for preview or confirmation.',
      parameters: {
        type: 'object' as const,
        properties: {
          session_id: {
            type: 'string',
            description: 'Session identifier returned by extract_and_store_cv',
          },
        },
        required: ['session_id'],
        additionalProperties: false,
      },
    },
  },
  {
    type: 'function' as const,
    function: {
      name: 'update_cv_field',
      description:
        'Updates CV session fields (single update, batch edits[], one-section cv_patch, and/or confirmation flags).',
      parameters: {
        type: 'object' as const,
        properties: {
          session_id: {
            type: 'string',
            description: 'Session identifier',
          },
          field_path: {
            type: 'string',
            description: "Field path (e.g., 'full_name', 'work_experience[0].employer') for single update",
          },
          value: {
            description: 'New value for the field (single update)',
          },
          edits: {
            type: 'array',
            description: 'Batch edits; each requires field_path and value',
            items: {
              type: 'object',
              properties: {
                field_path: { type: 'string' },
                value: {},
              },
              required: ['field_path', 'value'],
            },
          },
          cv_patch: {
            type: 'object',
            description: 'Replace a single top-level section (exactly one key).',
            additionalProperties: true,
          },
          confirm: {
            type: 'object',
            description:
              'Confirmation flags for stable personal data; set both true before generating a PDF (contact_confirmed + education_confirmed).',
            properties: {
              contact_confirmed: { type: 'boolean' },
              education_confirmed: { type: 'boolean' },
            },
            additionalProperties: false,
          },
          client_context: {
            type: 'object',
            description: 'Optional UI context (non-sensitive); backend stores a bounded summary in event log.',
            additionalProperties: true,
          },
        },
        required: ['session_id'],
        additionalProperties: false,
      },
    },
  },
  {
    type: 'function' as const,
    function: {
      name: 'validate_cv',
      description:
        'Runs deterministic schema + DoD validation checks for the current session (no PDF render). Use to decide next missing fields/edits.',
      parameters: {
        type: 'object' as const,
        properties: {
          session_id: { type: 'string', description: 'Session identifier' },
        },
        required: ['session_id'],
        additionalProperties: false,
      },
    },
  },
  {
    type: 'function' as const,
    function: {
      name: 'generate_cv_from_session',
      description: 'Generates a PDF from CV data stored in the session (replaces generate_cv_action).',
      parameters: {
        type: 'object' as const,
        properties: {
          session_id: {
            type: 'string',
            description: 'Session identifier',
          },
          language: {
            type: 'string',
            enum: ['en', 'de', 'pl'],
            description: 'Optional language override',
          },
        },
        required: ['session_id'],
        additionalProperties: false,
      },
    },
  },
  {
    type: 'function' as const,
    function: {
      name: 'cv_session_search',
      description:
        'Search session data (cv_data + docx_prefill_unconfirmed + recent events) and return bounded previews. Use to recover education/contact/work without asking the user again.',
      parameters: {
        type: 'object' as const,
        properties: {
          session_id: { type: 'string', description: 'Session identifier' },
          q: { type: 'string', description: 'Optional text query (case-insensitive substring match)' },
          section: { type: 'string', description: "Optional section hint (e.g., 'education', 'contact')" },
          limit: { type: 'integer', description: 'Max hits (1..50, default 20)' },
        },
        required: ['session_id'],
        additionalProperties: false,
      },
    },
  },
];

// Tools formatted for the Responses API (function calling).
// See: https://platform.openai.com/docs/guides/function-calling?api-mode=responses
export const CV_TOOLS_RESPONSES = [
  // Built-in OpenAI tool: enables the model to fetch web pages via OpenAI's web search toolchain.
  // Without this entry, a stored prompt's "web browsing" setting is not available to the Responses API call.
  { type: 'web_search' as const },
  {
    type: 'function' as const,
    name: 'extract_and_store_cv',
    description:
      'Extracts CV data from uploaded DOCX and stores it in a session. First tool to call after upload.',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        docx_base64: {
          type: 'string' as const,
          description: 'Base64 encoded DOCX file content',
        },
        language: {
          type: 'string' as const,
          enum: ['en', 'de', 'pl'],
          description: 'CV language (default: en)',
        },
        extract_photo: {
          type: 'boolean' as const,
          description: 'Whether to extract the embedded photo (default: true)',
        },
      },
      required: ['docx_base64'],
      additionalProperties: false,
    },
  },
  {
    type: 'function' as const,
    name: 'get_cv_session',
    description: 'Retrieves CV data from an existing session for preview or confirmation.',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        session_id: {
          type: 'string' as const,
          description: 'Session identifier returned by extract_and_store_cv',
        },
      },
      required: ['session_id'],
      additionalProperties: false,
    },
  },
  {
    type: 'function' as const,
    name: 'update_cv_field',
    description:
      'Updates CV session fields (single update, batch edits[], one-section cv_patch, and/or confirmation flags).',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        session_id: {
          type: 'string' as const,
          description: 'Session identifier',
        },
        field_path: {
          type: 'string' as const,
          description: "Field path (single update)",
        },
        value: {
          description: 'New value (single update)',
        },
        cv_patch: {
          type: 'object' as const,
          description: 'Replace a single top-level section (exactly one key).',
          additionalProperties: true,
        },
        edits: {
          type: 'array' as const,
          description: 'Batch edits',
          items: {
            type: 'object' as const,
            properties: {
              field_path: { type: 'string' as const },
              value: {},
            },
            required: ['field_path', 'value'],
          },
        },
        confirm: {
          type: 'object' as const,
          description:
            'Confirmation flags for stable personal data; set both true before generating a PDF (contact_confirmed + education_confirmed).',
          properties: {
            contact_confirmed: { type: 'boolean' as const },
            education_confirmed: { type: 'boolean' as const },
          },
          additionalProperties: false,
        },
        client_context: {
          type: 'object' as const,
          description: 'Optional UI context (non-sensitive).',
          additionalProperties: true,
        },
      },
      required: ['session_id'],
      additionalProperties: false,
    },
  },
  {
    type: 'function' as const,
    name: 'validate_cv',
    description:
      'Runs deterministic schema + DoD validation checks for the current session (no PDF render). Use to decide next missing fields/edits.',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        session_id: { type: 'string' as const, description: 'Session identifier' },
      },
      required: ['session_id'],
      additionalProperties: false,
    },
  },
  {
    type: 'function' as const,
    name: 'generate_cv_from_session',
    description: 'Generates a PDF from CV data stored in the session (replaces generate_cv_action).',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        session_id: {
          type: 'string' as const,
          description: 'Session identifier',
        },
        language: {
          type: 'string' as const,
          enum: ['en', 'de', 'pl'],
          description: 'Optional language override',
        },
      },
      required: ['session_id'],
      additionalProperties: false,
    },
  },
  {
    type: 'function' as const,
    name: 'cv_session_search',
    description:
      'Search session data (cv_data + docx_prefill_unconfirmed + recent events) and return bounded previews. Use to recover education/contact/work without asking the user again.',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        session_id: { type: 'string' as const, description: 'Session identifier' },
        q: { type: 'string' as const, description: 'Optional text query (case-insensitive substring match)' },
        section: { type: 'string' as const, description: "Optional section hint (e.g., 'education', 'contact')" },
        limit: { type: 'integer' as const, description: 'Max hits (1..50, default 20)' },
      },
      required: ['session_id'],
      additionalProperties: false,
    },
  },
];
