import type { Condition, ConditionGroup, ElementType, FlowElement, MCConfig, Survey } from "./types";

export const elementLabels: Record<ElementType, string> = {
  block: "Block",
  branch: "Branch",
  randomizer: "Randomizer",
  block_randomizer: "Block Randomizer",
  participant_randomizer: "Participant Randomizer",
  python_code: "Python Code",
  embedded_data: "Embedded Variable",
  call_ai: "AI Conversation Agent",
  end_survey: "End of Survey",
};

export const operators: Record<Condition["operator"], string> = {
  equals: "Equals (=)",
  not_equals: "Does not equal (≠)",
  contains: "Contains",
  not_contains: "Does not contain",
  greater: "Greater than (>)",
  greater_equal: "Greater or equal (≥)",
  less: "Less than (<)",
  less_equal: "Less or equal (≤)",
};

export function conditionText(path: ConditionGroup, survey: Survey) {
  if (path.is_default) return "Otherwise";
  return path.conditions.map((condition, index) => {
    const question = condition.source_type === "question"
      ? survey.blocks.flatMap(block => block.questions).find(q => q.question_id === condition.source_id)
      : undefined;
    const agent = condition.source_type === "agent"
      ? survey.ai_configs.find(item => item.ai_config_id === condition.source_id)
      : undefined;
    let value = String(condition.value);
    if (question?.question_type === "multiple_choice" && value) {
      const choice = (question.config as MCConfig).choices.find(item =>
        item.value === condition.value || item.choice_id === condition.value);
      value = choice ? choice.label || String(choice.value) : `[Deleted option: ${value}]`;
    }
    return [
      index ? path.logic ?? condition.connector : "",
      question?.question_name || agent?.agent_name || condition.source_id || "Choose source",
      operators[condition.operator],
      value ? `"${value}"` : "",
    ].filter(Boolean).join(" ");
  }).join(" ");
}

export function elementName(node: FlowElement, survey: Survey) {
  if (node.type === "call_ai")
    return survey.ai_configs.find(agent => agent.ai_config_id === node.ai_config_id)?.agent_name || elementLabels.call_ai;
  if (node.type === "block") {
    const block = survey.blocks.find(item => item.block_id === node.block_id && !item.is_deleted);
    return node.config.name || block?.block_name || (node.block_id ? "Invalid Block" : "Choose Block");
  }
  return node.config.name || elementLabels[node.type];
}
