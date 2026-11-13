<script setup lang="ts">
import { computed } from "vue";
import { Delete } from "@element-plus/icons-vue";
import type { AIConfig, Condition, ConditionGroup, FlowElement, FlowTrash, MCConfig, Survey } from "../types";
import { group } from "../defaults";
import { conditionText, operators } from "../flowLabels";
import AISettings from "./AISettings.vue";

const props = defineProps<{
  element: FlowElement;
  survey: Survey;
  agent?: AIConfig;
  trash: FlowTrash[];
  defaultModel: string;
}>();
const emit = defineEmits<{ editBlock: [id: string] }>();
const config = computed(() => props.element.config);
const paths = computed(() => config.value.condition_groups);

function before(elements: FlowElement[], known: Set<string>): Set<string> | null {
  for (const node of elements) {
    if (node.element_id === props.element.element_id) return known;
    if (node.type === "block") {
      const block = props.survey.blocks.find(item => item.block_id === node.block_id && !item.is_deleted);
      for (const question of block?.questions ?? [])
        if (!question.is_deleted && question.question_type !== "text_graphic") known.add(question.question_id);
    }
    for (const path of node.config.condition_groups) {
      const found = before(path.children, new Set(known));
      if (found) return found;
    }
    const found = before(node.children, new Set(known));
    if (found) return found;
    if (node.type === "call_ai" && node.ai_config_id) known.add(node.ai_config_id);
    if (node.type === "end_survey") break;
  }
  return null;
}
const available = computed(() => before(props.survey.flow.elements, new Set()) ?? new Set<string>());
const questions = computed(() => props.survey.blocks.flatMap(block => block.questions)
  .filter(question => available.value.has(question.question_id)));
const agents = computed(() => props.survey.ai_configs.filter(agent => available.value.has(agent.ai_config_id)));

function addPath(fallback = false) {
  const path = { ...group(), path_name: fallback ? "Otherwise" : "", is_default: fallback, logic: "AND" as const };
  if (fallback || props.element.type === "participant_randomizer") path.conditions = [];
  const index = paths.value.findIndex(item => item.is_default);
  paths.value.splice(index < 0 ? paths.value.length : index, 0, path);
}
function deletePath(index: number) {
  const [path] = paths.value.splice(index, 1);
  path.children.forEach((element, position) => props.trash.push({
    element, position, parent_id: props.element.element_id, group_id: path.group_id,
    deleted_at: new Date().toISOString(),
  }));
}
function movePath(index: number, offset: number) {
  const target = index + offset;
  if (!paths.value[target] || paths.value[target].is_default || paths.value[index].is_default) return;
  [paths.value[index], paths.value[target]] = [paths.value[target], paths.value[index]];
}
function source(condition: Condition) {
  if (condition.source_type === "agent") return "agent:" + condition.source_id;
  if (condition.source_type === "variable") return "variable";
  return condition.source_id ? "question:" + condition.source_id : "";
}
function setSource(condition: Condition, selection: string) {
  const [type, id = ""] = selection.split(":");
  condition.source_type = type as Condition["source_type"];
  condition.source_id = id;
  condition.value = "";
}
function choices(condition: Condition) {
  if (condition.source_type !== "question") return [];
  const question = questions.value.find(item => item.question_id === condition.source_id);
  return question?.question_type === "multiple_choice" ? (question.config as MCConfig).choices : [];
}
const duplicateName = computed(() => !!props.agent && props.survey.ai_configs.some(agent =>
  agent.ai_config_id !== props.agent?.ai_config_id && agent.agent_name === props.agent?.agent_name));
</script>

<template>
  <div v-if="element.type === 'branch'" class="branch-configuration">
    <label>Branch Name<el-input v-model="config.name" /></label>
    <div class="branch-routing">
      <span>Routing Mode</span>
      <el-radio-group v-model="config.routing_mode">
        <el-radio value="first">First Matching Path (Recommended)</el-radio>
        <el-radio value="all">All Matching Paths</el-radio>
      </el-radio-group>
      <small v-if="!config.routing_mode">This branch uses the original group routing until you select a mode.</small>
    </div>
    <section v-for="(path, index) in paths" :key="path.group_id" class="branch-config-path">
      <div class="branch-section-header">
        <h3>{{ path.is_default ? "Otherwise" : `Path ${index + 1} — Conditions` }}</h3>
        <div class="branch-path-actions">
          <button v-if="!path.is_default && index" type="button" aria-label="Move path up" @click="movePath(index, -1)">↑</button>
          <button v-if="!path.is_default && paths[index + 1] && !paths[index + 1].is_default" type="button"
            aria-label="Move path down" @click="movePath(index, 1)">↓</button>
          <button v-if="paths.length > 1" type="button" aria-label="Delete path" @click="deletePath(index)">×</button>
          <button v-if="!path.is_default" type="button" @click="path.conditions.push(group().conditions[0])">＋ Condition</button>
        </div>
      </div>
      <label>Path Name<el-input v-model="path.path_name" /></label>
      <template v-if="!path.is_default">
        <template v-for="(condition, position) in path.conditions" :key="position">
          <el-select v-if="position" class="branch-logic-select" aria-label="Condition logic"
            :model-value="path.logic ?? condition.connector" @update:model-value="path.logic = $event">
            <el-option label="AND" value="AND" /><el-option label="OR" value="OR" />
          </el-select>
          <div class="branch-condition-card">
            <div class="branch-section-header">
              <span>Condition {{ position + 1 }}</span>
              <button type="button" class="branch-delete-condition" :aria-label="'Delete condition ' + (position + 1)"
                @click="path.conditions.splice(position, 1)"><el-icon><Delete /></el-icon></button>
            </div>
            <el-select :model-value="source(condition)" placeholder="Choose source" aria-label="Condition source"
              @update:model-value="setSource(condition, $event)">
              <el-option v-for="question in questions" :key="question.question_id"
                :label="question.question_name" :value="'question:' + question.question_id" />
              <el-option label="Embedded Data / Python Result" value="variable" />
              <el-option v-for="agentOption in agents" :key="agentOption.ai_config_id"
                :label="agentOption.agent_name + ' (Agent Output)'" :value="'agent:' + agentOption.ai_config_id" />
            </el-select>
            <el-input v-if="condition.source_type === 'variable'" v-model="condition.source_id" placeholder="Variable name" />
            <div class="branch-operands">
              <el-select v-model="condition.operator" aria-label="Operator">
                <el-option v-for="(label, value) in operators" :key="value" :label="label" :value="value" />
              </el-select>
              <el-select v-if="choices(condition).length" placeholder="Choose value" aria-label="Value"
                :model-value="choices(condition).find(choice => choice.choice_id === condition.value)?.value ?? condition.value"
                @update:model-value="condition.value = $event">
                <el-option v-for="choice in choices(condition)" :key="choice.choice_id"
                  :label="choice.label || String(choice.value)" :value="choice.value" />
              </el-select>
              <el-input v-else v-model="condition.value" placeholder="Value" aria-label="Value" />
            </div>
          </div>
        </template>
        <div class="branch-logic-preview">
          <span>Logic Preview</span>
          <p>{{ conditionText(path, survey) || "Add conditions to define this path." }}</p>
        </div>
      </template>
    </section>
    <div class="branch-path-actions">
      <button type="button" @click="addPath()">＋ Path</button>
      <button v-if="!paths.some(path => path.is_default)" type="button" @click="addPath(true)">＋ Otherwise</button>
    </div>
  </div>

  <div v-else class="settings-form">
    <template v-if="element.type === 'block'">
      <label>Choose Block<el-select v-model="element.block_id">
        <el-option v-for="block in survey.blocks.filter(item => !item.is_deleted)" :key="block.block_id"
          :label="block.block_name" :value="block.block_id" />
      </el-select></label>
      <el-button v-if="element.block_id" @click="emit('editBlock', element.block_id)">Edit Block</el-button>
    </template>
    <template v-else-if="element.type === 'block_randomizer'">
      <label>Randomization Mode<el-radio-group v-model="config.randomization_mode">
        <el-radio value="select">Random Selection</el-radio>
        <el-radio value="shuffle">Shuffle Order</el-radio>
      </el-radio-group></label>
      <label v-if="config.randomization_mode !== 'shuffle'">Number of Blocks to Present
        <el-input-number v-model="config.number_to_present" :min="1" :max="Math.max(1, Math.min(5, element.children.length))" />
      </label>
      <small>Add candidate Blocks under this node in the Flow Canvas.</small>
    </template>
    <template v-else-if="element.type === 'participant_randomizer'">
      <label>Randomization Mode<el-radio-group v-model="config.randomization_mode">
        <el-radio value="simple">Simple Random Assignment</el-radio>
        <el-radio value="balanced">Balanced Assignment</el-radio>
      </el-radio-group></label>
      <small>Participants are assigned to one path. Paths have equal allocation targets.</small>
      <div v-for="(path, index) in paths" :key="path.group_id" class="participant-path">
        <label>{{ `Path ${index + 1} Name` }}<el-input v-model="path.path_name" /></label>
        <el-button :disabled="!index" aria-label="Move path up" @click="movePath(index, -1)">↑</el-button>
        <el-button :disabled="index === paths.length - 1" aria-label="Move path down" @click="movePath(index, 1)">↓</el-button>
        <el-button :disabled="paths.length <= 2" @click="deletePath(index)">Delete Path</el-button>
      </div>
      <el-button @click="addPath()">＋ Path</el-button>
    </template>
    <template v-else-if="element.type === 'python_code'">
      <div class="python-configuration">
        <label>Element Name<el-input v-model="config.name" placeholder="Python Code" /></label>
        <label><span class="python-code-label">Python Code <small>Python</small></span>
          <textarea v-model="config.python_code" rows="10" maxlength="32768" spellcheck="false"
            placeholder='score = response["question_id"]&#10;result = {"score": score}' />
        </label>
        <small>Write your Python code here. Use {#question_id#} to reference an answer. Syntax is checked in Preview.</small>
      </div>
    </template>
    <template v-else-if="element.type === 'randomizer'">
      <label>Number of Elements to Present<el-input-number v-model="config.number_to_present"
        :min="1" :max="Math.max(1, element.children.length)" /></label>
      <el-checkbox v-model="config.evenly_present">Evenly Present Elements</el-checkbox>
    </template>
    <template v-else-if="element.type === 'embedded_data'">
      <label>Variable Name<el-input v-model="config.variable_name" /></label>
      <label>Value<el-input v-model="config.value" /></label>
    </template>
    <AISettings v-else-if="element.type === 'call_ai' && agent" :config="agent"
      :questions="questions" :default-model="defaultModel" :duplicate-name="duplicateName" />
    <label v-else-if="element.type === 'end_survey'">End Information<el-input v-model="config.end_information"
      type="textarea" :rows="5" placeholder="Optional ending information" /></label>
  </div>
</template>
