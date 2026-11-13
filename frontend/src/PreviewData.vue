<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "./api";
import type { PreviewDataPage, PreviewDataSnapshot } from "./types";

const id = String(useRoute().params.id);
const snapshots = ref<PreviewDataSnapshot[]>([]);
const selected = ref("");
const page = ref(1);
const data = ref<PreviewDataPage | null>(null);
const loading = ref(false);
const error = ref("");
let request = 0;

async function load() {
  if (!selected.value) return;
  const token = ++request;
  loading.value = true;
  error.value = "";
  data.value = null;
  try {
    const result = await api.previewData(id, selected.value, page.value);
    if (token === request) data.value = result;
  } catch (e) {
    if (token === request) error.value = (e as Error).message;
  } finally {
    if (token === request) loading.value = false;
  }
}

async function init() {
  loading.value = true;
  error.value = "";
  try {
    snapshots.value = await api.previewSnapshots(id);
    selected.value = snapshots.value[0]?.snapshot_id || "";
    await load();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

const cell = (value: unknown) => typeof value === "object" && value !== null
  ? JSON.stringify(value) : value ?? "";
onMounted(init);
</script>

<template>
  <main class="preview-data" v-loading="loading">
    <router-link :to="`/survey/${id}/builder`">Back to Builder</router-link>
    <h1>Preview Data</h1>
    <p>Only submitted test responses appear here.</p>
    <p v-if="error" role="alert">{{ error }} <el-button text @click="selected ? load() : init()">Retry</el-button></p>
    <p v-else-if="!loading && !snapshots.length">No submitted preview responses.</p>
    <template v-if="snapshots.length">
      <label for="preview-snapshot">Snapshot</label>
      <select id="preview-snapshot" v-model="selected" @change="page = 1; load()">
        <option v-for="snapshot in snapshots" :key="snapshot.snapshot_id" :value="snapshot.snapshot_id">
          {{ new Date(snapshot.created_at).toLocaleString() }} · {{ snapshot.snapshot_id.slice(0, 8) }}
          · {{ snapshot.response_count }} responses
        </option>
      </select>
      <a :href="`/api/surveys/${id}/preview-data/${selected}/csv`">Download CSV</a>
      <template v-if="data">
        <el-table :data="data.items">
          <el-table-column label="Submitted" min-width="170">
            <template #default="{row}">{{ new Date(row.submitted_at).toLocaleString() }}</template>
          </el-table-column>
          <el-table-column v-for="column in data.columns" :key="column.question_id" :label="column.name" min-width="140">
            <template #default="{row}">{{ cell(row.answers[column.question_id]) }}</template>
          </el-table-column>
          <el-table-column label="content" min-width="230">
            <template #default="{row}">{{ cell(row.content) }}</template>
          </el-table-column>
        </el-table>
        <el-pagination v-if="data.total > data.page_size" v-model:current-page="page"
          :page-size="data.page_size" :total="data.total" layout="prev, pager, next" @current-change="load" />
      </template>
    </template>
  </main>
</template>

<style scoped>
.preview-data { margin: 24px auto; max-width: 1120px; padding: 0 20px; }
.preview-data select { margin: 0 16px; padding: 5px; }
.preview-data .el-table { margin: 16px 0; }
</style>
