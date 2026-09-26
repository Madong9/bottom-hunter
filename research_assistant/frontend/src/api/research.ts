import type { HealthStatus, ResearchTask, ResearchTaskList } from "../types/research";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function createResearch(query: string): Promise<ResearchTask> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 90_000);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("本次研究超过 90 秒。后端可能仍在处理，请稍后刷新历史记录。");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`);
  }

  return (await response.json()) as ResearchTask;
}

export async function listResearch(limit = 30): Promise<ResearchTaskList> {
  const response = await fetch(`${API_BASE}/api/v1/research?limit=${limit}`);
  if (!response.ok) throw new Error(`加载历史记录失败（${response.status}）`);
  return (await response.json()) as ResearchTaskList;
}

export async function getHealth(): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE}/api/v1/health`);
  if (!response.ok) throw new Error(`后端状态检查失败（${response.status}）`);
  return (await response.json()) as HealthStatus;
}
