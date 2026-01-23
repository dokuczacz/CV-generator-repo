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
      description: 'Updates CV session fields (single or batch edits).',
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
      name: 'fetch_job_posting_text',
      description:
        'Fetches and extracts readable text from a job posting URL. Use as a fallback when job_posting_text is missing.',
      parameters: {
        type: 'object' as const,
        properties: {
          url: {
            type: 'string',
            description: 'Job posting URL to fetch',
          },
        },
        required: ['url'],
        additionalProperties: false,
      },
    },
  },
  {
    type: 'function' as const,
    function: {
      name: 'process_cv_orchestrated',
      description:
        'Single-call workflow: extract, apply edits, validate, and generate PDF. Creates or reuses session.',
      parameters: {
        type: 'object' as const,
        properties: {
          session_id: {
            type: 'string',
            description: 'Optional: reuse an existing session',
          },
          docx_base64: {
            type: 'string',
            description: 'Required if no session_id: Base64 encoded DOCX',
          },
          language: {
            type: 'string',
            enum: ['en', 'de', 'pl'],
            description: 'CV language (default: en)',
          },
          edits: {
            type: 'array',
            description: 'Optional list of edits to apply before generation',
            items: {
              type: 'object',
              properties: {
                field_path: {
                  type: 'string',
                  description: "Field path (e.g., 'full_name', 'work_experience[0].title')",
                },
                value: {
                  description: 'New value for the field',
                },
              },
              required: ['field_path', 'value'],
            },
          },
          extract_photo: {
            type: 'boolean',
            description: 'Whether to extract photo (default: true)',
          },
        },
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
    description: 'Updates CV session fields (single, batch edits[], or one-section cv_patch).',
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
      },
      required: ['session_id'],
      additionalProperties: false,
    },
  },
  {
    type: 'function' as const,
    name: 'update_cv_fields',
    description: 'Batch update multiple fields in the CV session to reduce tool calls.',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        session_id: {
          type: 'string' as const,
          description: 'Session identifier',
        },
        edits: {
          type: 'array' as const,
          description: 'List of edits to apply',
          items: {
            type: 'object' as const,
            properties: {
              field_path: { type: 'string' as const, description: 'Field path to update' },
              value: { description: 'New value for the field' },
            },
            required: ['field_path', 'value'],
          },
        },
      },
      required: ['session_id', 'edits'],
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
    name: 'fetch_job_posting_text',
    description:
      'Fetches and extracts readable text from a job posting URL. Use as a fallback when job_posting_text is missing.',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        url: {
          type: 'string' as const,
          description: 'Job posting URL to fetch',
        },
      },
      required: ['url'],
      additionalProperties: false,
    },
  },
  {
    type: 'function' as const,
    name: 'process_cv_orchestrated',
    description:
      'Single-call workflow: extract, apply edits, validate, and generate PDF. Creates or reuses session.',
    strict: false,
    parameters: {
      type: 'object' as const,
      properties: {
        session_id: {
          type: 'string' as const,
          description: 'Optional: reuse an existing session',
        },
        docx_base64: {
          type: 'string' as const,
          description: 'Required if no session_id: Base64 encoded DOCX',
        },
        language: {
          type: 'string' as const,
          enum: ['en', 'de', 'pl'],
          description: 'CV language (default: en)',
        },
        edits: {
          type: 'array' as const,
          description: 'Optional list of edits to apply before generation',
          items: {
            type: 'object' as const,
            properties: {
              field_path: {
                type: 'string' as const,
                description: "Field path (e.g., 'full_name', 'work_experience[0].title')",
              },
              value: {
                description: 'New value for the field',
              },
            },
            required: ['field_path', 'value'],
          },
        },
        extract_photo: {
          type: 'boolean' as const,
          description: 'Whether to extract photo (default: true)',
        },
      },
      additionalProperties: false,
    },
  },
];
