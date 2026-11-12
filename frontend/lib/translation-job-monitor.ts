/**
 * Phase95: UI-only job observer. Translation execution and strict QA remain server-owned.
 * This module deliberately does not start, resume, or mark server jobs complete.
 */
export const JOB_MONITOR_STORAGE_KEY = "pepertranslator:tracked-jobs:v1"

export type TrackedJobKind = "reading" | "layout" | "production" | "preflight" | "batch"
export type TrackedJobStatus = "queued" | "running" | "completed" | "needs_review" | "failed" | "interrupted"

export type TrackedTranslationJob = {
  id: string
  kind: TrackedJobKind
  targetId: string
  title: string
  status: TrackedJobStatus
  progress: number
  createdAt: string
  error: string | null
  missedPolls: number
  announced: boolean
  acknowledged: boolean
}

type ServerStatus = Record<string, unknown>
const KINDS: TrackedJobKind[] = ["reading", "layout", "production", "preflight", "batch"]
const STATUSES: TrackedJobStatus[] = ["queued", "running", "completed", "needs_review", "failed", "interrupted"]

export function isTerminalJob(job: TrackedTranslationJob): boolean {
  return ["completed", "needs_review", "failed", "interrupted"].includes(job.status)
}

export function jobStatusUrl(job: TrackedTranslationJob, apiBase: string): string {
  const target = encodeURIComponent(job.targetId)
  if (job.kind === "batch") return `${apiBase}/api/layout-translation/batches/${target}`
  const root = `${apiBase}/api/pdfs/${target}`
  if (job.kind === "reading") return `${root}/translation`
  if (job.kind === "layout") return `${root}/layout-translation`
  return `${root}/layout-translation/${job.kind}`
}

export function createTrackedJob(kind: TrackedJobKind, targetId: string, title: string): TrackedTranslationJob {
  if (!KINDS.includes(kind)) throw new Error("Unknown job kind")
  const expected = kind === "batch" ? /^[a-f0-9]{32}$/i : /^[a-f0-9]{64}$/i
  if (!expected.test(targetId)) throw new Error("Invalid job identifier")
  return {
    id: `${kind}:${targetId}`, kind, targetId,
    title: title.trim().slice(0, 140) || "名称未設定の論文",
    status: "queued", progress: 0, createdAt: new Date().toISOString(),
    error: null, missedPolls: 0, announced: false, acknowledged: false,
  }
}

/** No success may be inferred from progress=100 or a PDF existing by itself. */
export function updateTrackedJob(job: TrackedTranslationJob, raw: unknown): TrackedTranslationJob {
  if (isTerminalJob(job)) return job
  const state = raw && typeof raw === "object" ? raw as ServerStatus : {}
  const serverStatus = typeof state.status === "string" ? state.status : ""
  if (serverStatus === "not_started" || !serverStatus) {
    const missedPolls = job.missedPolls + 1
    return missedPolls >= 2
      ? { ...job, missedPolls, status: "interrupted", error: "処理状態を復元できませんでした。アプリ再起動後のジョブ状態を確認してください。" }
      : { ...job, missedPolls }
  }
  const rawProgress = typeof state.progress === "number" && Number.isFinite(state.progress) ? state.progress : job.progress
  const progress = Math.max(0, Math.min(100, Math.round(rawProgress)))
  const qa = state.qa && typeof state.qa === "object" ? state.qa as ServerStatus : {}
  const full = state.full && typeof state.full === "object" ? state.full as ServerStatus : {}
  const fullQa = full.qa && typeof full.qa === "object" ? full.qa as ServerStatus : {}
  let status: TrackedJobStatus
  if (serverStatus === "queued" || serverStatus === "running") status = serverStatus
  else if (serverStatus === "completed_with_errors") status = "needs_review"
  else if (serverStatus === "completed") {
    status = (
      (job.kind === "reading" && (Number(state.untranslated_segments || 0) > 0 || state.quality_status === "needs_review")) ||
      (job.kind === "batch" && Number(state.failed || 0) > 0) ||
      (job.kind === "layout" && qa.quality_gate !== "pass") ||
      (job.kind === "production" && fullQa.quality_gate !== "pass") ||
      (job.kind === "preflight" && qa.status !== "pass")
    ) ? "needs_review" : "completed"
  } else if (serverStatus === "failed") {
    const reviewPdf = (job.kind === "layout" && state.mono_ready === true && qa.quality_gate === "fail") ||
      (job.kind === "production" && full.mono_ready === true && fullQa.quality_gate === "fail")
    status = reviewPdf ? "needs_review" : "failed"
  } else {
    // Unknown or stale status is not a success.
    return { ...job, missedPolls: job.missedPolls + 1 }
  }
  const error = typeof state.error === "string" && state.error.trim() ? state.error.slice(0, 450) : null
  return { ...job, status, progress, error, missedPolls: 0 }
}

export function restoreTrackedJobs(raw: string | null): TrackedTranslationJob[] {
  if (!raw) return []
  try {
    const items: unknown = JSON.parse(raw)
    if (!Array.isArray(items)) return []
    const result: TrackedTranslationJob[] = []
    for (const value of items.slice(0, 40)) {
      if (!value || typeof value !== "object") continue
      const item = value as Partial<TrackedTranslationJob>
      const kind = item.kind as TrackedJobKind
      const status = item.status as TrackedJobStatus
      if (!KINDS.includes(kind) || !STATUSES.includes(status)) continue
      const match = kind === "batch" ? /^[a-f0-9]{32}$/i : /^[a-f0-9]{64}$/i
      if (typeof item.targetId !== "string" || !match.test(item.targetId) || item.id !== `${item.kind}:${item.targetId}`) continue
      result.push({
        id: item.id, kind, targetId: item.targetId,
        title: typeof item.title === "string" ? item.title.slice(0, 140) : "名称未設定の論文",
        status, progress: typeof item.progress === "number" ? Math.max(0, Math.min(100, item.progress)) : 0,
        createdAt: typeof item.createdAt === "string" ? item.createdAt : "",
        error: typeof item.error === "string" ? item.error.slice(0, 450) : null,
        missedPolls: 0, announced: item.announced === true, acknowledged: item.acknowledged === true,
      })
    }
    return result
  } catch {
    return []
  }
}

export function keepRecentJobs(jobs: TrackedTranslationJob[]): TrackedTranslationJob[] {
  const active = jobs.filter((job) => !isTerminalJob(job))
  const history = jobs.filter(isTerminalJob).sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 16)
  return [...active, ...history]
}

export function jobStatusLabel(job: TrackedTranslationJob): string {
  switch (job.status) {
    case "queued": return "待機中"
    case "running": return `翻訳中 ${job.progress}%`
    case "completed": return "翻訳完了"
    case "needs_review": return "品質要確認・一部失敗"
    case "failed": return "翻訳失敗"
    case "interrupted": return "処理状態を確認できません"
  }
}
