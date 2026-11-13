<script setup lang="ts">
import { computed } from "vue";
import type { FlowElement, ElementType, Survey } from "../types";
import { conditionText, elementLabels, elementName } from "../flowLabels";

const props = defineProps<{
  elements: FlowElement[];
  survey: Survey;
  selected: string | null;
  parentId?: string | null;
  groupId?: string | null;
  matches: string[];
  blocksOnly?: boolean;
}>();
const emit = defineEmits<{
  select: [id: string];
  insert: [type: ElementType, parent: string | null, group: string | null, index: number];
  action: [action: string, id: string];
}>();
const types: ElementType[] = [
  "block", "branch", "block_randomizer", "participant_randomizer", "call_ai", "python_code", "end_survey",
];
const allowed = computed(() => props.blocksOnly ? types.slice(0, 1) : types);
const editable = computed(() => props.survey.role !== "viewer");
function summary(node: FlowElement) {
  const name = elementName(node, props.survey);
  return node.type === "block" && !["Choose Block", "Invalid Block"].includes(name) ? `Show ${name}` : name;
}
function detail(node: FlowElement) {
  if (node.type === "block") {
    const block = props.survey.blocks.find(item => item.block_id === node.block_id && !item.is_deleted);
    const count = block?.questions.filter(q => !q.is_deleted && q.question_type !== "text_graphic").length;
    return count ? `(${count} questions)` : "";
  }
  if (node.type === "participant_randomizer") {
    if (node.config.condition_groups.length < 2) return "At least two paths required";
    return node.config.randomization_mode === "balanced" ? "Balanced Assignment" : "Simple Random Assignment";
  }
  if (node.type === "block_randomizer") {
    if (!node.children.length) return "Add candidate Blocks";
    if (node.config.randomization_mode === "shuffle") return "Shuffle Order";
    return node.config.number_to_present > node.children.length
      ? "Not enough candidate Blocks" : `Present ${node.config.number_to_present} Blocks`;
  }
  if (node.type === "randomizer") return `Present ${node.config.number_to_present} Elements`;
  return "";
}
</script>

<template>
  <div class="flow-diagram-level" :class="{ 'flow-diagram-nested': parentId }">
    <template v-for="(node, index) in elements" :key="node.element_id">
      <div v-if="index === 0 || elements[index - 1].type !== 'end_survey'"
        class="flow-diagram-insert" :class="{ 'flow-diagram-first': !index && !parentId }">
        <el-dropdown v-if="editable" trigger="click"
          @command="(type: ElementType) => emit('insert', type, parentId ?? null, groupId ?? null, index)">
          <button type="button" class="insert-plus" aria-label="Insert Flow element">+</button>
          <template #dropdown><el-dropdown-menu>
            <el-dropdown-item v-for="type in allowed" :key="type" :command="type">{{ elementLabels[type] }}</el-dropdown-item>
          </el-dropdown-menu></template>
        </el-dropdown>
      </div>

      <div class="flow-diagram-node-row">
        <button type="button" class="flow-diagram-node" :id="'flow-' + node.element_id" aria-haspopup="dialog"
          :class="{ selected: selected === node.element_id, 'end-node': node.type === 'end_survey', 'search-match': matches.includes(node.element_id) }"
          @click="emit('select', node.element_id)">
          <span>{{ summary(node) }}</span>
          <small v-if="detail(node)">{{ detail(node) }}</small>
        </button>
        <el-dropdown v-if="editable" trigger="click" class="flow-node-actions"
          @command="(action: string) => emit('action', action, node.element_id)">
          <button type="button" aria-label="Element actions">⋯</button>
          <template #dropdown><el-dropdown-menu>
            <el-dropdown-item command="rename" :disabled="node.type === 'end_survey'">Rename</el-dropdown-item>
            <el-dropdown-item command="duplicate">Duplicate</el-dropdown-item>
            <el-dropdown-item command="up" :disabled="index === 0">Move Up</el-dropdown-item>
            <el-dropdown-item command="down" :disabled="index === elements.length - 1">Move Down</el-dropdown-item>
            <el-dropdown-item command="delete" divided>Delete</el-dropdown-item>
          </el-dropdown-menu></template>
        </el-dropdown>
      </div>

      <div v-if="node.type === 'branch' || node.type === 'participant_randomizer'" class="flow-diagram-fork">
        <div v-for="(path, pathIndex) in node.config.condition_groups" :key="path.group_id" class="flow-diagram-path">
          <div class="flow-path-label" :class="{ 'search-match': matches.includes(node.element_id) }">
            <span>{{ path.path_name || (path.is_default ? "Otherwise" : `Path ${pathIndex + 1}`) }}</span>
            <small v-if="node.type === 'branch'">{{ conditionText(path, survey) }}</small>
          </div>
          <FlowTree :elements="path.children" :survey="survey" :selected="selected" :matches="matches"
            :parent-id="node.element_id" :group-id="path.group_id" @select="emit('select', $event)"
            @insert="(t, p, g, i) => emit('insert', t, p, g, i)" @action="(a, id) => emit('action', a, id)" />
        </div>
      </div>
      <FlowTree v-else-if="node.type === 'randomizer' || node.type === 'block_randomizer'"
        :elements="node.children" :survey="survey" :selected="selected" :matches="matches"
        :parent-id="node.element_id" :blocks-only="node.type === 'block_randomizer'" @select="emit('select', $event)"
        @insert="(t, p, g, i) => emit('insert', t, p, g, i)" @action="(a, id) => emit('action', a, id)" />
    </template>

    <div v-if="editable && (!elements.length || elements[elements.length - 1].type !== 'end_survey')"
      class="flow-diagram-insert flow-diagram-tail" :class="{ 'flow-diagram-first': !elements.length && !parentId }">
      <el-dropdown trigger="click"
        @command="(type: ElementType) => emit('insert', type, parentId ?? null, groupId ?? null, elements.length)">
        <button type="button" class="insert-plus" aria-label="Add Flow element">+</button>
        <template #dropdown><el-dropdown-menu>
          <el-dropdown-item v-for="type in allowed" :key="type" :command="type">{{ elementLabels[type] }}</el-dropdown-item>
        </el-dropdown-menu></template>
      </el-dropdown>
    </div>
  </div>
</template>
