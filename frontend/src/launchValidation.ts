import type { FlowElement, Survey } from "./types";

export function validateLaunch(survey: Survey) {
  if (!survey.flow.elements.length)
    throw new Error("No Flow configured. Please configure the Survey Flow before continuing.");

  function check(elements: FlowElement[]) {
    for (const node of elements) {
      if (node.type === "block" && !node.block_id)
        throw new Error("Choose a Block for each Block element.");
      if (node.type === "branch" || node.type === "participant_randomizer") {
        const groups = node.config.condition_groups;
        if (node.type === "branch" && (!groups.length || groups.some(group =>
          !group.is_default && (!group.conditions.length || group.conditions.some(condition => !condition.source_id)))))
          throw new Error("Complete the conditions for each Branch.");
        if (node.type === "participant_randomizer" && groups.length < 2)
          throw new Error("Participant Randomizer needs at least two Paths.");
        for (const group of groups) check(group.children);
      }
      if (node.type === "randomizer" && node.config.number_to_present > node.children.length)
        throw new Error("Randomizer count exceeds child count.");
      if (node.type === "block_randomizer" && (!node.children.length ||
          (node.config.randomization_mode !== "shuffle" && node.config.number_to_present > node.children.length)))
        throw new Error("Block Randomizer does not have enough Blocks.");
      if (node.type === "python_code" && !node.config.python_code?.trim())
        throw new Error("Enter Python Code before starting Preview.");
      if (node.type === "embedded_data" && !node.config.variable_name.trim())
        throw new Error("Enter a variable name for each Embedded Data element.");
      if (node.type === "call_ai") {
        const agent = survey.ai_configs.find((item) => item.ai_config_id === node.ai_config_id);
        if (!agent?.system_prompt.trim() || !agent.user_message_template.trim())
          throw new Error("Enter System Prompt and User Message Template for each Conversation.");
      }
      check(node.children);
    }
  }

  check(survey.flow.elements);
}
