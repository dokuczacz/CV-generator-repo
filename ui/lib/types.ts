// TypeScript types from openapi_cv_actions.yaml

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
  trainings?: string[];
  interests?: string;
  references?: string;
  photo_url?: string;
  data_privacy_consent?: string;
  further_experience?: FurtherExperience[];
}

export interface WorkExperience {
  date_range: string;
  employer: string;
  title: string;
  bullets: string[];
}

export interface Education {
  date_range: string;
  institution: string;
  title: string;
  details?: string;
}

export interface FurtherExperience {
  date_range: string;
  organization: string;
  title: string;
  bullets?: string[];
  details?: string;
}

export interface Language {
  language: string;
  level: string;
}

export interface GenerateCVResponse {
  success: boolean;
  pdf_base64: string;
  filename?: string;
  validation?: {
    is_valid: boolean;
    errors: ValidationError[];
    warnings: string[];
  };
}

export interface ValidationError {
  field: string;
  current_value: any;
  limit?: number;
  excess?: number;
  message: string;
  suggestion?: string;
}
