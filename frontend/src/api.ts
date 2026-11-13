import type {
  Survey,
  WorkingData,
  ProjectPage,
  Revision,
  Preview,
  Answer,
  Capabilities,
  PageTiming,
  PreviewDataPage,
  PreviewDataSnapshot,
} from "./types";
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch("/api" + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!r.ok) {
    let message = "Request failed";
    try {
      const data = await r.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail);
    } catch {}
    throw new Error(message);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
export const workingPayload = (s: Survey): WorkingData => ({
  survey_name: s.survey_name,
  survey_config: s.survey_config,
  blocks: s.blocks,
  flow: s.flow,
  ai_configs: s.ai_configs,
});
export const api = {
  capabilities: () => request<Capabilities>("/capabilities"),
  projects: (params: URLSearchParams) =>
    request<ProjectPage>("/projects?" + params),
  create: () => request<Survey>("/projects", { method: "POST" }),
  importProject: (body: {import_request_id: string; project_name: string; file_name: string; content: string}) =>
    request<{survey_id: string}>("/projects/import", {
      method: "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(30_000),
    }),
  prepareExecution: (id: string, version?: number) =>
    request<Survey>(`/surveys/${id}/execution-preparation${version ? "?expected_version=" + version : ""}`,
      { method: "POST" }),
  publish: (s: Survey) =>
    request<Survey>(`/surveys/${s.survey_id}/publish`, {
      method: "POST", body: JSON.stringify({expected_version: s.working_version}),
    }),
  previewSnapshots: (id: string) =>
    request<PreviewDataSnapshot[]>(`/surveys/${id}/preview-data/snapshots`),
  previewData: (id: string, snapshot: string, page: number) =>
    request<PreviewDataPage>(`/surveys/${id}/preview-data/${snapshot}?page=${page}`),
  working: (id: string) => request<Survey>(`/surveys/${id}/working`),
  save: (s: Survey, type: "auto" | "apply") =>
    request<Survey>(`/surveys/${s.survey_id}/working`, {
      method: "PUT",
      body: JSON.stringify({
        ...workingPayload(s),
        expected_version: s.working_version,
        save_type: type,
      }),
    }),
  revisions: (id: string, module: "survey" | "flow") =>
    request<Revision[]>(`/surveys/${id}/revisions?module=${module}`),
  restore: (s: Survey, rid: string, module: "survey" | "flow") =>
    request<Survey>(
      `/surveys/${s.survey_id}/revisions/${rid}/restore?module=${module}`,
      {
        method: "POST",
        body: JSON.stringify({ expected_version: s.working_version }),
      },
    ),
  start: (id: string, version?: number) =>
    request<Preview>(`/surveys/${id}/preview-sessions${version ? "?expected_version=" + version : ""}`, { method: "POST" }),
  submit: (id: string) =>
    request<Preview>(`/preview-sessions/${id}/submit`, { method: "POST" }),
  preview: (id: string) => request<Preview>(`/preview-sessions/${id}`),
  next: (id: string, answers: Record<string, Answer>, timings: PageTiming[] = []) =>
    request<Preview>(`/preview-sessions/${id}/next`, {
      method: "POST",
      body: JSON.stringify({ answers, timings }),
    }),
  back: (id: string) =>
    request<Preview>(`/preview-sessions/${id}/back`, { method: "POST" }),
  quitConversation: (id: string) =>
    request<Preview>(`/preview-sessions/${id}/quit-conversation`, { method: "POST" }),
  chat: (id: string, message: string) =>
    request<Preview>(`/preview-sessions/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  end: (id: string) =>
    request<void>(`/preview-sessions/${id}`, { method: "DELETE" }),
};
