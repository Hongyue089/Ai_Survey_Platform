import type {
  Question,
  QuestionType,
  FlowElement,
  ElementType,
  AIConfig,
  ConditionGroup,
} from "./types";
export const id = () => crypto.randomUUID();
export const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));
export function question(
  type: QuestionType,
  name: string,
  order: number,
): Question {
  const base = {
    question_id: id(),
    question_name: name,
    question_text: "",
    sort_order: order,
    required: false,
    is_deleted: false,
    deleted_at: null,
  };
  if (type === "multiple_choice")
    return {
      ...base,
      question_type: type,
      config: {
        response_time: { enabled: false, start_timing: "page_displayed", end_timing: "final_response" },
        answer_type: "single",
        format: "list",
        layout: "vertical",
        min_selection: 1,
        max_selection: 1,
        choices: Array.from({ length: 2 }, (_, i) => ({
          choice_id: id(),
          value: i + 1,
          label: "",
        })),
      },
    };
  if (type === "text_entry")
    return {
      ...base,
      question_type: type,
      config: {
        input_type: "single_line",
        placeholder: "",
        max_characters: 1000,
      },
    };
  if (type === "matrix")
    return {
      ...base,
      question_type: type,
      config: {
        matrix_type: "likert",
        answer_type: "single",
        statements: Array.from({ length: 3 }, () => ({
          statement_id: id(),
          label: "",
        })),
        scale_points: Array.from({ length: 5 }, (_, i) => ({
          choice_id: id(),
          value: i + 1,
          label: "",
        })),
      },
    };
  return { ...base, question_type: type, config: {} };
}
export const group = (): ConditionGroup => ({
  group_id: id(),
  connector: "AND",
  conditions: [
    {
      source_type: "question",
      source_id: "",
      operator: "equals",
      value: "",
      connector: "AND",
    },
  ],
  children: [],
});
export function element(type: ElementType): FlowElement {
  return {
    element_id: id(),
    type,
    sort_order: 1,
    block_id: null,
    ai_config_id: null,
    children: [],
    config: {
      end_information: "",
      name: type === "branch" ? "Branch" : "",
      condition_groups: type === "branch" ? [{ ...group(), logic: "AND" }] :
        type === "participant_randomizer" ? ["Path 1", "Path 2"].map(path_name => ({ ...group(), path_name, conditions: [] })) : [],
      routing_mode: type === "branch" ? "first" : null,
      randomization_mode: type === "block_randomizer" ? "select" : type === "participant_randomizer" ? "simple" : null,
      python_code: "",
      number_to_present: 1,
      evenly_present: false,
      variable_name: "",
      value: "",
    },
  };
}
export const aiConfig = (name: string, model: string): AIConfig => ({
  ai_config_id: id(),
  config_name: name,
  config_version: 1,
  agent_name: name,
  provider: "openai",
  model,
  system_prompt: "",
  context_template: "",
  user_message_template: "",
  input_source_config: { question_id: null },
  temperature: 0.7,
  top_p: null,
  max_output_tokens: 800,
  max_turns: 3,
  include_history: true,
  history_window: 10,
  end_condition: "max_turns_reached",
  timeout_seconds: 30,
  max_retries: 2,
  failure_behavior: "show_error",
  response_format: "text",
  logging_config: {
    save_prompt: true,
    save_response: true,
    save_token_usage: true,
    save_latency: true,
    save_error: true,
  },
});
