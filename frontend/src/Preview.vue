<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "./api";
import { validateLaunch } from "./launchValidation";
import type { Preview, Answer, Question, PageTiming } from "./types";
const route = useRoute(),
  router = useRouter(),
  view = ref<Preview | null>(null),
  answers = ref<Record<string, Answer>>({}),
  busy = ref(false),
  error = ref(""),
  message = ref("");
const sid = String(route.params.id),
  storageKey = "survey-preview:" + sid;
const editorPath = `/survey/${sid}/${route.query.from === "flow" ? "flow" : "builder"}`;
const flowPath = `/survey/${sid}/flow`;
const version = typeof route.query.version === "string" ? Number(route.query.version) : undefined;
const translations = {
  en: {
    next: "Next",
    back: "Back",
    finish: "Submit",
    end: "Survey ended.",
    send: "Send",
    retry: "Retry",
    required: "Please answer the required question.",
    error: "Please check your answer.",
    loading: "Loading…",
  },
  ja: {
    next: "次へ",
    back: "戻る",
    finish: "送信",
    end: "調査終了です。",
    send: "送信",
    retry: "再試行",
    required: "必須の質問に回答してください。",
    error: "回答を確認してください。",
    loading: "読み込み中…",
  },
  "zh-CN": {
    next: "下一页",
    back: "返回",
    finish: "提交",
    end: "问卷已结束。",
    send: "发送",
    retry: "重试",
    required: "请回答必填问题。",
    error: "请检查您的回答。",
    loading: "加载中…",
  },
};
const t = computed(
  () =>
    translations[view.value?.survey_config.general.interface_language || "en"],
);
const timingEvents = ref<PageTiming[]>([]);
let displayedPage = "", timerStart = 0;
watch(() => [view.value?.page.kind === "block" ? view.value.page.page_id : "", busy.value], async () => {
  const page = view.value?.page;
  if (busy.value || page?.kind !== "block" || displayedPage === page.page_id) return;
  await nextTick();
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (busy.value || view.value?.page.kind !== "block" || view.value.page.page_id !== page.page_id) return;
    displayedPage = page.page_id;
    timerStart = performance.now();
    timingEvents.value = page.block.questions.filter(q => q.question_type === "multiple_choice" && q.config.response_time.enabled).map(q => ({question_id: q.question_id, events: [{question_id: q.question_id, event: "question_displayed", at: new Date().toISOString(), elapsed_ms: 0}]}));
  }));
}, {flush: "post"});
function interaction(q: Question) {
  const timing = timingEvents.value.find(t => t.question_id === q.question_id);
  if (timing && answers.value[q.question_id] !== null && answers.value[q.question_id] !== undefined) timing.events.push({question_id: q.question_id, event: "option_selected", at: new Date().toISOString(), elapsed_ms: performance.now() - timerStart, value: JSON.parse(JSON.stringify(answers.value[q.question_id] ?? null))});
}
function submissionTimings(): PageTiming[] {
  return timingEvents.value.map(t => ({question_id: t.question_id, events: [...t.events, {question_id: t.question_id, event: "page_submitted", at: new Date().toISOString(), elapsed_ms: performance.now() - timerStart}]}));
}
function setView(v: Preview) {
  if (v.page.kind !== "block" || view.value?.page.kind !== "block" || v.page.page_id !== view.value.page.page_id) {
    displayedPage = ""; timingEvents.value = [];
  }
  view.value = v;
  answers.value = JSON.parse(JSON.stringify(v.answers));
  sessionStorage.setItem(storageKey, v.preview_session_id);
  document.title = v.survey_config.general.display_name || v.survey_name;
  document.documentElement.lang = v.survey_config.general.interface_language;
  const meta =
    document.querySelector('meta[name="robots"]') ||
    document.head.appendChild(document.createElement("meta"));
  meta.setAttribute("name", "robots");
  meta.setAttribute("content", "noindex,nofollow");
}
async function opening() {
  if (
    view.value?.page.kind === "ai" &&
    !view.value.page.messages.length &&
    !view.value.page.error
  ) {
    busy.value = true;
    try {
      setView(await api.chat(view.value.preview_session_id, ""));
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      busy.value = false;
    }
  }
}
async function startPreview(expectedVersion?: number) {
  const working = await api.prepareExecution(sid, expectedVersion);
  validateLaunch(working);
  setView(await api.start(sid, working.working_version));
}
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const nav = performance.getEntriesByType("navigation")[0] as
      PerformanceNavigationTiming | undefined;
    const saved =
      nav?.type === "reload" ? sessionStorage.getItem(storageKey) : null;
    if (saved) {
      try {
        setView(await api.preview(saved));
      } catch {
        await startPreview(version);
      }
    } else await startPreview(version);
  } catch (e) {
    error.value =
      "Failed to load survey preview. Please Retry. " + (e as Error).message;
  } finally {
    busy.value = false;
  }
  await opening();
}
onMounted(load);
async function restart() {
  busy.value = true;
  error.value = "";
  try {
    const old = view.value?.preview_session_id;
    await startPreview();
    if (old) await api.end(old);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
  await opening();
}
async function next() {
  if (!view.value) return;
  busy.value = true;
  error.value = "";
  try {
    const current = view.value.page;
    const values: Record<string, Answer> = {};
    if (current.kind === "block")
      for (const q of current.block.questions)
        if (!q.is_deleted && q.question_type !== "text_graphic")
          values[q.question_id] = answers.value[q.question_id] ?? null;
    setView(await api.next(view.value.preview_session_id, values, submissionTimings()));
    message.value = "";
  } catch (e) {
    const msg = (e as Error).message;
    error.value = msg.startsWith("Required")
      ? t.value.required
      : msg.startsWith("Invalid")
        ? t.value.error
        : msg;
  } finally {
    busy.value = false;
  }
  await opening();
}
async function quitConversation() {
  if (!view.value) return;
  busy.value = true;
  error.value = "";
  try {
    setView(await api.quitConversation(view.value.preview_session_id));
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function submit() {
  if (!view.value) return;
  busy.value = true;
  error.value = "";
  try {
    setView(await api.submit(view.value.preview_session_id));
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function back() {
  if (!view.value) return;
  busy.value = true;
  error.value = "";
  try {
    setView(await api.back(view.value.preview_session_id));
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function send() {
  if (!view.value) return;
  busy.value = true;
  error.value = "";
  try {
    const opening =
      view.value.page.kind === "ai" && !view.value.page.messages.length;
    setView(
      await api.chat(
        view.value.preview_session_id,
        opening ? "" : message.value,
      ),
    );
    message.value = "";
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function exit() {
  if (view.value) {
    try {
      await api.end(view.value.preview_session_id);
    } catch {}
    sessionStorage.removeItem(storageKey);
  }
  if (window.opener) {
    window.close();
    return;
  }
  await router.push(editorPath);
}
function multi(qid: string, value: number, checked: boolean) {
  const a = Array.isArray(answers.value[qid])
    ? [...(answers.value[qid] as number[])]
    : [];
  answers.value[qid] = checked ? [...a, value] : a.filter((v) => v !== value);
}
function matrix(
  qid: string,
  statement: string,
  value: number,
  multiple: boolean,
  checked: boolean,
) {
  const a = answers.value[qid];
  const rows = a && typeof a === "object" && !Array.isArray(a) ? { ...a } : {};
  if (multiple) {
    const values = Array.isArray(rows[statement])
      ? (rows[statement] as number[])
      : [];
    rows[statement] = checked
      ? [...values, value]
      : values.filter((v) => v !== value);
  } else rows[statement] = value;
  answers.value[qid] = rows;
}
function matrixChecked(qid: string, statement: string, value: number) {
  const a = answers.value[qid];
  if (!a || typeof a !== "object" || Array.isArray(a)) return false;
  const row = a[statement];
  return Array.isArray(row) ? row.includes(value) : row === value;
}
function text(qid: string) {
  return typeof answers.value[qid] === "string"
    ? (answers.value[qid] as string)
    : "";
}
function isChecked(q: Question, value: number) {
  const answer = answers.value[q.question_id];
  return Array.isArray(answer) ? answer.includes(value) : answer === value;
}
function dropdown(q: Question, event: Event) {
  const target = event.target as HTMLSelectElement;
  if (
    q.question_type === "multiple_choice" &&
    q.config.answer_type === "multiple"
  )
    answers.value[q.question_id] = Array.from(target.selectedOptions).map((o) =>
      Number(o.value),
    );
  else
    answers.value[q.question_id] = target.value ? Number(target.value) : null;
}
</script>
<template>
  <div class="preview-shell">
    <header class="preview-banner">
      <div>
        <strong>Preview Mode</strong
        ><small
          >This is a preview. Responses will not be recorded as formal survey
          data.</small
        >
      </div>
      <div>
        <el-button :disabled="busy" @click="restart">Restart Preview</el-button
        ><el-button @click="exit">Exit Preview</el-button>
      </div>
    </header>
    <details v-if="view?.execution_path.length" class="preview-path">
      <summary>Flow Execution</summary>
      <ol>
        <li v-for="(node, index) in view.execution_path" :key="node.element_id + index"
          :aria-current="'element_id' in view.page && view.page.element_id === node.element_id ? 'step' : undefined">
          {{ node.label }}
        </li>
      </ol>
    </details>
    <main class="respondent" v-loading="busy && view?.page.kind !== 'block'">
      <h1>
        {{
          view?.survey_config.general.display_name ||
          view?.survey_name ||
          "Survey Preview"
        }}
      </h1>
      <p v-if="view?.survey_config.general.survey_description">
        {{ view.survey_config.general.survey_description }}
      </p>
      <div v-if="error" class="preview-error" role="alert">
        {{ error }}
        <button v-if="!view" class="text-button" @click="load">
          {{ t.retry }}
        </button>
        <div v-if="!view">
          <router-link :to="flowPath">Go to Flow</router-link>
          <router-link :to="`/survey/${sid}/builder`">Go to Builder</router-link>
        </div>
      </div>
      <template v-if="view"
        ><template v-if="view.page.kind === 'block'"
          ><section
            v-for="q in view.page.block.questions.filter((q) => !q.is_deleted)"
            :key="q.question_id"
            class="respondent-question"
            @change="interaction(q)"
          >
            <h2 v-if="q.question_type !== 'text_graphic'">
              <span v-if="view.survey_config.general.show_question_numbers"
                >{{ q.question_name }}. </span
              >{{ q.question_text
              }}<span v-if="q.required" class="danger-text"> *</span>
            </h2>
            <p v-else class="graphic-text">{{ q.question_text }}</p>
            <template v-if="q.question_type === 'multiple_choice'"
              ><select
                v-if="q.config.format === 'dropdown'"
                :multiple="q.config.answer_type === 'multiple'"
                class="respondent-select"
                :aria-label="q.question_text"
                @change="dropdown(q, $event)"
              >
                <option
                  v-if="q.config.answer_type === 'single'"
                  value=""
                ></option>
                <option
                  v-for="c in q.config.choices"
                  :key="c.choice_id"
                  :value="c.value"
                  :selected="isChecked(q, c.value)"
                >
                  {{ c.label }}
                </option>
              </select>
              <div v-else class="choice-design" :class="q.config.layout">
                <label
                  v-for="c in q.config.choices"
                  :key="c.choice_id"
                  class="answer-choice"
                  ><input
                    :type="
                      q.config.answer_type === 'single' ? 'radio' : 'checkbox'
                    "
                    :name="q.question_id"
                    :checked="isChecked(q, c.value)"
                    @change="
                      q.config.answer_type === 'single'
                        ? (answers[q.question_id] = c.value)
                        : multi(
                            q.question_id,
                            c.value,
                            ($event.target as HTMLInputElement).checked,
                          )
                    "
                  /><span>{{ c.label }}</span></label
                >
              </div></template
            >
            <template v-else-if="q.question_type === 'text_entry'">
              <textarea
                v-if="q.config.input_type === 'text_area'"
                :value="text(q.question_id)"
                :maxlength="q.config.max_characters"
                :placeholder="q.config.placeholder"
                :aria-label="q.question_text"
                @input="
                  answers[q.question_id] = (
                    $event.target as HTMLTextAreaElement
                  ).value
                " /><input
                v-else
                class="respondent-text"
                :value="text(q.question_id)"
                :maxlength="q.config.max_characters"
                :placeholder="q.config.placeholder"
                :aria-label="q.question_text"
                @input="
                  answers[q.question_id] = (
                    $event.target as HTMLInputElement
                  ).value
                "
            /></template>
            <div v-else-if="q.question_type === 'matrix'" class="matrix-scroll">
              <div
                class="matrix-grid"
                :style="{
                  gridTemplateColumns: `minmax(160px,2fr) repeat(${q.config.scale_points.length},minmax(100px,1fr))`,
                  minWidth: `${160 + q.config.scale_points.length * 100}px`,
                }"
              >
                <div />
                <strong
                  v-for="c in q.config.scale_points"
                  :key="c.choice_id"
                  class="matrix-label"
                  >{{ c.label }}</strong
                ><template
                  v-for="s in q.config.statements"
                  :key="s.statement_id"
                  ><span>{{ s.label }}</span
                  ><label
                    v-for="c in q.config.scale_points"
                    :key="c.choice_id"
                    class="matrix-cell"
                    ><input
                      :type="
                        q.config.answer_type === 'single' ? 'radio' : 'checkbox'
                      "
                      :name="q.question_id + '-' + s.statement_id"
                      :aria-label="s.label + ' — ' + c.label"
                      :checked="
                        matrixChecked(q.question_id, s.statement_id, c.value)
                      "
                      @change="
                        matrix(
                          q.question_id,
                          s.statement_id,
                          c.value,
                          q.config.answer_type === 'multiple',
                          ($event.target as HTMLInputElement).checked,
                        )
                      " /></label
                ></template>
              </div>
            </div></section
        ></template>
        <section v-else-if="view.page.kind === 'ai'" class="conversation">
          <h2>{{ view.page.config.agent_name }}</h2>
          <p class="muted">
            {{ view.page.turn_count }} / {{ view.page.config.max_turns }} turns
          </p>
          <div
            v-for="(m, i) in view.page.messages"
            :key="i"
            class="chat-message"
            :class="m.role"
          >
            <small>{{
              m.role === "user" ? "Participant" : view.page.config.agent_name
            }}</small>
            <p>{{ m.content }}</p>
          </div>
          <div v-if="view.page.error" class="preview-error">
            {{ view.page.error
            }}<el-button v-if="!view.page.done" @click="send">{{
              t.retry
            }}</el-button>
          </div>
          <div
            v-if="
              !view.page.done && view.page.messages.length && !view.can_continue
            "
            class="chat-input"
          >
            <el-input v-model="message" type="textarea" :rows="3" /><el-button
              type="primary"
              :disabled="busy || !message.trim()"
              @click="send"
              >{{ t.send }}</el-button
            >
          </div>
        </section>
        <section v-else-if="view.page.kind === 'python_error'" class="preview-error" role="alert">
          <strong>{{ view.page.name }} · {{ view.page.error }}</strong>
          <p v-if="view.page.line">Line {{ view.page.line }}</p>
          <p>{{ view.page.message }}</p>
          <el-button :disabled="busy" @click="next">{{ t.retry }}</el-button>
          <router-link :to="{ path: `/survey/${sid}/flow`, query: { element: view.page.element_id } }">Edit Element</router-link>
        </section>
        <p v-else-if="view.page.kind === 'end' && view.page.end_information" class="end-message" style="white-space: pre-wrap">{{ view.page.end_information }}</p>
        <small v-if="view.page.kind === 'end'" role="status">{{
          view.failed ? "Preview ended after an execution error."
            : view.submitted ? "Preview response saved." : t.end
        }}</small>
        <details v-if="view.timing_debug.length"><summary>Preview timing debug</summary><pre>{{ JSON.stringify(view.timing_debug, null, 2) }}</pre></details>
        <footer class="respondent-actions">
          <el-button v-if="view.can_back" :disabled="busy" @click="back">{{
            t.back
          }}</el-button
          ><el-button v-if="view.page.kind === 'ai' && view.page.can_quit && !view.can_continue"
            :disabled="busy" @click="quitConversation">Quit Conversation</el-button>
          <el-button
            v-if="view.page.kind === 'block' || view.page.kind === 'ai'"
            type="primary"
            :disabled="busy || (view.page.kind === 'ai' && !view.page.done) || (view.page.kind === 'block' && view.page.block.questions.some(q => q.question_type === 'multiple_choice' && q.config.response_time.enabled) && !timingEvents.length)"
            @click="next"
            >{{ t.next }}</el-button
          ><el-button v-else-if="view.page.kind === 'end' && !view.submitted && !view.failed" type="primary"
            :loading="busy" @click="submit">{{ t.finish }}</el-button>
        </footer></template
      >
    </main>
  </div>
</template>
