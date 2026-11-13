import type { Survey, Question, FlowElement } from "./types";
export function references(survey: Survey, q: Question, values?: (number | string)[]) {
  const result: string[] = [];
  function walk(elements: FlowElement[]) {
    for (const e of elements) {
      if (e.config.condition_groups.some(g => g.conditions.some(c => c.source_type === "question" && c.source_id === q.question_id && (!values || values.includes(c.value))))) result.push(e.config.name || e.element_id);
      if (!values && e.type === "call_ai") {
        const a = survey.ai_configs.find(a => a.ai_config_id === e.ai_config_id);
        if (a && (a.input_source_config.question_id === q.question_id || [a.context_template, a.user_message_template].some(t => [q.question_id, q.question_name].some(token => t.includes("{#" + token + "#}"))))) result.push(a.agent_name);
      }
      walk(e.children); for (const g of e.config.condition_groups) walk(g.children);
    }
  }
  walk(survey.flow.elements); for (const t of survey.flow.trash) walk([t.element]);
  return [...new Set(result)];
}
