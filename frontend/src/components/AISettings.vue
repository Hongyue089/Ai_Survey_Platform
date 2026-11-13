<script setup lang="ts">
import { computed } from "vue";
import type { AIConfig, Question } from "../types";
const props = defineProps<{
  config: AIConfig;
  questions: Question[];
  defaultModel: string;
  duplicateName?: boolean;
}>();
const outputVariable = computed(() => "{#" + props.config.agent_name.trim().toLowerCase().replace(/\s+/g, "_") + "#}");
function copyOutput() { return navigator.clipboard.writeText(outputVariable.value); }
const allowQuit = computed({
  get: () => props.config.input_source_config.allow_participant_quit ?? true,
  set: value => { props.config.input_source_config.allow_participant_quit = value; },
});
</script>
<template>
  <div class="settings-form ai-settings">
    <section class="agent-section">
      <h3>1. Agent Identity</h3>
      <label>Agent Name<el-input v-model="config.agent_name" maxlength="255" :class="{ 'agent-name-error': duplicateName }" /></label>
      <small v-if="duplicateName" role="alert" class="flow-configuration-error">An agent with this name already exists.</small>
      <label>Output Variable
        <div class="agent-output">
          <el-input :model-value="outputVariable" readonly />
          <el-button round aria-label="Copy output variable" @click="copyOutput">Copy</el-button>
        </div>
      </label>
      <small>References the complete conversation history.</small>
    </section>
    <section class="agent-section">
      <h3>2. Prompt Configuration</h3>
      <label>Role Instruction / System Prompt<el-input v-model="config.system_prompt" type="textarea" :rows="3"
        placeholder="Define the AI’s role, conversational style, and behavioral instructions." /></label>
      <label>Context<el-input v-model="config.context_template" type="textarea" :rows="5"
        placeholder="Provide study background or reference earlier survey data." /></label>
      <el-checkbox v-model="config.input_source_config.include_previous_conversation">Include Previous AI Conversations</el-checkbox>
      <label>User Message Template<el-input v-model="config.user_message_template" type="textarea" :rows="3"
        placeholder="Define the task used to generate each AI response." /></label>
    </section>
    <section class="agent-section">
      <h3>3. Conversation Settings</h3>
      <label>Conversation Mode<el-radio-group model-value="text">
        <el-radio value="text">Text Interview</el-radio>
        <el-radio value="voice" disabled>Voice Interview</el-radio>
      </el-radio-group></label>
      <label>Max Turns <el-input-number v-model="config.max_turns" :min="1" /></label>
      <small>Number of completed participant response turns.</small>
      <el-checkbox v-model="allowQuit">Allow Participants to Quit</el-checkbox>
    </section>
    <el-collapse
      ><el-collapse-item title="Advanced Settings"
        ><label>Input Source<el-select v-model="config.input_source_config.question_id" clearable :value-on-clear="null">
          <el-option v-for="question in questions" :key="question.question_id" :label="question.question_name" :value="question.question_id" />
        </el-select></label>
        <label>Temperature<el-input-number v-model="config.temperature" :min="0" :max="1" :step="0.1" /></label>
        <label
          >Model<el-input
            v-model="config.model"
            :placeholder="
              defaultModel || 'Configure AI_MODEL on server'
            " /></label
        ><label
          >Max Output Tokens<el-input-number
            v-model="config.max_output_tokens"
            :min="1" /></label
        ><el-checkbox v-model="config.include_history"
          >Include history</el-checkbox
        ><label
          >History Window<el-input-number
            v-model="config.history_window"
            :min="0" /></label
        ><label
          >Timeout (seconds)<el-input-number
            v-model="config.timeout_seconds"
            :min="1"
            :max="300" /></label
        ><label
          >Max Retries<el-input-number
            v-model="config.max_retries"
            :min="0"
            :max="5" /></label
        ><label
          >Failure Behavior<el-select v-model="config.failure_behavior"
            ><el-option label="Show error" value="show_error" /><el-option
              label="Skip"
              value="skip" /><el-option
              label="Use empty default value"
              value="use_default_value" /><el-option
              label="End survey"
              value="end_survey" /></el-select></label
        ><label
          >Response Format<el-select v-model="config.response_format"
            ><el-option label="Text" value="text" /><el-option
              label="JSON"
              value="json" /></el-select></label
        ><label v-for="(_, key) in config.logging_config" :key="key"
          ><el-checkbox v-model="config.logging_config[key]">{{
            key.replaceAll("_", " ")
          }}</el-checkbox></label
        ></el-collapse-item
      ></el-collapse
    >
  </div>
</template>
