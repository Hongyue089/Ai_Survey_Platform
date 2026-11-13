export type QuestionType =
  "multiple_choice" | "text_entry" | "text_graphic" | "matrix";
export interface Choice {
  choice_id: string;
  value: number;
  label: string;
}
export interface Statement {
  statement_id: string;
  label: string;
}
export interface ResponseTimeConfig {
  enabled: boolean;
  start_timing: "page_displayed";
  end_timing: "first_interaction" | "final_response";
}
export interface MCConfig {
  response_time: ResponseTimeConfig;
  answer_type: "single" | "multiple";
  format: "list" | "dropdown";
  layout: "vertical" | "horizontal" | "2_columns" | "3_columns";
  min_selection: number;
  max_selection: number;
  choices: Choice[];
}
export interface TextConfig {
  input_type: "single_line" | "text_area";
  placeholder: string;
  max_characters: number;
}
export interface MatrixConfig {
  matrix_type: "likert";
  answer_type: "single" | "multiple";
  statements: Statement[];
  scale_points: Choice[];
}
interface QuestionBase {
  question_id: string;
  question_name: string;
  question_text: string;
  sort_order: number;
  required: boolean;
  is_deleted: boolean;
  deleted_at: string | null;
}
export type Question =
  | (QuestionBase & { question_type: "multiple_choice"; config: MCConfig })
  | (QuestionBase & { question_type: "text_entry"; config: TextConfig })
  | (QuestionBase & {
      question_type: "text_graphic";
      config: Record<string, never>;
    })
  | (QuestionBase & { question_type: "matrix"; config: MatrixConfig });
export interface QuestionGroup {
  group_id: string; name: string; question_ids: string[];
  question_order: "original" | "random";
  display_mode: "all" | "random_n"; display_count: number;
}
export interface Block {
  question_groups?: QuestionGroup[];
  block_id: string;
  block_name: string;
  sort_order: number;
  is_deleted: boolean;
  deleted_at: string | null;
  questions: Question[];
}
export type Answer =
  string | number | number[] | Record<string, number | number[] | null> | null;
export interface Condition {
  source_type: "question" | "variable" | "agent";
  source_id: string;
  operator: "equals" | "not_equals" | "contains" | "not_contains" | "greater" | "greater_equal" | "less" | "less_equal";
  value: string | number;
  connector: "AND" | "OR";
}
export interface ConditionGroup {
  group_id: string;
  path_name?: string;
  logic?: "AND" | "OR" | null;
  is_default?: boolean;
  connector: "AND" | "OR";
  conditions: Condition[];
  children: FlowElement[];
}
export type ElementType =
  | "block"
  | "branch"
  | "randomizer"
  | "block_randomizer"
  | "participant_randomizer"
  | "python_code"
  | "embedded_data"
  | "call_ai"
  | "end_survey";
export interface ElementConfig {
  end_information: string;
  name: string;
  condition_groups: ConditionGroup[];
  number_to_present: number;
  evenly_present: boolean;
  routing_mode?: "first" | "all" | null;
  randomization_mode?: "select" | "shuffle" | "simple" | "balanced" | null;
  python_code?: string;
  variable_name: string;
  value: string | number;
}
export interface FlowElement {
  element_id: string;
  type: ElementType;
  sort_order: number;
  block_id: string | null;
  ai_config_id: string | null;
  config: ElementConfig;
  children: FlowElement[];
}
export interface FlowTrash {
  element: FlowElement;
  parent_id: string | null;
  group_id: string | null;
  position: number;
  deleted_at: string;
}
export interface FlowData {
  schema_version: 1;
  elements: FlowElement[];
  trash: FlowTrash[];
}
export interface LoggingConfig {
  save_prompt: boolean;
  save_response: boolean;
  save_token_usage: boolean;
  save_latency: boolean;
  save_error: boolean;
}
export interface AIConfig {
  ai_config_id: string;
  config_name: string;
  config_version: number;
  agent_name: string;
  provider: "openai";
  model: string;
  system_prompt: string;
  context_template: string;
  user_message_template: string;
  input_source_config: { question_id: string | null; include_previous_conversation?: boolean; allow_participant_quit?: boolean };
  temperature: number;
  top_p: number | null;
  max_output_tokens: number;
  max_turns: number;
  include_history: boolean;
  history_window: number | null;
  end_condition: "max_turns_reached";
  timeout_seconds: number;
  max_retries: number;
  failure_behavior: "skip" | "show_error" | "use_default_value" | "end_survey";
  response_format: "text" | "json";
  logging_config: LoggingConfig;
}
export interface SurveyOptions {
  general: {
    interface_language: "en" | "ja" | "zh-CN";
    display_name: string;
    survey_description: string;
    show_question_numbers: boolean;
  };
  responses: {
    allow_back_button: boolean;
    allow_finish_later: boolean;
    incomplete_response: { action: "record" | "delete"; timeout_days: number };
  };
  availability: { open_at: string | null; close_at: string | null };
  security: {
    allowed_referrer: { enabled: boolean; domains: string[] };
    prevent_multiple_submissions: boolean;
    bot_detection_enabled: false;
    prevent_search_indexing: boolean;
    anonymize_responses: boolean;
  };
  ai: { enabled: boolean; config_id: string | null };
}
export interface WorkingData {
  survey_name: string;
  survey_config: SurveyOptions;
  blocks: Block[];
  flow: FlowData;
  ai_configs: AIConfig[];
}
export interface Survey extends WorkingData {
  survey_id: string;
  project_type: "survey";
  status: "draft" | "published" | "closed";
  working_version: number;
  updated_at: string;
  created_at: string;
  role: "owner" | "editor" | "viewer";
}
export interface Project {
  survey_id: string;
  project_type: "survey";
  survey_name: string;
  status: Survey["status"];
  created_at: string;
  updated_at: string;
  question_count: number;
  response_count: number;
}
export interface ProjectPage {
  items: Project[];
  page: number;
  page_size: number;
  total: number;
}
export interface Revision {
  revision_id: string;
  revision_number: number;
  save_type: "auto" | "apply" | "restore" | "published";
  source: "survey" | "legacy_flow" | "publication";
  created_at: string;
  created_by: string;
  block_count: number;
  question_count: number;
  element_count: number;
}
export interface Capabilities {
  development_user: string;
  default_model: string;
  ai_ready: boolean;
  autosave_seconds: number;
  options_autosave_seconds: number;
}
export type PreviewPage =
  | { kind: "block"; element_id: string; page_id: string; block: Block }
  | {
      kind: "ai";
      element_id: string;
      conversation_id: string;
      config: Pick<AIConfig, "agent_name" | "max_turns" | "failure_behavior">;
      messages: { role: "user" | "assistant"; content: string }[];
      turn_count: number;
      done: boolean;
      can_quit?: boolean;
      error: string | null;
    }
  | { kind: "python_error"; name: string; error: string; message: string; line?: number; element_id: string }
  | { kind: "end"; end_information: string };
export interface TimingEvent { question_id: string; event: "question_displayed" | "option_selected" | "page_submitted"; at: string; elapsed_ms: number; value?: Answer; }
export interface PageTiming { question_id: string; events: TimingEvent[]; }
export interface Preview {
  snapshot_id: string | null;
  revision_id: string | null;
  submitted: boolean;
  failed: boolean;
  execution_path: { element_id: string; label: string }[];
  timing_debug: Record<string, unknown>[];
  preview_session_id: string;
  survey_id: string;
  page: PreviewPage;
  answers: Record<string, Answer>;
  survey_config: SurveyOptions;
  survey_name: string;
  can_back: boolean;
  can_continue: boolean;
  working_version: number;
  expires_at: string;
}


export interface PreviewDataSnapshot {
  snapshot_id: string;
  created_at: string;
  response_count: number;
}
export interface PreviewDataPage {
  columns: {question_id: string; name: string}[];
  items: {response_id: string; submitted_at: string; answers: Record<string, Answer>; content: unknown[]}[];
  total: number;
  page_size: number;
}
