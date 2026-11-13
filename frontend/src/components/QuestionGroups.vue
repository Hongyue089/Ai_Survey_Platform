<script setup lang="ts">
import type { Block } from "../types";
import { id } from "../defaults";
const props = defineProps<{ block: Block }>();
function add() { (props.block.question_groups ||= []).push({ group_id: id(), name: "Question Group", question_ids: [], question_order: "original", display_mode: "all", display_count: 1 }); }
</script>
<template>
  <strong>Question Groups</strong>
  <div v-for="g in block.question_groups" :key="g.group_id" class="condition-group">
    <label>Group Name<el-input v-model="g.name" /></label>
    <label>Questions<el-select v-model="g.question_ids" multiple><el-option v-for="q in block.questions.filter(q => !q.is_deleted)" :key="q.question_id" :label="q.question_name" :value="q.question_id" :disabled="block.question_groups?.some(other => other.group_id !== g.group_id && other.question_ids.includes(q.question_id))" /></el-select></label>
    <label>Question Order<el-select v-model="g.question_order"><el-option label="Original Order" value="original"/><el-option label="Random Order" value="random"/></el-select></label>
    <label>Questions to Display<el-select v-model="g.display_mode"><el-option label="Display All" value="all"/><el-option label="Randomly display N questions" value="random_n"/></el-select></label>
    <label v-if="g.display_mode === 'random_n'">Display count<el-input-number v-model="g.display_count" :min="1" :max="Math.max(1, g.question_ids.length)"/> of {{g.question_ids.length}} questions</label>
    <button class="text-button" @click="block.question_groups = block.question_groups?.filter(other => other.group_id !== g.group_id)">Remove group</button>
  </div>
  <button class="text-button" @click="add">+ Question Group</button>
</template>
