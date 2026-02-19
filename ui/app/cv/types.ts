export interface Message {
  role: 'user' | 'assistant';
  content: string;
  pdfBase64?: string;
}

export interface UIActionButton {
  id: string;
  label: string;
  style?: 'primary' | 'secondary' | 'tertiary';
}

export interface UIActionField {
  key: string;
  label: string;
  value: string;
  type?: 'text' | 'textarea';
  editable?: boolean;
  placeholder?: string;
}

export interface UIAction {
  kind: string;
  stage?: string;
  title?: string;
  text?: string;
  actions?: UIActionButton[];
  fields?: UIActionField[];
  disable_free_text?: boolean;
}

export type StageUpdate = {
  step: string;
  ok?: boolean;
  mode?: string;
  error?: string;
  [key: string]: unknown;
};

export type CVSessionPreview = {
  cv_data: Record<string, unknown>;
  metadata: Record<string, unknown>;
  readiness: Record<string, unknown>;
};

export type WizardStep = {
  current: number;
  total: number;
} | null;

export type StepperItem = {
  n: number;
  label: string;
  targetWizardStage: string;
};
