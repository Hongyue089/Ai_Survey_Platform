<script setup lang="ts">
import { ref } from "vue";
import type { Question } from "../types";
import InlineText from "./InlineText.vue";
defineProps<{ question: Question }>();
const dialog = ref(false);
</script>
<template>
  <div class="question-design">
    <InlineText
      v-model="question.question_text"
      :placeholder="
        question.question_type === 'text_graphic'
          ? 'Write your text here…'
          : 'Question text'
      "
      multiline
    />
    <template v-if="question.question_type === 'multiple_choice'">
      <button
        v-if="question.config.format === 'dropdown'"
        class="text-button choices-link"
        @click="dialog = true"
      >
        Click here to edit choices.
      </button>
      <div v-else class="choice-design" :class="question.config.layout">
        <div
          v-for="(c, i) in question.config.choices"
          :key="c.choice_id"
          class="choice-line"
        >
          <span>{{ question.config.answer_type === "single" ? "○" : "□" }}</span
          ><InlineText v-model="c.label" :placeholder="`Choice ${i + 1}`" />
        </div>
      </div>
      <el-dialog v-model="dialog" title="Edit choices" width="480px"
        ><div
          v-for="(c, i) in question.config.choices"
          :key="c.choice_id"
          class="choice-line"
        >
          <span>{{ i + 1 }}</span
          ><el-input v-model="c.label" :placeholder="`Choice ${i + 1}`" /></div
      ></el-dialog>
    </template>
    <el-input
      v-else-if="question.question_type === 'text_entry'"
      disabled
      :type="question.config.input_type === 'text_area' ? 'textarea' : 'text'"
      :placeholder="question.config.placeholder"
      :rows="3"
    />
    <div v-else-if="question.question_type === 'matrix'" class="matrix-scroll">
      <div
        class="matrix-grid"
        :style="{
          gridTemplateColumns: `minmax(170px,2fr) repeat(${question.config.scale_points.length},minmax(100px,1fr))`,
          minWidth: `${170 + question.config.scale_points.length * 100}px`,
        }"
      >
        <div />
        <div
          v-for="(c, i) in question.config.scale_points"
          :key="c.choice_id"
          class="matrix-label"
        >
          <InlineText v-model="c.label" :placeholder="`Scale Point ${i + 1}`" />
        </div>
        <template
          v-for="(s, i) in question.config.statements"
          :key="s.statement_id"
          ><InlineText
            v-model="s.label"
            :placeholder="`Statement ${i + 1}`"
          /><span
            v-for="c in question.config.scale_points"
            :key="c.choice_id"
            class="matrix-cell"
            >{{ question.config.answer_type === "single" ? "○" : "□" }}</span
          ></template
        >
      </div>
    </div>
  </div>
</template>
