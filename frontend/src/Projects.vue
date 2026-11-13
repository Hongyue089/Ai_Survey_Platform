<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "./api";
import { id } from "./defaults";
import type { ProjectPage } from "./types";
const router = useRouter(),
  search = ref(""),
  sort = ref("last_modified"),
  page = ref(1),
  loading = ref(false),
  creating = ref(false),
  error = ref(""),
  data = ref<ProjectPage>({ items: [], total: 0, page: 1, page_size: 20 });
let version = 0,
  timer: ReturnType<typeof setTimeout>;
async function load() {
  const token = ++version;
  loading.value = true;
  error.value = "";
  try {
    const result = await api.projects(
      new URLSearchParams({
        search_keyword: search.value.trim(),
        sort_option: sort.value,
        page: String(page.value),
        page_size: "20",
      }),
    );
    if (token === version) data.value = result;
  } catch {
    if (token === version) {
      data.value = { items: [], total: 0, page: 1, page_size: 20 };
      error.value = "Failed to load projects. Please Retry.";
    }
  } finally {
    if (token === version) loading.value = false;
  }
}
watch([search, sort], () => {
  page.value = 1;
  clearTimeout(timer);
  timer = setTimeout(load, 250);
});
watch(page, load);
onMounted(load);
async function create() {
  creating.value = true;
  try {
    const s = await api.create();
    await router.push(`/survey/${s.survey_id}/builder`);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    creating.value = false;
  }
}
const importOpen = ref(false),
  importing = ref(false),
  importedId = ref(""),
  importError = ref(""),
  projectName = ref(""),
  selectedFile = ref<File | null>(null);
let requestId = "";

function openImport() {
  importedId.value = "";
  importError.value = "";
  projectName.value = "";
  selectedFile.value = null;
  requestId = "";
  importOpen.value = true;
}
function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".json") || file.size > 2 * 1024 * 1024) {
    importError.value = "Select a .json file no larger than 2 MiB.";
    return;
  }
  selectedFile.value = file;
  if (!projectName.value.trim()) projectName.value = file.name.slice(0, -5).slice(0, 100);
  importError.value = "";
  requestId = "";
}
async function importProject() {
  const file = selectedFile.value;
  const name = projectName.value.trim();
  if (!file || !name || importedId.value || importing.value) return;
  importing.value = true;
  importError.value = "";
  try {
    requestId ||= id();
    const result = await api.importProject({
      import_request_id: requestId, project_name: name, file_name: file.name,
      content: await file.text(),
    });
    importedId.value = result.survey_id;
    void load();
  } catch (e) {
    const failure = e as Error;
    importError.value = failure.name === "TimeoutError" || failure instanceof TypeError
      ? "The result could not be confirmed. Retry with the same file and project name."
      : failure.message;
  } finally {
    importing.value = false;
  }
}
const date = (x: string) =>
  new Date(x).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
</script>
<template>
  <div class="projects-page">
    <header class="global-nav">
      <button aria-label="Projects" @click="router.push('/')">☰</button
      ><span class="help" title="Survey authoring platform">?</span>
    </header>
    <div class="project-toolbar">
      <span class="filter-icon" title="Search filters projects">☷</span
      ><el-select v-model="sort" aria-label="Sort projects" style="width: 155px"
        ><el-option label="Last modified" value="last_modified" /><el-option
          label="Date created"
          value="date_created" /><el-option
          label="Name A–Z"
          value="name_az" /><el-option
          label="Name Z–A"
          value="name_za" /><el-option label="Responses" value="responses"
      /></el-select>
      <div class="toolbar-spacer" />
      <el-input
        v-model="search"
        maxlength="100"
        placeholder="⌕ search Title"
        aria-label="Search project name"
        style="width: 235px"
        clearable
      /><el-button type="primary" title="Import an existing project (JSON)" @click="openImport"
        >Import a Project</el-button
      ><el-button type="primary" :loading="creating" @click="create"
        >Create new project</el-button
      >
    </div>
    <el-dialog
      v-model="importOpen"
      title="Import Project"
      width="min(520px, 92vw)"
      :show-close="!importing"
      :close-on-click-modal="!importing"
      :close-on-press-escape="!importing"
    >
      <el-form label-position="top" @submit.prevent="importProject">
        <el-form-item label="Project Name" required>
          <el-input v-model="projectName" maxlength="100" :disabled="importing || !!importedId"
            @input="requestId = ''" />
        </el-form-item>
        <el-form-item label="Upload JSON File" required>
          <input v-if="!importedId" type="file" accept=".json,application/json"
            aria-label="Upload JSON File" :disabled="importing" @change="chooseFile" />
          <div v-if="selectedFile">
            {{ selectedFile.name }}
            <el-button v-if="!importing && !importedId" text @click="selectedFile = null; requestId = ''">Remove</el-button>
          </div>
        </el-form-item>
        <el-button native-type="submit" type="primary" :loading="importing"
          :disabled="!selectedFile || !projectName.trim() || !!importedId">Import</el-button>
      </el-form>
      <p v-if="importError" role="alert">{{ importError }}</p>
      <p v-if="importedId" role="status">Project imported successfully.</p>
      <template #footer>
        <el-button :disabled="!importedId" @click="router.push(`/survey/${importedId}/builder`)">Go to Builder</el-button>
        <el-button type="primary" :disabled="!importedId"
          @click="router.push(`/survey/${importedId}/preview`)">Go to Preview</el-button>
      </template>
    </el-dialog>
    <main class="project-list" v-loading="loading">
      <button
        v-for="p in data.items"
        :key="p.survey_id"
        class="project-row"
        @click="router.push(`/survey/${p.survey_id}/builder`)"
      >
        <div class="project-title">
          <small>{{ p.project_type }}</small
          ><strong>{{ p.survey_name }}</strong
          ><small>saved at {{ date(p.updated_at) }}</small>
        </div>
        <div class="project-stat">
          <strong :class="p.status">{{
            p.status[0].toUpperCase() + p.status.slice(1)
          }}</strong
          ><small>Status</small>
        </div>
        <div class="project-stat">
          <strong>{{ p.question_count }}</strong
          ><small>Question</small>
        </div>
        <div class="project-stat">
          <strong>{{ p.response_count }}</strong
          ><small>responses</small>
        </div>
      </button>
      <div v-if="!loading && !data.items.length" class="project-empty">
        <span v-if="error"
          >{{ error }}
          <button class="text-button" @click="load">Retry</button></span
        ><span v-else-if="search.trim()"
          >No projects found for "{{ search.trim() }}".</span
        ><span v-else>No projects yet. Create your first survey.</span>
      </div>
      <div class="project-count">
        <span>{{ Math.min(page * 20, data.total) }} of {{ data.total }}</span>
      </div>
    </main>
    <footer class="project-pagination">
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="Math.max(data.total, 1)"
        layout="prev,pager,next"
        :pager-count="5"
      />
    </footer>
  </div>
</template>
