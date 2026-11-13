<script setup lang="ts">
import { computed } from "vue";
import type { Survey } from "../types";
import { aiConfig } from "../defaults";
import AISettings from "./AISettings.vue";
const props = defineProps<{ survey: Survey; defaultModel: string }>();
const selectedAI = computed(() =>
  props.survey.ai_configs.find(
    (a) => a.ai_config_id === props.survey.survey_config.ai.config_id,
  ),
);
function newAI() {
  const a = aiConfig(
    `Default_${props.survey.ai_configs.length + 1}`,
    props.defaultModel,
  );
  props.survey.ai_configs.push(a);
  props.survey.survey_config.ai.config_id = a.ai_config_id;
}
</script>
<template>
  <div class="options-content settings-form">
    <section id="option-general">
      <h3>General</h3>
      <label id="setting-interface-language"
        >Interface Language<small
          >Select the language for respondent interface text. Question content
          is not translated.</small
        ><el-select
          v-model="survey.survey_config.general.interface_language"
          style="width: 230px"
          ><el-option label="English" value="en" /><el-option
            label="日本語"
            value="ja" /><el-option
            label="简体中文"
            value="zh-CN" /></el-select></label
      ><label id="setting-display-name"
        >Display Name<small
          >Survey title shown to respondents and in the browser tab.</small
        ><el-input
          v-model="survey.survey_config.general.display_name"
          maxlength="255" /></label
      ><label id="setting-description"
        >Survey Description<el-input
          v-model="survey.survey_config.general.survey_description"
          type="textarea"
          :rows="4"
          maxlength="10000" /></label
      ><label id="setting-question-numbers"
        ><el-checkbox
          v-model="survey.survey_config.general.show_question_numbers"
          >Question Numbers</el-checkbox
        ></label
      >
    </section>
    <section id="option-responses">
      <h3>Responses</h3>
      <label id="setting-back"
        ><el-checkbox v-model="survey.survey_config.responses.allow_back_button"
          >Back Button</el-checkbox
        ></label
      ><label id="setting-finish-later"
        ><el-checkbox
          v-model="survey.survey_config.responses.allow_finish_later"
          >Allow Respondents to Finish Later</el-checkbox
        ><small
          >Formal resume behavior awaits the Response module.</small
        ></label
      ><label id="setting-incomplete"
        >Incomplete Survey Responses<el-select
          v-model="survey.survey_config.responses.incomplete_response.action"
          ><el-option label="Record" value="record" /><el-option
            label="Delete"
            value="delete" /></el-select
        ><el-input-number
          v-model="
            survey.survey_config.responses.incomplete_response.timeout_days
          "
          :min="1"
        /><small
          >Days after last activity; formal cleanup awaits Response.</small
        ></label
      >
      <h3 id="setting-availability">Survey Availability</h3>
      <label
        >Open at<el-date-picker
          v-model="survey.survey_config.availability.open_at"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ssZ"
          clearable /></label
      ><label
        >Close at<el-date-picker
          v-model="survey.survey_config.availability.close_at"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ssZ"
          clearable /></label
      ><small
        >Availability applies to public Surveys after Publish is
        implemented.</small
      >
    </section>
    <section id="option-security">
      <h3>Security</h3>
      <label id="setting-referrer"
        ><el-checkbox
          v-model="survey.survey_config.security.allowed_referrer.enabled"
          >Allowed Referrer</el-checkbox
        ><el-select
          v-model="survey.survey_config.security.allowed_referrer.domains"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="Add domains"
          :disabled="
            !survey.survey_config.security.allowed_referrer.enabled
          " /></label
      ><label id="setting-duplicates"
        ><el-checkbox
          v-model="survey.survey_config.security.prevent_multiple_submissions"
          >Prevent Multiple Submissions</el-checkbox
        ></label
      ><label id="setting-indexing"
        ><el-checkbox
          v-model="survey.survey_config.security.prevent_search_indexing"
          >Prevent Search Indexing</el-checkbox
        ></label
      ><label id="setting-anonymous"
        ><el-checkbox
          v-model="survey.survey_config.security.anonymize_responses"
          >Anonymous Responses</el-checkbox
        ><small
          >Formal privacy behavior awaits Response Privacy design.</small
        ></label
      >
    </section>
    <section id="option-ai">
      <h3>AI</h3>
      <el-checkbox v-model="survey.survey_config.ai.enabled"
        >Enable Survey AI</el-checkbox
      ><label
        >Default AI Configuration<el-select
          v-model="survey.survey_config.ai.config_id"
          clearable
          :empty-values="[null, undefined, '']"
          :value-on-clear="null"
          ><el-option
            v-for="a in survey.ai_configs"
            :key="a.ai_config_id"
            :label="a.agent_name"
            :value="a.ai_config_id" /></el-select></label
      ><el-button @click="newAI">Add AI Configuration</el-button
      ><AISettings
        v-if="selectedAI"
        :config="selectedAI"
        :questions="
          survey.blocks
            .filter((b) => !b.is_deleted)
            .flatMap((b) => b.questions.filter((q) => !q.is_deleted))
        "
        :default-model="defaultModel"
      />
      <p class="muted">
        Each Flow Call AI uses its own Configuration. API keys are configured
        only on the server.
      </p>
    </section>
  </div>
</template>
