<script setup lang="ts">
import { references } from "./dependencies";
import QuestionGroups from "./components/QuestionGroups.vue";
import {
  ref,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from "vue";
import {
  useRoute,
  useRouter,
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
} from "vue-router";
import { ElMessageBox } from "element-plus";
import { api, workingPayload } from "./api";
import { validateLaunch } from "./launchValidation";
import type {
  Survey,
  Block,
  Question,
  FlowElement,
  ElementType,
  Revision,
  FlowTrash,
  AIConfig,
} from "./types";
import { id, clone, question, element, aiConfig } from "./defaults";
import NavIcon from "./components/NavIcon.vue";
import QuestionSettings from "./components/QuestionSettings.vue";
import QuestionDesign from "./components/QuestionDesign.vue";
import { elementLabels, elementName } from "./flowLabels";
import FlowTree from "./components/FlowTree.vue";
import FlowSettings from "./components/FlowSettings.vue";
import OptionsContent from "./components/OptionsContent.vue";
const route = useRoute(),
  router = useRouter(),
  module = computed(() => String(route.params.module)),
  sid = computed(() => String(route.params.id));
const survey = ref<Survey | null>(null),
  loading = ref(false),
  loadError = ref(""),
  saveError = ref(""),
  saving = ref(false),
  publishing = ref(false),
  baseline = ref(""),
  defaultModel = ref(""),
  toast = ref(""),
  selected = ref<string | null>(null),
  nodeDraft = ref<{ element: FlowElement; agent?: AIConfig; trash: FlowTrash[] } | null>(null),
  nodeSaving = ref(false),
  nodeError = ref(""),
  nodeDeleteFailed = ref(false),
  selectedKind = ref<"block" | "question" | "element" | null>(null),
  collapsed = ref<Set<string>>(new Set()),
  footerCollapsed = ref(false),
  search = ref(""),
  trashOpen = ref(false),
  historyOpen = ref(false),
  revisions = ref<Revision[]>([]),
  historyError = ref(""),
  flowZoom = ref(100),
  pythonSaved = ref(""),
  copiedConfiguration = ref(false),
  optionSection = ref("general");
let pythonTimer: ReturnType<typeof setTimeout> | undefined;
let autosaveTimer: ReturnType<typeof setTimeout> | undefined,
  toastTimer: ReturnType<typeof setTimeout> | undefined,
  pending: Promise<boolean> | null = null;
const signature = computed(() =>
  survey.value ? JSON.stringify(workingPayload(survey.value)) : "",
);
const dirty = computed(
  () => !!survey.value && signature.value !== baseline.value,
);
const activeBlocks = computed(
  () =>
    survey.value?.blocks
      .filter((b) => !b.is_deleted)
      .sort((a, b) => a.sort_order - b.sort_order) || [],
);
const allQuestions = computed(() =>
  activeBlocks.value.flatMap((b) => b.questions.filter((q) => !q.is_deleted)),
);
function flatten(elements: FlowElement[]): FlowElement[] {
  return elements.flatMap((e) => [
    e,
    ...flatten(e.children),
    ...e.config.condition_groups.flatMap((g) => flatten(g.children)),
  ]);
}
const flowNodes = computed(() => flatten(survey.value?.flow.elements || []));
const currentQuestion = computed(() =>
  allQuestions.value.find((q) => q.question_id === selected.value),
);
const currentBlock = computed(() =>
  activeBlocks.value.find((b) => b.block_id === selected.value),
);
const nodeType = computed(() => nodeDraft.value ? elementLabels[nodeDraft.value.element.type] : "");
const isPython = computed(() => nodeDraft.value?.element.type === "python_code");
const isBranch = computed(() => nodeDraft.value?.element.type === "branch");
const pythonDraft = computed(() => isPython.value ? JSON.stringify(nodeDraft.value?.element) : "");
const nodeName = computed(() => {
  const draft = nodeDraft.value;
  if (!draft) return "";
  const node = draft.element;
  return draft.agent?.agent_name || node.config.name || node.config.variable_name
    || survey.value?.blocks.find((block) => block.block_id === node.block_id)?.block_name
    || nodeType.value;
});
const optionsSearch = [
  { label: "Interface Language", id: "setting-interface-language" },
  { label: "Display Name", id: "setting-display-name" },
  { label: "Survey Description", id: "setting-description" },
  { label: "Question Numbers", id: "setting-question-numbers" },
  { label: "Back Button", id: "setting-back" },
  { label: "Allow Respondents to Finish Later", id: "setting-finish-later" },
  { label: "Incomplete Survey Responses", id: "setting-incomplete" },
  { label: "Survey Availability", id: "setting-availability" },
  { label: "Allowed Referrer", id: "setting-referrer" },
  { label: "Prevent Multiple Submissions", id: "setting-duplicates" },
  { label: "Prevent Search Indexing", id: "setting-indexing" },
  { label: "Anonymous Responses", id: "setting-anonymous" },
  { label: "AI Configuration", id: "option-ai" },
];
const results = computed(() => {
  const key = search.value.trim().toLowerCase();
  if (!key) return [];
  if (module.value === "builder")
    return allQuestions.value
      .filter((q) =>
        (q.question_name + " " + q.question_text).toLowerCase().includes(key),
      )
      .map((q) => ({
        id: q.question_id,
        label: `${activeBlocks.value.find((b) => b.questions.includes(q))?.block_name} - ${q.question_name}`,
      }));
  if (module.value === "flow")
    return flowNodes.value
      .filter((e) => flowText(e).toLowerCase().includes(key))
      .map((e) => ({ id: e.element_id, label: flowText(e) }));
  return optionsSearch.filter((o) => o.label.toLowerCase().includes(key));
});
const removedQuestions = computed(
  () =>
    survey.value?.blocks.flatMap((b) =>
      b.questions
        .filter((q) => q.is_deleted)
        .map((q) => ({ block: b, question: q })),
    ) || [],
);
const removedBlocks = computed(
  () =>
    survey.value?.blocks.filter((b) => b.is_deleted) ||
    [],
);
function flowText(e: FlowElement) {
  return [
    e.config.name,
    e.config.variable_name,
    elementLabels[e.type],
    ...e.config.condition_groups.map(path => path.path_name),
    survey.value?.blocks.find((b) => b.block_id === e.block_id)?.block_name,
    survey.value?.ai_configs.find((a) => a.ai_config_id === e.ai_config_id)
      ?.agent_name,
  ]
    .filter(Boolean)
    .join(" ");
}
function showToast(message: string) {
  toast.value = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.value = ""), 60000);
}
async function load() {
  loading.value = true;
  loadError.value = "";
  selected.value = null;
  selectedKind.value = null;
  nodeDraft.value = null;
  try {
    survey.value = await api.working(sid.value);
    baseline.value = signature.value;
    saveError.value = "";
  } catch {
    survey.value = null;
    loadError.value = `Failed to load survey${module.value === "flow" ? " flow" : module.value === "options" ? " settings" : ""}. Please Retry.`;
  } finally {
    loading.value = false;
  }
}
onMounted(async () => {
  try {
    defaultModel.value = (await api.capabilities()).default_model;
  } catch {}
  await load();
  if (module.value === "flow" && typeof route.query.element === "string")
    openNodeConfiguration(route.query.element);
});
watch(sid, load);
watch(module, () => {
  clearTimeout(pythonTimer);
  nodeDraft.value = null;
  selected.value = null;
  selectedKind.value = null;
  search.value = "";
  clearTimeout(autosaveTimer);
  if (dirty.value) schedule();
});
function schedule() {
  clearTimeout(autosaveTimer);
  if (dirty.value && !nodeDraft.value)
    autosaveTimer = setTimeout(
      () => void save("auto"),
      module.value === "options" ? 10000 : 600000,
    );
}
watch(signature, () => schedule());
async function save(type: "auto" | "apply" = "apply", staged?: Survey): Promise<boolean> {
  if (pending) {
    await pending;
    if (dirty.value) return save(type);
    return !saveError.value;
  }
  if (!survey.value || survey.value.role === "viewer") return false;
  const local = staged ?? clone(survey.value),
    before = signature.value;
  saving.value = true;
  saveError.value = "";
  clearTimeout(autosaveTimer);
  pending = (async () => {
    try {
      const result = await api.save(local, type);
      if (signature.value === before) {
        survey.value = result;
        baseline.value = JSON.stringify(workingPayload(result));
      } else if (survey.value) {
        survey.value.working_version = result.working_version;
        survey.value.updated_at = result.updated_at;
        for (const a of survey.value.ai_configs) {
          const saved = result.ai_configs.find(
            (x) => x.ai_config_id === a.ai_config_id,
          );
          if (saved) a.config_version = saved.config_version;
        }
        baseline.value = JSON.stringify(workingPayload(result));
      }
      return true;
    } catch (e) {
      const message = "Failed to save changes. Please Retry. " + (e as Error).message;
      if (staged) nodeError.value = message;
      else saveError.value = message;
      return false;
    } finally {
      saving.value = false;
      pending = null;
    }
  })();
  const result = await pending;
  if (dirty.value && result) schedule();
  return result;
}
async function ensureSaved() {
  if (pending && !(await pending)) return false;
  while (dirty.value) {
    if (!(await save())) return false;
  }
  return true;
}
async function openPreview() {
  const win = window.open("about:blank", "_blank");
  if (!(await ensureSaved())) {
    win?.close();
    return;
  }
  const url = router.resolve({
    path: `/survey/${sid.value}/preview`,
    query: { version: survey.value?.working_version, from: module.value },
  }).href;
  if (win) win.location.href = url;
  else window.open(url, "_blank");
}
async function publishSurvey() {
  if (!survey.value || publishing.value) return;
  publishing.value = true;
  try {
    if (!(await ensureSaved()) || !survey.value) return;
    const local = survey.value;
    const before = signature.value;
    const prepared = await api.prepareExecution(local.survey_id, local.working_version);
    validateLaunch(prepared);
    const result = await api.publish(prepared);
    if (survey.value?.survey_id !== local.survey_id) return;
    if (signature.value === before) {
      survey.value = result;
      baseline.value = signature.value;
    } else {
      survey.value.status = result.status;
      survey.value.working_version = result.working_version;
      survey.value.updated_at = result.updated_at;
      baseline.value = JSON.stringify(workingPayload(result));
    }
    showToast("Published version saved.");
  } catch (error) {
    showToast((error as Error).message);
  } finally {
    publishing.value = false;
  }
}
onBeforeRouteLeave(async () => !dirty.value || (await ensureSaved()));
onBeforeRouteUpdate(
  async (to, from) =>
    to.fullPath === from.fullPath || !dirty.value || (await ensureSaved()),
);
function unload(e: BeforeUnloadEvent) {
  if (dirty.value) {
    e.preventDefault();
    e.returnValue = "";
  }
}
window.addEventListener("beforeunload", unload);
onBeforeUnmount(() => {
  clearTimeout(autosaveTimer);
  clearTimeout(toastTimer);
  clearTimeout(pythonTimer);
  window.removeEventListener("beforeunload", unload);
});
function select(kind: "block" | "question" | "element", identifier: string) {
  selected.value = identifier;
  selectedKind.value = kind;
}
function toggleBlock(identifier: string) {
  const set = new Set(collapsed.value);
  set.has(identifier) ? set.delete(identifier) : set.add(identifier);
  collapsed.value = set;
}
function addBlock(after: Block) {
  if (!survey.value) return;
  const target = after.sort_order + 1;
  for (const b of survey.value.blocks)
    if (b.sort_order >= target) b.sort_order++;
  const b: Block = {
    block_id: id(),
    block_name: `Block ${Math.max(survey.value.blocks.length, 0) + 1}`,
    sort_order: target,
    is_deleted: false,
    deleted_at: null,
    questions: [],
  };
  survey.value.blocks.push(b);
  select("block", b.block_id);
}
function addQuestion(b: Block) {
  const nums =
    survey.value?.blocks
      .flatMap((b) => b.questions)
      .map((q) => Number(q.question_name.match(/^Q(\d+)$/)?.[1] || 0)) || [];
  const q = question(
    "multiple_choice",
    `Q${Math.max(0, ...nums) + 1}`,
    Math.max(0, ...b.questions.map((q) => q.sort_order)) + 1,
  );
  b.questions.push(q);
  select("question", q.question_id);
}
function referenced(identifier: string) {
  const s = survey.value;
  if (!s) return false;
  return (
    JSON.stringify(s.flow).includes('"' + identifier + '"') ||
    s.ai_configs.some((a) => a.input_source_config.question_id === identifier)
  );
}
async function removeQuestion() {
  const q = currentQuestion.value;
  if (!q) return;
  const refs = references(survey.value!, q);
  if (refs.length || referenced(q.question_id)) {
    showToast("Question referenced by Flow: " + (refs.join(", ") || q.question_name) + ". Remove references first.");
    return;
  }
  const before = clone(survey.value!);
  for (const b of survey.value!.blocks) for (const g of b.question_groups || []) { g.question_ids = g.question_ids.filter(id => id !== q.question_id); g.display_count = Math.max(1, Math.min(g.display_count, g.question_ids.length)); if (!g.question_ids.length) g.display_mode = "all"; }
  q.is_deleted = true;
  q.deleted_at = new Date().toISOString();
  selected.value = null;
  if (!(await save())) {
    survey.value = before;
    showToast("Failed to delete question. Please retry.");
  }
}
async function removeBlock() {
  const b = currentBlock.value;
  if (!b) return;
  if (
    referenced(b.block_id) ||
    b.questions.some((q) => referenced(q.question_id))
  ) {
    const refs = [...flowNodes.value, ...survey.value!.flow.trash.flatMap(t => flatten([t.element]))].filter(e => e.block_id === b.block_id).map(e => e.config.name || e.element_id);
    b.questions.forEach(q => refs.push(...references(survey.value!, q)));
    showToast("Block / Questions referenced by Flow: " + [...new Set(refs)].join(", ") + ". Remove references first.");
    return;
  }
  const before = clone(survey.value!);
  b.is_deleted = true;
  b.deleted_at = new Date().toISOString();
  for (const q of b.questions)
    if (!q.is_deleted) {
      q.is_deleted = true;
      q.deleted_at = b.deleted_at;
    }
  selected.value = null;
  if (!(await save())) {
    survey.value = before;
    showToast("Failed to delete block. Please retry.");
  }
}
async function restoreQuestion(b: Block, q: Question) {
  const before = clone(survey.value!);
  b.is_deleted = false;
  b.deleted_at = null;
  q.is_deleted = false;
  q.deleted_at = null;
  const active = new Set(b.questions.filter(q => !q.is_deleted).map(q => q.question_id));
  for (const g of b.question_groups || []) { g.question_ids = g.question_ids.filter(id => active.has(id)); g.display_count = Math.max(1, Math.min(g.display_count, g.question_ids.length)); if (!g.question_ids.length) g.display_mode = "all"; }
  if (!(await save())) {
    survey.value = before;
    showToast("Failed to restore question. Please retry.");
  }
}
async function restoreEmptyBlock(b: Block) {
  b.is_deleted = false;
  b.deleted_at = null;
  for (const q of b.questions) { q.is_deleted = false; q.deleted_at = null; }
  if (!(await save())) showToast("Failed to restore block. Please retry.");
}

function location(
  identifier: string,
  elements = survey.value?.flow.elements || [],
  parent: string | null = null,
  gid: string | null = null,
): {
  array: FlowElement[];
  index: number;
  parent: string | null;
  group: string | null;
} | null {
  for (let i = 0; i < elements.length; i++) {
    const e = elements[i];
    if (e.element_id === identifier)
      return { array: elements, index: i, parent, group: gid };
    const found = location(identifier, e.children, e.element_id, null);
    if (found) return found;
    for (const g of e.config.condition_groups) {
      const found = location(identifier, g.children, e.element_id, g.group_id);
      if (found) return found;
    }
  }
  return null;
}
function targetArray(parent: string | null, gid: string | null) {
  if (!survey.value) return null;
  if (!parent) return survey.value.flow.elements;
  const e = flowNodes.value.find((e) => e.element_id === parent);
  if (!e) return null;
  if (gid)
    return (
      e.config.condition_groups.find((g) => g.group_id === gid)?.children ||
      null
    );
  return ["randomizer", "block_randomizer"].includes(e.type) ? e.children : null;
}
function normalize(elements: FlowElement[]) {
  elements.forEach((e, i) => {
    e.sort_order = i + 1;
    normalize(e.children);
    e.config.condition_groups.forEach((g) => normalize(g.children));
  });
}
function insert(
  type: ElementType,
  parent: string | null,
  gid: string | null,
  index: number,
) {
  const list = targetArray(parent, gid);
  if (!list || !survey.value) return;
  const p = flowNodes.value.find((e) => e.element_id === parent);
  if (p?.type === "block_randomizer" && type !== "block") return;
  if (p?.type === "randomizer" && !["block", "branch"].includes(type)) {
    showToast("Randomizer accepts Block or Branch only.");
    return;
  }
  const e = element(type);
  if (type === "call_ai") {
    const names = new Set(survey.value.ai_configs.map((a) => a.agent_name));
    let n = 1;
    while (names.has(`Conversation_${n}`)) n++;
    const a = aiConfig(`Conversation_${n}`, defaultModel.value);
    survey.value.ai_configs.push(a);
    e.ai_config_id = a.ai_config_id;
  }
  list.splice(index, 0, e);
  normalize(survey.value.flow.elements);
  openNodeConfiguration(e.element_id);
}
function newAgentName(base: string, survey: Survey) {
  const names = new Set(survey.ai_configs.map(agent => agent.agent_name));
  let index = 1;
  while (names.has(`${base}_${index}`)) index++;
  return `${base}_${index}`;
}

async function nodeAction(action: string, identifier: string) {
  const working = survey.value;
  const loc = location(identifier);
  if (!working || working.role === "viewer" || !loc) return;
  const node = loc.array[loc.index];
  if (action === "delete") {
    openNodeConfiguration(identifier);
    await confirmNodeRemoval();
    return;
  }
  if (action === "rename") {
    if (["branch", "python_code", "call_ai"].includes(node.type)) {
      openNodeConfiguration(identifier);
      return;
    }
    try {
      const result = await ElMessageBox.prompt("Element Name", "Rename", {
        inputValue: elementName(node, working), inputValidator: value => !!value.trim() || "Enter a name.",
      });
      node.config.name = result.value.trim();
    } catch { return; }
  } else if (action === "duplicate") {
    const copy = clone(node);
    const agents = new Map<string, AIConfig>();
    for (const item of flatten([copy])) {
      item.element_id = id();
      for (const path of item.config.condition_groups) path.group_id = id();
      if (item.ai_config_id) {
        const original = working.ai_configs.find(agent => agent.ai_config_id === item.ai_config_id);
        if (original) {
          const agent = clone(original);
          agent.ai_config_id = id();
          agent.config_version = 1;
          agent.agent_name = newAgentName(original.agent_name, working);
          working.ai_configs.push(agent);
          agents.set(original.ai_config_id, agent);
          item.ai_config_id = agent.ai_config_id;
        }
      }
    }
    for (const item of flatten([copy]))
      for (const path of item.config.condition_groups)
        for (const condition of path.conditions)
          if (condition.source_type === "agent")
            condition.source_id = agents.get(condition.source_id)?.ai_config_id ?? condition.source_id;
    for (const agent of agents.values())
      for (const [original, mapped] of agents) {
        agent.context_template = agent.context_template.replaceAll("{#" + original + "#}", "{#" + mapped.ai_config_id + "#}");
        agent.user_message_template = agent.user_message_template.replaceAll("{#" + original + "#}", "{#" + mapped.ai_config_id + "#}");
      }
    loc.array.splice(loc.index + 1, 0, copy);
  } else {
    const target = loc.index + (action === "up" ? -1 : 1);
    if (target < 0 || target >= loc.array.length) return;
    [loc.array[loc.index], loc.array[target]] = [loc.array[target], loc.array[loc.index]];
  }
  normalize(working.flow.elements);
}

function openNodeConfiguration(identifier: string) {
  const node = flowNodes.value.find((item) => item.element_id === identifier);
  if (!node || !survey.value || nodeDraft.value) return;
  const agent = survey.value.ai_configs.find((item) => item.ai_config_id === node.ai_config_id);
  clearTimeout(autosaveTimer);
  nodeError.value = "";
  nodeDeleteFailed.value = false;
  copiedConfiguration.value = false;
  pythonSaved.value = JSON.stringify(node);
  nodeDraft.value = { element: clone(node), agent: agent && clone(agent), trash: [] };
  select("element", identifier);
}

function closeNodeConfiguration() {
  if (nodeSaving.value) return;
  clearTimeout(pythonTimer);
  nodeDraft.value = null;
  nodeError.value = "";
  selected.value = null;
  selectedKind.value = null;
  schedule();
}

async function saveNodeConfiguration(remove = false, close = true) {
  const draft = nodeDraft.value;
  if (!draft || !survey.value || survey.value.role === "viewer" || nodeSaving.value) return;
  if (!remove && draft.agent && survey.value.ai_configs.some(agent =>
    agent.ai_config_id !== draft.agent?.ai_config_id && agent.agent_name === draft.agent?.agent_name)) {
    nodeError.value = "An agent with this name already exists.";
    return;
  }
  clearTimeout(pythonTimer);
  const pythonSignature = pythonDraft.value;
  nodeSaving.value = true;
  nodeError.value = "";
  nodeDeleteFailed.value = remove;
  let saved = false;
  try {
    if (pending) await pending;
    const working = clone(survey.value);
    const loc = location(draft.element.element_id, working.flow.elements);
    if (!loc) {
      nodeError.value = "This element is no longer available. Close the configuration and reload the Flow.";
      return;
    }
    if (remove) {
      const [removed] = loc.array.splice(loc.index, 1);
      working.flow.trash.push({
        element: removed, parent_id: loc.parent, group_id: loc.group,
        position: loc.index, deleted_at: new Date().toISOString(),
      });
    } else {
      loc.array[loc.index] = clone(draft.element);
      working.flow.trash.push(...clone(draft.trash));
      if (draft.agent) {
        const index = working.ai_configs.findIndex((agent) => agent.ai_config_id === draft.agent?.ai_config_id);
        if (index !== -1) {
          const oldName = working.ai_configs[index].agent_name;
          const oldVariable = oldName.trim().toLowerCase().replace(/\s+/g, "_");
          working.ai_configs[index] = clone(draft.agent);
          if (oldName !== draft.agent.agent_name) {
            for (const agent of working.ai_configs) {
              for (const token of [oldName, oldVariable]) {
                const ref = "{#" + draft.agent.ai_config_id + "#}";
                agent.context_template = agent.context_template.replaceAll("{#" + token + "#}", ref);
                agent.user_message_template = agent.user_message_template.replaceAll("{#" + token + "#}", ref);
              }
              const previous = "{#ai_" + oldName + "#}";
              const replacement = "{#ai_" + draft.agent.agent_name + "#}";
              agent.context_template = agent.context_template.replaceAll(previous, replacement);
              agent.user_message_template = agent.user_message_template.replaceAll(previous, replacement);
            }
            for (const node of flatten(working.flow.elements))
              for (const path of node.config.condition_groups)
                for (const condition of path.conditions)
                  if (condition.source_type === "variable" && condition.source_id === "ai_" + oldName)
                    condition.source_id = "ai_" + draft.agent.agent_name;
          }
        }
      }
    }
    normalize(working.flow.elements);
    saved = await save(isPython.value && !remove ? "auto" : "apply", working);
    if (saved && isPython.value) pythonSaved.value = pythonSignature;
  } finally {
    nodeSaving.value = false;
    if (saved && close && (!isPython.value || remove || pythonDraft.value === pythonSaved.value)) closeNodeConfiguration();
    else if (saved && isPython.value && pythonDraft.value !== pythonSaved.value) schedulePython();
  }
}

function schedulePython() {
  clearTimeout(pythonTimer);
  if (isPython.value && !nodeSaving.value && pythonDraft.value !== pythonSaved.value)
    pythonTimer = setTimeout(() => void saveNodeConfiguration(false, false), 900);
}
watch(pythonDraft, schedulePython);
function backFromNode() {
  if (isPython.value && pythonDraft.value !== pythonSaved.value) void saveNodeConfiguration();
  else closeNodeConfiguration();
}
async function copyNodeConfiguration() {
  if (!nodeDraft.value) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(nodeDraft.value.element.config, null, 2));
    copiedConfiguration.value = true;
  } catch {
    nodeError.value = "Could not copy the configuration.";
  }
}
async function editBlockFromFlow(identifier: string) {
  await saveNodeConfiguration();
  if (nodeDraft.value) return;
  await router.push(`/survey/${sid.value}/builder`);
  select("block", identifier);
  await nextTick();
  document.getElementById("block-" + identifier)?.scrollIntoView({ block: "center" });
}

async function confirmNodeRemoval() {
  try {
    await ElMessageBox.confirm(
      "Move this element and its children to Flow Trash?",
      "Delete Element",
      { type: "warning", confirmButtonText: "Delete", cancelButtonText: "Cancel" },
    );
  } catch {
    return;
  }
  await saveNodeConfiguration(true);
}

async function restoreElement(t: FlowTrash) {
  if (!survey.value) return;
  const before = clone(survey.value),
    target = targetArray(t.parent_id, t.group_id) || survey.value.flow.elements;
  target.splice(Math.min(t.position, target.length), 0, t.element);
  survey.value.flow.trash = survey.value.flow.trash.filter((x) => x !== t);
  normalize(survey.value.flow.elements);
  if (!(await save())) {
    survey.value = before;
    showToast("Failed to restore element. Please retry.");
  }
}

async function openHistory() {
  if (!(await ensureSaved())) return;
  historyOpen.value = true;
  historyError.value = "";
  try {
    revisions.value = await api.revisions(
      sid.value,
      module.value === "flow" ? "flow" : "survey",
    );
  } catch {
    historyError.value = "Failed to load version history. Retry.";
  }
}
async function restoreRevision(r: Revision) {
  if (!survey.value || !(await ensureSaved())) return;
  try {
    survey.value = await api.restore(
      survey.value,
      r.revision_id,
      module.value === "flow" ? "flow" : "survey",
    );
    baseline.value = signature.value;
    selected.value = null;
    historyOpen.value = false;
  } catch (e) {
    showToast("Failed to restore version. " + (e as Error).message);
  }
}
async function scrollResult(identifier: string, openNode = true) {
  if (module.value === "builder") {
    const b = activeBlocks.value.find((b) =>
      b.questions.some((q) => q.question_id === identifier),
    );
    if (b) collapsed.value.delete(b.block_id);
    select("question", identifier);
  } else if (module.value === "flow" && openNode) openNodeConfiguration(identifier);
  await nextTick();
  document
    .getElementById(
      module.value === "options"
        ? identifier
        : module.value === "flow"
          ? `flow-${identifier}`
          : `question-${identifier}`,
    )
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}
watch(search, () => {
  if (results.value.length) void scrollResult(results.value[0].id, false);
});
function section(name: string) {
  optionSection.value = name;
  document
    .getElementById("option-" + name)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}
const savedText = computed(() =>
  saving.value
    ? "Saving…"
    : saveError.value ||
      (!navigator.onLine && dirty.value
        ? "Changes are not saved."
        : dirty.value
          ? "Changes are not saved."
          : survey.value
            ? `saved at ${new Date(survey.value.updated_at).toLocaleString()}`
            : ""),
);
</script>
<template>
  <div class="editor-shell">
    <header class="global-nav">
      <button aria-label="Projects" @click="router.push('/')">☰</button
      ><span class="help">?</span>
    </header>
    <nav class="primary-nav">
      <button class="active" @click="router.push(`/survey/${sid}/builder`)">
        Survey</button
      ><button
        v-for="name in ['distribution', 'analysis', 'report']"
        :key="name"
        :class="{ active: module === name }"
        @click="router.push(`/survey/${sid}/${name}`)"
      >
        {{ name[0].toUpperCase() + name.slice(1) }}
      </button>
    </nav>
    <div v-if="toast" class="operation-toast">
      ⚠ {{ toast }}<button @click="toast = ''">×</button>
    </div>
    <div class="editor-body">
      <nav class="icon-nav">
        <button
          v-for="(name, i) in ['builder', 'flow', 'options']"
          :key="name"
          :title="name"
          :aria-label="name"
          :class="{ active: module === name }"
          @click="router.push(`/survey/${sid}/${name}`)"
        >
          <NavIcon :name="name" />
        </button>
      </nav>
      <aside
        v-if="module === 'builder' || module === 'options'"
        class="settings-panel"
      >
        <h3>{{ module === "builder" ? "Edit Question" : "Option" }}</h3>
        <template v-if="survey"
          ><div v-if="survey.role === 'viewer'" class="muted">View only</div>
          <fieldset :disabled="survey.role === 'viewer'">
            <QuestionSettings
              v-if="
                module === 'builder' &&
                selectedKind === 'question' &&
                currentQuestion
              "
              :question="currentQuestion"
              :survey="survey"
              @delete="removeQuestion"
            />
            <div
              v-else-if="
                module === 'builder' && selectedKind === 'block' && currentBlock
              "
              class="settings-form"
            >
              <label
                >Block Name<el-input
                  v-model="currentBlock.block_name"
                  maxlength="255" /></label
              ><QuestionGroups :block="currentBlock" />
              <el-button class="danger-soft" @click="removeBlock"
                >♜ Delete Block</el-button
              >
            </div>
            <div v-else-if="module === 'options'" class="option-links">
              <button
                v-for="name in ['general', 'responses', 'security', 'ai']"
                :key="name"
                :class="{ active: optionSection === name }"
                @click="section(name)"
              >
                {{ name === "ai" ? "AI" : name[0].toUpperCase() + name.slice(1)
                }}<small>{{
                  {
                    general: "Language, Display Name, Description",
                    responses: "Back Button, Resume, Availability",
                    security: "Referrer, Multiple Submissions",
                    ai: "AI Configuration",
                  }[name]
                }}</small>
              </button>
            </div>
            <p v-else class="select-hint">Please Select One Block/Question</p>
          </fieldset></template
        >
        <p v-else class="select-hint">Please Select One Block/Question</p>
      </aside>
      <div class="work-area">
        <div class="survey-header">
          <div>
            <div class="survey-name">
              <input
                v-if="survey && module === 'builder'"
                v-model="survey.survey_name"
                maxlength="100"
                aria-label="Survey Name"
                :disabled="survey.role === 'viewer'"
              /><strong v-else>{{ survey?.survey_name || "Survey" }}</strong
              ><span v-if="survey && module === 'builder'">✎</span
              ><span
                v-if="survey && module !== 'options'"
                class="status-tag"
                :class="survey.status"
                >{{
                  survey.status[0].toUpperCase() + survey.status.slice(1)
                }}</span
              >
            </div>
            <button
              class="save-status"
              :class="{ error: saveError }"
              @click="saveError && save()"
            >
              {{ savedText }}
            </button>
          </div>
          <div
            class="header-tools"
            v-if="['builder', 'flow', 'options'].includes(module)"
          >
            <div class="search-container">
              <el-input
                v-model="search"
                placeholder="⌕"
                aria-label="Search current module"
                clearable
              />
              <div v-if="search && results.length > 1" class="search-results">
                <button
                  v-for="r in results"
                  :key="r.id"
                  @click="scrollResult(r.id)"
                >
                  {{ r.label }}
                </button>
              </div>
            </div>
            <el-button
              v-if="module !== 'options'"
              class="trash-button"
              @click="trashOpen = true"
              >Trash</el-button
            ><el-button
              v-if="module !== 'options'"
              plain
              type="primary"
              @click="openHistory"
              >History</el-button
            >
          </div>
        </div>
        <main class="canvas" v-loading="loading">
          <div v-if="loadError" class="load-error">
            {{ loadError
            }}<button class="text-button" @click="load">Retry</button>
          </div>
          <template v-else-if="survey"
            ><fieldset :disabled="survey.role === 'viewer'">
              <div v-if="module === 'builder'" class="builder-content">
                <template v-for="b in activeBlocks" :key="b.block_id"
                  ><section
                    class="block"
                    :class="{
                      selected:
                        selectedKind === 'block' && selected === b.block_id,
                    }"
                  >
                    <header
                      :id="'block-' + b.block_id"
                      class="block-header"
                      @click="select('block', b.block_id)"
                    >
                      <button
                        :aria-label="`Toggle ${b.block_name}`"
                        @click.stop="toggleBlock(b.block_id)"
                      >
                        {{ collapsed.has(b.block_id) ? "›" : "⌄" }}</button
                      >{{ b.block_name }}
                    </header>
                    <div v-if="!collapsed.has(b.block_id)">
                      <div
                        v-for="q in b.questions
                          .filter((q) => !q.is_deleted)
                          .sort((a, b) => a.sort_order - b.sort_order)"
                        :key="q.question_id"
                        :id="`question-${q.question_id}`"
                        class="question"
                        :class="{
                          selected: selected === q.question_id,
                          'search-match': results.some(
                            (r) => r.id === q.question_id,
                          ),
                        }"
                        @click="select('question', q.question_id)"
                      >
                        <small class="question-name">{{
                          q.question_name
                        }}</small
                        ><QuestionDesign :question="q" />
                      </div>
                      <div class="add-question">
                        <el-button type="primary" @click="addQuestion(b)"
                          >+ Add new question</el-button
                        >
                      </div>
                    </div>
                  </section>
                  <button class="add-block" @click="addBlock(b)">
                    Add Block
                  </button></template
                ><button
                  v-if="!activeBlocks.length"
                  class="add-block"
                  @click="
                    survey.blocks.push({
                      block_id: id(),
                      block_name: 'Block 1',
                      sort_order:
                        Math.max(0, ...survey.blocks.map((b) => b.sort_order)) +
                        1,
                      is_deleted: false,
                      deleted_at: null,
                      questions: [],
                    })
                  "
                >
                  Add Block
                </button>
              </div>
              <div v-else-if="module === 'flow'" class="flow-diagram-canvas">
              <div class="flow-zoom" role="group" aria-label="Flow zoom">
                <el-button circle aria-label="Zoom out" :disabled="flowZoom <= 60" @click="flowZoom -= 10">−</el-button>
                <button type="button" aria-label="Reset zoom" @click="flowZoom = 100">{{ flowZoom }}%</button>
                <el-button circle aria-label="Zoom in" :disabled="flowZoom >= 150" @click="flowZoom += 10">＋</el-button>
              </div>
              <FlowTree class="flow-diagram-root" :style="{ zoom: flowZoom / 100 }"
                :elements="survey.flow.elements"
                :survey="survey"
                :selected="selected"
                                :matches="results.map((r) => r.id)"
                @select="openNodeConfiguration"
                @insert="insert"
                @action="nodeAction"
              />
              </div>
              <OptionsContent
                v-else-if="module === 'options'"
                :survey="survey"
                :default-model="defaultModel"
              />
              <p v-else class="deferred-message">
                {{ module[0].toUpperCase() + module.slice(1) }} will be
                available after its PRD is finalized.
              </p>
            </fieldset></template
          >
        </main>
        <footer
          v-if="['builder', 'flow', 'options'].includes(module)"
          class="editor-footer"
          :class="{ collapsed: footerCollapsed }"
        >
          <button
            class="footer-toggle"
            :aria-label="
              footerCollapsed ? 'Expand actions' : 'Collapse actions'
            "
            @click="footerCollapsed = !footerCollapsed"
          >
            {{ footerCollapsed ? "⌃" : "⌄" }}
          </button>
          <div v-show="!footerCollapsed">
            <el-button
              type="primary"
              :loading="saving"
              :disabled="!survey || survey.role === 'viewer'"
              @click="save()"
              >Apply</el-button
            ><el-button
              v-if="module !== 'options'"
              plain
              type="primary"
              :disabled="!survey || survey.role === 'viewer'"
              @click="openPreview"
              >Preview</el-button
            ><el-button
              type="primary"
              :loading="publishing"
              :disabled="!survey || survey.role === 'viewer'"
              @click="publishSurvey"
              >Publish</el-button
            >
          </div>
        </footer>
      </div>
    </div>
    <el-dialog
      :model-value="!!nodeDraft"
      class="flow-configuration"
      :class="{ 'flow-prototype-modal': isBranch || isPython || nodeDraft?.agent }"
      width="min(1024px, calc(100vw - 32px))"
      top="6vh"
      append-to-body
      :title="nodeType + ' Configuration'"
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="!nodeSaving && !isPython"
      @update:model-value="!$event && closeNodeConfiguration()"
    >
      <template #header="{ titleId }">
        <div class="flow-configuration-header">
          <el-button text circle aria-label="Close node configuration" :disabled="nodeSaving"
            @click="backFromNode">×</el-button>
          <div>
            <h2 :id="titleId"><span v-if="isPython" aria-hidden="true">‹/› </span>{{ nodeType }} Configuration</h2>
            <p v-if="!isBranch && !isPython && nodeName !== nodeType">{{ nodeName }}</p>
          </div>
        </div>
      </template>
      <p v-if="isPython" class="python-save-status" role="status">
        {{ nodeSaving ? "Saving…" : nodeError ? "Save failed" : pythonDraft !== pythonSaved ? "Unsaved changes" : "Saved" }}
      </p>
      <fieldset v-if="survey && nodeDraft" :disabled="(nodeSaving && !isPython) || survey.role === 'viewer'">
        <FlowSettings
          :element="nodeDraft.element"
          :survey="survey"
          :agent="nodeDraft.agent"
          :trash="nodeDraft.trash"
          :default-model="defaultModel"
          @edit-block="editBlockFromFlow"
        />
      </fieldset>
      <template #footer>
        <div v-if="nodeError" class="flow-configuration-error" role="alert">{{ nodeError }}</div>
        <div v-if="survey" class="flow-configuration-actions">
          <el-button v-if="survey.role !== 'viewer'" type="danger" plain
            :disabled="nodeSaving" @click="confirmNodeRemoval">{{ nodeError && nodeDeleteFailed ? "Retry Delete" : "Delete Element" }}</el-button>
          <div>
            <el-button v-if="!isPython" :disabled="nodeSaving" @click="backFromNode">
              {{ survey.role === "viewer" ? "Back" : "Cancel" }}
            </el-button>
            <el-button v-if="isBranch && survey.role !== 'viewer'" round :disabled="nodeSaving"
              @click="copyNodeConfiguration">{{ copiedConfiguration ? "Copied" : "Copy JSON" }}</el-button>
            <el-button v-if="isPython" round :loading="nodeSaving" @click="backFromNode">
              {{ nodeError && !nodeDeleteFailed ? "Retry Save" : "← Back" }}
            </el-button>
            <el-button v-else-if="survey.role !== 'viewer'" type="primary" :round="isBranch"
              :class="{ 'branch-use-configuration': isBranch }" :loading="nodeSaving"
              @click="saveNodeConfiguration()">{{ nodeError && !nodeDeleteFailed ? "Retry Apply" : isBranch ? "Use Configuration" : "Apply" }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
    <el-dialog
      v-model="trashOpen"
      :title="`♜ Trash | ${module === 'flow' ? (survey?.flow.trash.length || 0) + ' Element' : removedQuestions.length + ' Question'}`"
      width="min(850px,92vw)"
      class="list-dialog"
      ><template v-if="survey"
        ><template v-if="module === 'flow'"
          ><div
            v-for="t in survey.flow.trash"
            :key="t.element.element_id"
            class="trash-row"
          >
            <div>
              <strong>{{ flowText(t.element) }}</strong
              ><small
                >{{ flatten([t.element]).length }} Element(s), including
                children</small
              >
            </div>
            <el-button
              plain
              type="primary"
              :disabled="survey.role === 'viewer'"
              @click="restoreElement(t)"
              >Restore</el-button
            >
          </div></template
        ><template v-else
          ><div
            v-for="item in removedQuestions"
            :key="item.question.question_id"
            class="trash-row"
          >
            <div>
              <small>{{ item.block.block_name }}</small
              ><strong>{{ item.question.question_name }}</strong
              ><small>{{ item.question.question_text.slice(0, 100) }}</small>
            </div>
            <el-button
              plain
              type="primary"
              :disabled="survey.role === 'viewer'"
              @click="restoreQuestion(item.block, item.question)"
              >Restore</el-button
            >
          </div>
          <div v-for="b in removedBlocks" :key="b.block_id" class="trash-row">
            <strong>{{ b.block_name }}</strong
            ><el-button @click="restoreEmptyBlock(b)">Restore</el-button
            >
          </div></template
        >
        <p
          v-if="
            module === 'flow'
              ? !survey.flow.trash.length
              : !removedQuestions.length && !removedBlocks.length
          "
          class="muted"
        >
          Trash is empty.
        </p></template
      ></el-dialog
    >
    <el-dialog
      v-model="historyOpen"
      title="⟳ Version History"
      width="min(850px,92vw)"
      class="list-dialog"
      ><p v-if="historyError">{{ historyError }}</p>
      <div v-for="r in revisions" :key="r.revision_id" class="history-row">
        <div>
          <small>modified by {{ r.created_by }}</small
          ><strong
            >saved at {{ new Date(r.created_at).toLocaleString() }}</strong
          ><small
            >{{
              module === "flow"
                ? r.element_count + " elements"
                : r.block_count + " block | " + r.question_count + " questions"
            }}
            <span :class="['revision-status', r.save_type]">{{
              r.save_type === "auto"
                ? "Autosave"
                : r.save_type === "apply"
                  ? "Applied"
                  : r.save_type === "published" ? "Published" : "Restored"
            }}</span>
            <small v-if="r.source === 'legacy_flow'">Legacy Flow revision</small></small
          >
        </div>
        <el-button
          plain
          type="primary"
          :disabled="survey?.role === 'viewer'"
          @click="restoreRevision(r)"
          >Restore</el-button
        >
      </div>
      <p v-if="!historyError && !revisions.length" class="muted">
        No saved revisions yet.
      </p></el-dialog
    >
  </div>
</template>
