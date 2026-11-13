<script setup lang="ts">
import type { Question, QuestionType, Survey } from "../types";
import { ElMessage } from "element-plus";
import { references } from "../dependencies";
import { question as makeQuestion, id } from "../defaults";
const props = defineProps<{ question: Question; survey: Survey }>(),
  emit = defineEmits<{ (e: "delete"): void }>();
function typeChange(type: QuestionType) {
  const old = props.question;
  const refs = references(props.survey, old);
  if (type !== old.question_type && refs.length) { ElMessage.warning("Referenced by Flow: " + refs.join(", ")); return; }
  const replacement = makeQuestion(type, old.question_name, old.sort_order);
  Object.assign(old, replacement, {
    question_id: old.question_id,
    question_text: old.question_text,
    required: type === "text_graphic" ? false : old.required,
  });
}
function resize(key: "choices" | "statements" | "scale_points", count: number) {
  const q = props.question;
  if (q.question_type === "multiple_choice" && key === "choices") {
    const a = q.config.choices;
    const refs = references(props.survey, q, a.slice(count).flatMap(c => [c.value, c.choice_id]));
    if (refs.length) { ElMessage.warning("Options referenced by Flow: " + refs.join(", ")); return; }
    while (a.length < count)
      a.push({
        choice_id: id(),
        value: Math.max(0, ...a.map((c) => c.value)) + 1,
        label: "",
      });
    a.splice(count);
    q.config.max_selection = Math.min(q.config.max_selection, count);
    q.config.min_selection = Math.min(
      q.config.min_selection,
      q.config.max_selection,
    );
  } else if (q.question_type === "matrix") {
    if (key === "statements") {
      const a = q.config.statements;
      while (a.length < count) a.push({ statement_id: id(), label: "" });
      a.splice(count);
    } else if (key === "scale_points") {
      const a = q.config.scale_points;
      while (a.length < count)
        a.push({
          choice_id: id(),
          value: Math.max(0, ...a.map((c) => c.value)) + 1,
          label: "",
        });
      a.splice(count);
    }
  }
}
function answerType() {
  const q = props.question;
  if (
    q.question_type === "multiple_choice" &&
    q.config.answer_type === "single"
  )
    q.config.min_selection = q.config.max_selection = 1;
}
</script>
<template>
  <div class="settings-form">
    <label
      >Question Name<el-input
        v-model="question.question_name"
        maxlength="255" /></label
    ><label
      >Question Type<el-select
        :model-value="question.question_type"
        @update:model-value="typeChange"
        ><el-option label="Multiple Choice" value="multiple_choice" /><el-option
          label="Text Entry"
          value="text_entry" /><el-option
          label="Text / Graphic"
          value="text_graphic" /><el-option
          label="Matrix Table"
          value="matrix" /></el-select
    ></label>
    <template v-if="question.question_type === 'multiple_choice'"
      ><label
        >Answer Type<el-select
          v-model="question.config.answer_type"
          @change="answerType"
          ><el-option label="Single Answer" value="single" /><el-option
            label="Multiple Answers"
            value="multiple" /></el-select></label
      ><label
        >Number of Choices<el-input-number
          :model-value="question.config.choices.length"
          :min="1"
          :max="20"
          @update:model-value="resize('choices', Number($event))" /></label
      ><label
        >Format<el-select v-model="question.config.format"
          ><el-option label="List" value="list" /><el-option
            label="Dropdown"
            value="dropdown" /></el-select></label
      ><label v-if="question.config.format === 'list'"
        >Layout<el-select v-model="question.config.layout"
          ><el-option label="Vertical" value="vertical" /><el-option
            label="Horizontal"
            value="horizontal" /><el-option
            label="2 Columns"
            value="2_columns" /><el-option
            label="3 Columns"
            value="3_columns" /></el-select></label
      ><label
        >Minimum Selection<el-input-number
          v-model="question.config.min_selection"
          :min="0"
          :max="question.config.max_selection"
          :disabled="question.config.answer_type === 'single'" /></label
      ><label
        >Maximum Selection<el-input-number
          v-model="question.config.max_selection"
          :min="Math.max(1, question.config.min_selection)"
          :max="question.config.choices.length"
          :disabled="question.config.answer_type === 'single'" /></label
    ></template>
    <template v-else-if="question.question_type === 'text_entry'"
      ><label
        >Input Type<el-select v-model="question.config.input_type"
          ><el-option label="Single Line" value="single_line" /><el-option
            label="Text Area"
            value="text_area" /></el-select></label
      ><label
        >Placeholder<el-input v-model="question.config.placeholder" /></label
      ><label
        >Maximum Characters<el-input-number
          v-model="question.config.max_characters"
          :min="1"
          :max="100000" /></label
    ></template>
    <template v-else-if="question.question_type === 'matrix'"
      ><label
        >Matrix Type<el-select v-model="question.config.matrix_type"
          ><el-option label="Likert" value="likert" /></el-select></label
      ><label
        >Answer Type<el-select v-model="question.config.answer_type"
          ><el-option label="Allow One Answer" value="single" /><el-option
            label="Allow Multiple Answers"
            value="multiple" /></el-select></label
      ><label
        >Number of Statements<el-input-number
          :model-value="question.config.statements.length"
          :min="1"
          :max="20"
          @update:model-value="resize('statements', Number($event))" /></label
      ><label
        >Scale Points<el-input-number
          :model-value="question.config.scale_points.length"
          :min="1"
          :max="20"
          @update:model-value="resize('scale_points', Number($event))" /></label
    ></template>
    <template v-if="question.question_type === 'multiple_choice'">
      <el-checkbox v-model="question.config.response_time.enabled">Measure response time</el-checkbox>
      <template v-if="question.config.response_time.enabled">
        <label>Start timing<el-input model-value="When page is displayed" disabled /></label>
        <label>End timing<el-select v-model="question.config.response_time.end_timing"><el-option label="First interaction" value="first_interaction"/><el-option label="Final response / Next" value="final_response"/></el-select></label>
      </template>
    </template>
    <label
      v-if="question.question_type !== 'text_graphic'"
      class="checkbox-label"
      ><el-checkbox v-model="question.required">Required</el-checkbox></label
    ><el-button class="danger-soft" @click="emit('delete')"
      >♜ Delete Question</el-button
    >
  </div>
</template>
