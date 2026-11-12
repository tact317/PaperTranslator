"use client"

import * as React from "react"
import { Inter, JetBrains_Mono } from "next/font/google"
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Files,
  FolderOpen,
  HelpCircle,
  Keyboard,
  Lightbulb,
  List,
  Languages,
  Download,
  Loader2,
  Maximize2,
  Minus,
  MoreVertical,
  Plus,
  Printer,
  RotateCcw,
  Search,
  Send,
  Settings,
  Sparkles,
  XCircle,
  Zap,
} from "lucide-react"

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

const inter = Inter({
  subsets: ["latin", "latin-ext"],
  variable: "--font-inter",
})

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

type QuizStatus = "idle" | "checking" | "correct" | "partial" | "incorrect"

type KeyPointStatus = "correct" | "warning" | "missing"

type IssueCategory = "omission" | "mistranslation" | "wording" | "terminology"

type SyntaxInsight = {
  summary: string
  relations: {
    left: string
    relation: string
    right: string
    explanation: string
  }[]
}

type QuizItem = {
  id: number
  sourceText: string
  pageRef: number
}

type Evaluation = {
  verdict: "correct" | "partial" | "incorrect"
  score: number
  feedback: string
  referenceTranslation: string
  meaningErrors: string[]
  missingInformation: string[]
  issues: {
    category: IssueCategory
    sourceSpan: string
    message: string
    suggestion: string
  }[]
  keyPoints: {
    source: string
    translation: string
    status: KeyPointStatus
  }[]
  syntaxInsight: SyntaxInsight | null
}

type AttemptRecord = {
  answer: string
  evaluation: Evaluation
  createdAt: string
}

type QuestionRecord = {
  answer: string
  evaluation: Evaluation | null
  attempts: AttemptRecord[]
  updatedAt: string
}

type SavedSession = {
  version: 2
  currentIndex: number
  records: Record<string, QuestionRecord>
}

type UploadState = "empty" | "uploading" | "ready" | "error"

type UploadResponse = {
  status: "success"
  filename: string
  title: string
  document_id: string
  page_count: number
  total_chunks: number
  chunks: {
    id: number
    pageRef: number
    sourceText: string
  }[]
}

type RightPanelMode = "study" | "japanese"

type DocumentTranslationStatus = {
  status: "not_started" | "queued" | "running" | "completed" | "failed"
  progress: number
  translated_segments: number
  total_segments: number
  error: string | null
  updated_at: string | number | null
}

type TranslatedSegment = {
  id: number
  pageRef: number
  sourceText: string
  translation: string
}

type DocumentTranslationResult = {
  status: "success"
  document_id: string
  title: string
  model: string
  scope: "body"
  generated_at: string
  segments: TranslatedSegment[]
}

type JapaneseViewMode = "reading" | "layout"

type LayoutQaWarning = {
  severity: "critical" | "high" | "medium" | "low"
  page: number | null
  code: string
  message: string
  suggestion: string
}

type LayoutQaReport = {
  status: "ok" | "warning" | "failed"
  warning_count: number
  critical_count?: number
  high_count?: number
  quality_gate?: "pass" | "fail"
  coverage?: {
    body_japanese_chars: number
    body_latin_chars: number
    japanese_ratio: number
    japanese_percent: number
    minimum_percent: number
    untranslated_pages: number[]
  }
  method: string
  model: string
  generated_at: string
  warnings: LayoutQaWarning[]
}

type LayoutPreflightQa = {
  status: "pass" | "fail"
  page: number
  generated_at: string
  model: string
  japanese_percent: number
  prompt_leak_hits: string[]
  numeric_integrity: boolean
  untranslated: boolean
  proxy_request_count: number
  isolated_request_count: number
  problems: { code: string; message: string }[]
}

type LayoutPreflightStatus = {
  status: "not_started" | "queued" | "running" | "completed" | "failed"
  progress: number
  error: string | null
  updated_at: string | number | null
  page: number
  mono_ready: boolean
  qa: LayoutPreflightQa | null
  quality_profile?: string
  cached_quality_profile?: string | null
  cache_stale?: boolean
  proxy_requests?: number
  guard_events?: number
  last_activity_at?: string | number | null
}

type LayoutProductionStatus = {
  status: "not_started" | "queued" | "running" | "completed" | "failed"
  stage: "idle" | "queued" | "preflight" | "full" | "completed"
  progress: number
  error: string | null
  page: number
  updated_at: string | number | null
  quality_profile?: string
  preflight?: LayoutPreflightStatus
  full?: LayoutTranslationStatus
}

type LayoutBatchItem = {
  document_id: string
  filename: string
  title: string
  status: "queued" | "running" | "completed" | "failed"
  stage: "queued" | "preflight" | "full" | "completed" | "failed"
  failure_stage?: "preflight" | "full" | null
  progress: number
  error: string | null
  cached?: boolean
  output_dir?: string | null
  artifact_dir?: string | null
  artifact_stage?: "root" | "preflight" | "full"
  artifacts_available?: boolean
  qa_available?: boolean
  qa_stage?: "preflight" | "full" | null
  pdf_available?: boolean
  pdf_stage?: "preflight" | "full" | null
  quality_gate?: "pass" | "fail" | null
}

type LayoutBatchStatus = {
  batch_id: string
  status: "queued" | "running" | "completed" | "completed_with_errors" | "failed"
  progress: number
  error: string | null
  total: number
  completed: number
  failed: number
  current_index: number | null
  current_document_id: string | null
  created_at?: string | null
  quality_profile?: string | null
  app_build?: string | null
  api_version?: string | null
  current_quality_profile?: string | null
  current_app_build?: string | null
  current_api_version?: string | null
  stale_quality_profile?: boolean
  historical_build?: boolean
  items: LayoutBatchItem[]
}

type BatchUploadProgress = {
  active: boolean
  total: number
  uploaded: number
  error: string | null
}

type LayoutTranslationStatus = {
  status: "not_started" | "queued" | "running" | "completed" | "failed"
  progress: number
  error: string | null
  updated_at: string | number | null
  worker_ready: boolean
  worker_path: string | null
  model: string
  mono_ready: boolean
  dual_ready: boolean
  output_dir?: string | null
  qa: LayoutQaReport | null
  preflight?: LayoutPreflightStatus
  quality_profile?: string
  cached_quality_profile?: string | null
  cache_stale?: boolean
  proxy_requests?: number
  guard_events?: number
  last_activity_at?: string | number | null
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000"

async function requestOpenLayoutOutputFolder(documentId: string) {
  const response = await fetch(
    `${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/open-folder`,
    { method: "POST" }
  )
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(data?.detail || "\u4fdd\u5b58\u30d5\u30a9\u30eb\u30c0\u3092\u958b\u3051\u307e\u305b\u3093\u3067\u3057\u305f\u3002")
  }
  return data as { status: "opened"; path: string }
}

async function requestOpenLayoutArtifactFolder(
  documentId: string,
  stage: "auto" | "preflight" | "full" = "auto"
) {
  const response = await fetch(
    `${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/open-artifacts?stage=${stage}`,
    { method: "POST" }
  )
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(data?.detail || "証拠フォルダを開けませんでした。")
  }
  return data as { status: "opened"; stage: string; path: string }
}

function openLayoutArtifactFile(
  documentId: string,
  kind: "qa" | "pdf",
  stage: "auto" | "preflight" | "full" = "auto"
) {
  const url = `${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/artifact-${kind}?stage=${stage}`
  window.open(url, "_blank", "noopener,noreferrer")
}

function sessionStorageKey(documentId: string) {
  return `paper-translator:session:${documentId}`
}

function hasBilingualKeyPoints(evaluation: Evaluation | null) {
  if (!evaluation || evaluation.keyPoints.length === 0) return true
  return evaluation.keyPoints.every((point) => point.translation?.trim())
}

function effectiveEvaluation(record: QuestionRecord | undefined) {
  if (!record) return null
  return record.evaluation ?? record.attempts[record.attempts.length - 1]?.evaluation ?? null
}

function needsReview(evaluation: Evaluation | null) {
  if (!evaluation) return false
  if (evaluation.score < 85) return true
  if (evaluation.issues.some((issue) => issue.category === "omission" || issue.category === "mistranslation")) {
    return true
  }
  return evaluation.keyPoints.some((point) => point.status !== "correct")
}

function readSavedSession(documentId: string): SavedSession | null {
  try {
    const raw = window.localStorage.getItem(sessionStorageKey(documentId))
    if (!raw) return null

    const parsed = JSON.parse(raw) as {
      version?: number
      currentIndex?: number
      records?: Record<
        string,
        {
          answer?: string
          evaluation?: Evaluation | null
          attempts?: AttemptRecord[]
          updatedAt?: string
        }
      >
    }

    if (typeof parsed.currentIndex !== "number" || !parsed.records) {
      return null
    }

    const records = Object.fromEntries(
      Object.entries(parsed.records).map(([key, record]) => {
        const evaluation = record.evaluation ?? null
        const attempts =
          Array.isArray(record.attempts) && record.attempts.length > 0
            ? record.attempts
            : evaluation
              ? [
                  {
                    answer: record.answer ?? "",
                    evaluation,
                    createdAt: record.updatedAt ?? new Date().toISOString(),
                  },
                ]
              : []

        // Phase 4以前の保存結果には日本語キーポイントが無い場合がある。
        // 回答と履歴は残しつつ、最新評価だけ無効化して再採点可能にする。
        const currentEvaluation = hasBilingualKeyPoints(evaluation) ? evaluation : null

        return [
          key,
          {
            answer: record.answer ?? "",
            evaluation: currentEvaluation,
            attempts,
            updatedAt: record.updatedAt ?? new Date().toISOString(),
          } satisfies QuestionRecord,
        ]
      })
    )

    return {
      version: 2,
      currentIndex: parsed.currentIndex,
      records,
    }
  } catch {
    return null
  }
}


export default function Page() {
  const [questions, setQuestions] = React.useState<QuizItem[]>([])
  const [currentIndex, setCurrentIndex] = React.useState(0)
  const [answer, setAnswer] = React.useState("")
  const [status, setStatus] = React.useState<QuizStatus>("idle")
  const [evaluation, setEvaluation] = React.useState<Evaluation | null>(null)
  const [records, setRecords] = React.useState<Record<string, QuestionRecord>>({})
  const [reviewSequence, setReviewSequence] = React.useState<number[] | null>(null)

  const [paperTitle, setPaperTitle] = React.useState("No paper loaded")
  const [filename, setFilename] = React.useState<string | null>(null)
  const [pageCount, setPageCount] = React.useState(0)
  const [documentId, setDocumentId] = React.useState<string | null>(null)
  const [uploadState, setUploadState] = React.useState<UploadState>("empty")
  const [uploadError, setUploadError] = React.useState<string | null>(null)

  const [reportOpen, setReportOpen] = React.useState(false)
  const [reportText, setReportText] = React.useState("")
  const [reportSent, setReportSent] = React.useState(false)

  const [rightMode, setRightMode] = React.useState<RightPanelMode>("study")
  const [documentTranslationStatus, setDocumentTranslationStatus] =
    React.useState<DocumentTranslationStatus>({
      status: "not_started",
      progress: 0,
      translated_segments: 0,
      total_segments: 0,
      error: null,
      updated_at: null,
    })
  const [documentTranslation, setDocumentTranslation] =
    React.useState<DocumentTranslationResult | null>(null)
  const [japaneseViewMode, setJapaneseViewMode] = React.useState<JapaneseViewMode>("reading")
  const [layoutTranslationStatus, setLayoutTranslationStatus] =
    React.useState<LayoutTranslationStatus>({
      status: "not_started",
      progress: 0,
      error: null,
      updated_at: null,
      worker_ready: false,
      worker_path: null,
      model: "",
      mono_ready: false,
      dual_ready: false,
      qa: null,
    })
  const [layoutProductionStatus, setLayoutProductionStatus] =
    React.useState<LayoutProductionStatus>({
      status: "not_started",
      stage: "idle",
      progress: 0,
      error: null,
      page: 2,
      updated_at: null,
    })
  const [layoutBatchStatus, setLayoutBatchStatus] = React.useState<LayoutBatchStatus | null>(null)
  const [batchPanelOpen, setBatchPanelOpen] = React.useState(false)
  const [batchUploadProgress, setBatchUploadProgress] = React.useState<BatchUploadProgress>({
    active: false,
    total: 0,
    uploaded: 0,
    error: null,
  })
  const [readerPageRequest, setReaderPageRequest] = React.useState<number | null>(null)
  const [readerViewPage, setReaderViewPage] = React.useState(1)

  const current = questions[currentIndex] ?? null
  const reviewCandidateIndices = React.useMemo(
    () =>
      questions.flatMap((question, index) =>
        needsReview(effectiveEvaluation(records[String(question.id)])) ? [index] : []
      ),
    [questions, records]
  )
  const reviewMode = reviewSequence !== null
  const navigationPosition = reviewMode
    ? Math.max(reviewSequence.indexOf(currentIndex), 0)
    : currentIndex
  const navigationTotal = reviewMode ? reviewSequence.length : questions.length
  const isLastQuestion = navigationTotal > 0 && navigationPosition === navigationTotal - 1
  const progress = navigationTotal > 0 ? ((navigationPosition + 1) / navigationTotal) * 100 : 0
  const completedCount = Object.keys(records).filter(
    (key) => (records[key]?.attempts.length ?? 0) > 0
  ).length
  const currentAttempts = current ? records[String(current.id)]?.attempts ?? [] : []

  React.useEffect(() => {
    if (!documentId || questions.length === 0) return

    const session: SavedSession = {
      version: 2,
      currentIndex,
      records,
    }

    try {
      window.localStorage.setItem(sessionStorageKey(documentId), JSON.stringify(session))
    } catch (error) {
      console.warn("Session save failed:", error)
    }
  }, [currentIndex, documentId, questions.length, records])

  React.useEffect(() => {
    if (!documentId) return
    if (documentTranslationStatus.status !== "queued" && documentTranslationStatus.status !== "running") {
      return
    }

    const timer = window.setInterval(() => {
      void refreshDocumentTranslation(documentId)
    }, 1500)
    return () => window.clearInterval(timer)
  }, [documentId, documentTranslationStatus.status])

  React.useEffect(() => {
    if (!documentId) return
    const fullRunning = layoutTranslationStatus.status === "queued" || layoutTranslationStatus.status === "running"
    const preflightRunning = layoutTranslationStatus.preflight?.status === "queued" || layoutTranslationStatus.preflight?.status === "running"
    if (!fullRunning && !preflightRunning) {
      return
    }
    const timer = window.setInterval(() => {
      void refreshLayoutTranslation(documentId)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [documentId, layoutTranslationStatus.status, layoutTranslationStatus.preflight?.status])

  React.useEffect(() => {
    if (!documentId) return
    if (layoutProductionStatus.status !== "queued" && layoutProductionStatus.status !== "running") {
      return
    }
    const timer = window.setInterval(() => {
      void refreshLayoutProduction(documentId)
      void refreshLayoutTranslation(documentId)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [documentId, layoutProductionStatus.status])

  React.useEffect(() => {
    try {
      const batchId = window.localStorage.getItem("paper-translator:last-layout-batch")
      if (batchId) void refreshLayoutBatch(batchId, false)
    } catch {
      // localStorage is optional; an active backend batch keeps running without it.
    }
  }, [])

  React.useEffect(() => {
    const batchId = layoutBatchStatus?.batch_id
    if (!batchId || (layoutBatchStatus.status !== "queued" && layoutBatchStatus.status !== "running")) {
      return
    }
    const timer = window.setInterval(() => {
      void refreshLayoutBatch(batchId, false)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [layoutBatchStatus?.batch_id, layoutBatchStatus?.status])

  async function refreshDocumentTranslation(targetDocumentId: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${targetDocumentId}/translation`)
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "全文翻訳の状態取得に失敗しました。")
      }

      const nextStatus = data as DocumentTranslationStatus
      setDocumentTranslationStatus(nextStatus)

      if (nextStatus.status === "completed") {
        const resultResponse = await fetch(
          `${API_BASE_URL}/api/pdfs/${targetDocumentId}/translation/result`
        )
        const resultData = await resultResponse.json().catch(() => null)
        if (!resultResponse.ok) {
          throw new Error(resultData?.detail || "日本語版の読み込みに失敗しました。")
        }
        setDocumentTranslation(resultData as DocumentTranslationResult)
      }
    } catch (error) {
      console.error("Document translation status error:", error)
    }
  }

  async function startDocumentTranslation(force = false) {
    if (!documentId) return
    setRightMode("japanese")
    setDocumentTranslation(null)
    setDocumentTranslationStatus((previous) => ({
      ...previous,
      status: "queued",
      progress: 0,
      error: null,
    }))

    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${documentId}/translation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force, title: paperTitle }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "全文翻訳を開始できませんでした。")
      }
      setDocumentTranslationStatus(data as DocumentTranslationStatus)
      if (data?.status === "completed") {
        await refreshDocumentTranslation(documentId)
      }
    } catch (error) {
      setDocumentTranslationStatus({
        status: "failed",
        progress: 0,
        translated_segments: 0,
        total_segments: 0,
        error: error instanceof Error ? error.message : "全文翻訳に失敗しました。",
        updated_at: null,
      })
    }
  }

  async function refreshLayoutTranslation(targetDocumentId: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${targetDocumentId}/layout-translation`)
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "レイアウト翻訳の状態取得に失敗しました。")
      }
      setLayoutTranslationStatus(data as LayoutTranslationStatus)
    } catch (error) {
      console.error("Layout translation status error:", error)
    }
  }

  async function refreshLayoutProduction(targetDocumentId: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${targetDocumentId}/layout-translation/production`)
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "安全な一括生成の状態取得に失敗しました。")
      }
      const next = data as LayoutProductionStatus
      setLayoutProductionStatus(next)
      if (next.status === "completed" || next.status === "failed") {
        await refreshLayoutTranslation(targetDocumentId)
      }
    } catch (error) {
      console.error("Layout production status error:", error)
    }
  }

  async function startLayoutTranslation(force = false) {
    if (!documentId) return
    setRightMode("japanese")
    setJapaneseViewMode("layout")
    setLayoutTranslationStatus((previous) => ({
      ...previous,
      status: "queued",
      progress: 0,
      error: null,
    }))
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${documentId}/layout-translation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "レイアウト翻訳を開始できませんでした。")
      }
      setLayoutTranslationStatus(data as LayoutTranslationStatus)
    } catch (error) {
      setLayoutTranslationStatus((previous) => ({
        ...previous,
        status: "failed",
        progress: 0,
        error: error instanceof Error ? error.message : "レイアウト翻訳に失敗しました。",
      }))
    }
  }

  async function startLayoutPreflight(force = true) {
    if (!documentId) return
    setRightMode("japanese")
    setJapaneseViewMode("layout")
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/preflight`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force, page: 2 }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "1ページテストを開始できませんでした。")
      }
      await refreshLayoutTranslation(documentId)
    } catch (error) {
      setLayoutTranslationStatus((previous) => ({
        ...previous,
        preflight: {
          status: "failed",
          progress: 0,
          error: error instanceof Error ? error.message : "1ページテストに失敗しました。",
          updated_at: null,
          page: 2,
          mono_ready: false,
          qa: null,
        },
      }))
    }
  }

  async function startLayoutProduction(force = false) {
    if (!documentId) return
    setRightMode("japanese")
    setJapaneseViewMode("layout")
    setLayoutProductionStatus({
      status: "queued",
      stage: "queued",
      progress: 0,
      error: null,
      page: 2,
      updated_at: null,
    })
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/production`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force, page: 2 }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "安全な一括生成を開始できませんでした。")
      }
      setLayoutProductionStatus(data as LayoutProductionStatus)
      await refreshLayoutTranslation(documentId)
    } catch (error) {
      setLayoutProductionStatus({
        status: "failed",
        stage: "queued",
        progress: 0,
        error: error instanceof Error ? error.message : "安全な一括生成に失敗しました。",
        page: 2,
        updated_at: null,
      })
    }
  }

  async function refreshLayoutBatch(batchId: string, openPanel = true) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/layout-translation/batches/${batchId}`)
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        if (response.status === 404) {
          try { window.localStorage.removeItem("paper-translator:last-layout-batch") } catch {}
          setLayoutBatchStatus(null)
          return
        }
        throw new Error(data?.detail || "バッチの状態取得に失敗しました。")
      }
      const next = data as LayoutBatchStatus
      // Phase74: the browser used to auto-restore the last persisted batch even
      // after a quality-profile upgrade. That made an old Phase72 result look like
      // a fresh Phase73 rerun. Ignore stale historical batches on automatic restore;
      // explicit current-session batches are still shown normally.
      if (!openPanel && (next.stale_quality_profile || next.historical_build)) {
        try { window.localStorage.removeItem("paper-translator:last-layout-batch") } catch {}
        setLayoutBatchStatus(null)
        return
      }
      setLayoutBatchStatus(next)
      if (openPanel) setBatchPanelOpen(true)
    } catch (error) {
      console.error("Layout batch status error:", error)
    }
  }

  async function startLayoutBatch(files: File[]) {
    const pdfFiles = files.filter(
      (file) => file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf"
    )
    if (pdfFiles.length === 0) {
      setBatchUploadProgress({ active: false, total: 0, uploaded: 0, error: "PDFファイルを選択してください。" })
      setBatchPanelOpen(true)
      return
    }
    if (pdfFiles.length > 20) {
      setBatchUploadProgress({ active: false, total: pdfFiles.length, uploaded: 0, error: "1回のバッチは20件までです。" })
      setBatchPanelOpen(true)
      return
    }

    setBatchPanelOpen(true)
    setLayoutBatchStatus(null)
    setBatchUploadProgress({ active: true, total: pdfFiles.length, uploaded: 0, error: null })
    const uploadedItems: { document_id: string; filename: string; title: string }[] = []
    const uploadFailures: string[] = []

    for (let index = 0; index < pdfFiles.length; index += 1) {
      const file = pdfFiles[index]
      try {
        const formData = new FormData()
        formData.append("file", file)
        const response = await fetch(`${API_BASE_URL}/api/upload-pdf`, { method: "POST", body: formData })
        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || "PDFの解析に失敗しました。")
        const upload = data as UploadResponse
        uploadedItems.push({
          document_id: upload.document_id,
          filename: upload.filename,
          title: upload.title || upload.filename,
        })
      } catch (error) {
        uploadFailures.push(`${file.name}: ${error instanceof Error ? error.message : "アップロード失敗"}`)
      } finally {
        setBatchUploadProgress((previous) => ({ ...previous, uploaded: index + 1 }))
      }
    }

    if (uploadedItems.length === 0) {
      setBatchUploadProgress({
        active: false,
        total: pdfFiles.length,
        uploaded: pdfFiles.length,
        error: uploadFailures.join("\n") || "処理できるPDFがありませんでした。",
      })
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/layout-translation/batches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: uploadedItems, force: false, page: 2 }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || "バッチを開始できませんでした。")
      const next = data as LayoutBatchStatus
      setLayoutBatchStatus(next)
      try { window.localStorage.setItem("paper-translator:last-layout-batch", next.batch_id) } catch {}
      setBatchUploadProgress({
        active: false,
        total: pdfFiles.length,
        uploaded: pdfFiles.length,
        error: uploadFailures.length ? `${uploadFailures.length}件は追加できませんでした。\n${uploadFailures.join("\n")}` : null,
      })
    } catch (error) {
      setBatchUploadProgress({
        active: false,
        total: pdfFiles.length,
        uploaded: pdfFiles.length,
        error: error instanceof Error ? error.message : "バッチ開始に失敗しました。",
      })
    }
  }

  async function loadPdf(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
      setUploadState("error")
      setUploadError("PDFファイルを選択してください。")
      return
    }

    setUploadState("uploading")
    setUploadError(null)
    setQuestions([])
    setCurrentIndex(0)
    setAnswer("")
    setStatus("idle")
    setEvaluation(null)
    setRecords({})
    setReviewSequence(null)
    setRightMode("study")
    setDocumentTranslation(null)
    setDocumentTranslationStatus({
      status: "not_started",
      progress: 0,
      translated_segments: 0,
      total_segments: 0,
      error: null,
      updated_at: null,
    })
    setJapaneseViewMode("reading")
    setLayoutTranslationStatus({
      status: "not_started",
      progress: 0,
      error: null,
      updated_at: null,
      worker_ready: false,
      worker_path: null,
      model: "",
      mono_ready: false,
      dual_ready: false,
      qa: null,
    })
    setLayoutProductionStatus({
      status: "not_started",
      stage: "idle",
      progress: 0,
      error: null,
      page: 2,
      updated_at: null,
    })
    setReaderPageRequest(null)
    setReaderViewPage(1)

    setDocumentId(null)
    setFilename(file.name)
    setPaperTitle(file.name.replace(/\.pdf$/i, ""))

    try {
      const formData = new FormData()
      formData.append("file", file)

      const response = await fetch(`${API_BASE_URL}/api/upload-pdf`, {
        method: "POST",
        body: formData,
      })
      const data = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(data?.detail || "PDFの解析に失敗しました。")
      }

      const upload = data as UploadResponse
      setFilename(upload.filename)
      setPaperTitle(upload.title || upload.filename)
      setDocumentId(upload.document_id)
      setPageCount(upload.page_count)
      setQuestions(upload.chunks)

      const savedSession = readSavedSession(upload.document_id)
      const restoredRecords = savedSession?.records ?? {}
      const restoredIndex = Math.min(
        Math.max(savedSession?.currentIndex ?? 0, 0),
        Math.max(upload.chunks.length - 1, 0)
      )
      const restoredQuestion = upload.chunks[restoredIndex]
      const restoredRecord = restoredQuestion
        ? restoredRecords[String(restoredQuestion.id)]
        : undefined

      setRecords(restoredRecords)
      setCurrentIndex(restoredIndex)
      setAnswer(restoredRecord?.answer ?? "")
      setEvaluation(restoredRecord?.evaluation ?? null)
      setStatus(restoredRecord?.evaluation?.verdict ?? "idle")
      setUploadState("ready")
      void refreshDocumentTranslation(upload.document_id)
      void refreshLayoutTranslation(upload.document_id)
      void refreshLayoutProduction(upload.document_id)
    } catch (error) {
      console.error("PDF upload error:", error)
      setQuestions([])
      setDocumentId(null)
      setPageCount(0)
      setUploadState("error")
      setUploadError(error instanceof Error ? error.message : "PDFの解析に失敗しました。")
    }
  }

  async function submitAnswer() {
    if (!current || !answer.trim() || status === "checking") return
    setStatus("checking")
    setEvaluation(null)

    try {
      const response = await fetch(`${API_BASE_URL}/api/check-translation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_text: current.sourceText,
          user_answer: answer,
        }),
      })
      const data = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(data?.detail || "採点APIとの通信に失敗しました。")
      }
      if (data?.status !== "success" || !data.evaluation) {
        throw new Error("採点結果の形式が不正です。")
      }

      const apiEvaluation = data.evaluation
      const nextEvaluation: Evaluation = {
        verdict: apiEvaluation.verdict,
        score: apiEvaluation.score,
        feedback: apiEvaluation.feedback,
        referenceTranslation: apiEvaluation.reference_translation,
        meaningErrors: apiEvaluation.meaning_errors ?? [],
        missingInformation: apiEvaluation.missing_information ?? [],
        issues: (apiEvaluation.issues ?? []).map(
          (issue: {
            category: IssueCategory
            source_span?: string
            message: string
            suggestion?: string
          }) => ({
            category: issue.category,
            sourceSpan: issue.source_span ?? "",
            message: issue.message,
            suggestion: issue.suggestion ?? "",
          })
        ),
        keyPoints: apiEvaluation.key_points ?? [],
        syntaxInsight:
          apiEvaluation.syntax_focus?.needed && Array.isArray(apiEvaluation.syntax_focus?.relations)
            ? {
                summary: apiEvaluation.syntax_focus.summary ?? "",
                relations: apiEvaluation.syntax_focus.relations.map(
                  (relation: {
                    left?: string
                    relation?: string
                    right?: string
                    explanation?: string
                  }) => ({
                    left: relation.left ?? "",
                    relation: relation.relation ?? "関係",
                    right: relation.right ?? "",
                    explanation: relation.explanation ?? "",
                  })
                ),
              }
            : null,
      }

      setEvaluation(nextEvaluation)
      setStatus(nextEvaluation.verdict)
      setRecords((prev) => {
        const previous = prev[String(current.id)]
        const attempt: AttemptRecord = {
          answer,
          evaluation: nextEvaluation,
          createdAt: new Date().toISOString(),
        }

        return {
          ...prev,
          [String(current.id)]: {
            answer,
            evaluation: nextEvaluation,
            attempts: [...(previous?.attempts ?? []), attempt],
            updatedAt: attempt.createdAt,
          },
        }
      })
    } catch (error) {
      console.error("Scoring API error:", error)
      setStatus("idle")
      alert(error instanceof Error ? error.message : "採点に失敗しました。")
    }
  }

  function openQuestion(index: number) {
    if (index < 0 || index >= questions.length) return
    const nextQuestion = questions[index]
    const record = records[String(nextQuestion.id)]
    setCurrentIndex(index)
    setAnswer(record?.answer ?? "")
    setEvaluation(record?.evaluation ?? null)
    setStatus(record?.evaluation?.verdict ?? "idle")
  }

  function openReviewQuestion(index: number) {
    if (index < 0 || index >= questions.length) return
    const nextQuestion = questions[index]
    const record = records[String(nextQuestion.id)]
    setCurrentIndex(index)
    setAnswer(record?.answer ?? "")
    setEvaluation(null)
    setStatus("idle")

    if (record) {
      setRecords((prev) => ({
        ...prev,
        [String(nextQuestion.id)]: {
          ...record,
          evaluation: null,
          updatedAt: new Date().toISOString(),
        },
      }))
    }
  }

  function goNext() {
    if (isLastQuestion) return
    if (reviewSequence) {
      const position = reviewSequence.indexOf(currentIndex)
      if (position < 0 || position >= reviewSequence.length - 1) return
      openReviewQuestion(reviewSequence[position + 1])
      return
    }
    openQuestion(currentIndex + 1)
  }

  function goPrevious() {
    if (reviewSequence) {
      const position = reviewSequence.indexOf(currentIndex)
      if (position <= 0) return
      openReviewQuestion(reviewSequence[position - 1])
      return
    }
    if (currentIndex <= 0) return
    openQuestion(currentIndex - 1)
  }

  function toggleReviewMode() {
    if (reviewSequence) {
      setReviewSequence(null)
      return
    }
    if (reviewCandidateIndices.length === 0) return
    setReviewSequence(reviewCandidateIndices)
    openReviewQuestion(reviewCandidateIndices[0])
  }

  function updateAnswer(value: string) {
    setAnswer(value)
    if (!current) return
    setRecords((prev) => ({
      ...prev,
      [String(current.id)]: {
        answer: value,
        evaluation: prev[String(current.id)]?.evaluation ?? null,
        attempts: prev[String(current.id)]?.attempts ?? [],
        updatedAt: new Date().toISOString(),
      },
    }))
  }

  function startRevision() {
    if (!current) return
    setStatus("idle")
    setEvaluation(null)
    setRecords((prev) => {
      const previous = prev[String(current.id)]
      if (!previous) return prev

      return {
        ...prev,
        [String(current.id)]: {
          ...previous,
          evaluation: null,
          updatedAt: new Date().toISOString(),
        },
      }
    })
  }

  function resetQuiz() {
    setCurrentIndex(0)
    setAnswer("")
    setStatus("idle")
    setReportOpen(false)
    setReportText("")
    setReportSent(false)
    setEvaluation(null)
    setRecords({})
    setReviewSequence(null)
    setRightMode("study")
    if (documentId) {
      try {
        window.localStorage.removeItem(sessionStorageKey(documentId))
      } catch {
        // localStorage が利用できない環境でもリセット自体は継続する。
      }
    }
  }

  function submitReport() {
    if (!reportText.trim()) return
    setReportSent(true)
    setReportText("")
    window.setTimeout(() => {
      setReportSent(false)
      setReportOpen(false)
    }, 2000)
  }

  return (
    <main
      className={cn(
        inter.className,
        jetBrainsMono.variable,
        "h-screen overflow-hidden bg-zinc-950 text-zinc-50 antialiased",
        "selection:bg-indigo-500/20 selection:text-indigo-100"
      )}
    >
      <div className="flex h-full flex-col">
        <TopBar
          chapter={paperTitle}
          score={completedCount}
          total={questions.length}
          reviewCount={reviewCandidateIndices.length}
          reviewMode={reviewMode}
          onToggleReview={toggleReviewMode}
          onReset={resetQuiz}
          documentReady={Boolean(documentId)}
          rightMode={rightMode}
          translationStatus={documentTranslationStatus}
          onToggleJapanese={() => setRightMode((mode) => (mode === "study" ? "japanese" : "study"))}
        />

        <ResizablePanelGroup direction="horizontal" className="min-h-0 flex-1">
          <ResizablePanel
            defaultSize={48}
            minSize={34}
            maxSize={64}
            className="min-w-0"
          >
            <PdfPanel
              current={current}
              documentId={documentId}
              filename={filename}
              pageCount={pageCount}
              uploadState={uploadState}
              uploadError={uploadError}
              onFileSelected={loadPdf}
              onBatchFilesSelected={(files) => void startLayoutBatch(files)}
              batchActive={Boolean(layoutBatchStatus) || batchUploadProgress.active || Boolean(batchUploadProgress.error)}
              batchRunning={batchUploadProgress.active || layoutBatchStatus?.status === "queued" || layoutBatchStatus?.status === "running"}
              onShowBatch={() => setBatchPanelOpen(true)}
              requestedPage={rightMode === "japanese" ? readerPageRequest : null}
              onViewPageChange={setReaderViewPage}
            />
          </ResizablePanel>

          <ResizableHandle
            className={cn(
              "relative w-px bg-white/[0.05] transition-colors duration-200",
              "data-[resize-handle-state=hover]:bg-indigo-500/25",
              "data-[resize-handle-state=drag]:bg-indigo-500/45",
              "after:absolute after:left-1/2 after:top-1/2 after:h-8 after:w-1",
              "after:-translate-x-1/2 after:-translate-y-1/2",
              "after:rounded-full after:bg-zinc-800 after:transition-colors after:duration-200"
            )}
          />

          <ResizablePanel
            defaultSize={52}
            minSize={36}
            maxSize={66}
            className="min-w-0"
          >
            {rightMode === "study" ? (
              <QuizPanel
                current={current}
                currentIndex={navigationPosition}
                total={navigationTotal}
                progress={progress}
                reviewMode={reviewMode}
                answer={answer}
                setAnswer={updateAnswer}
                status={status}
                submitAnswer={submitAnswer}
                goNext={goNext}
                goPrevious={goPrevious}
                isLastQuestion={isLastQuestion}
                score={completedCount}
                evaluation={evaluation}
                attempts={currentAttempts}
                onRetry={startRevision}
                reportOpen={reportOpen}
                setReportOpen={setReportOpen}
                reportText={reportText}
                setReportText={setReportText}
                reportSent={reportSent}
                submitReport={submitReport}
                uploadState={uploadState}
              />
            ) : (
              <JapaneseReaderPanel
                documentId={documentId}
                pageCount={pageCount}
                currentPage={readerViewPage}
                viewMode={japaneseViewMode}
                onViewModeChange={setJapaneseViewMode}
                status={documentTranslationStatus}
                result={documentTranslation}
                layoutStatus={layoutTranslationStatus}
                layoutProductionStatus={layoutProductionStatus}
                onGenerate={() => void startDocumentTranslation(false)}
                onRegenerate={() => void startDocumentTranslation(true)}
                onGenerateLayout={() => void startLayoutTranslation(false)}
                onRegenerateLayout={() => void startLayoutTranslation(true)}
                onRunLayoutPreflight={() => void startLayoutPreflight(true)}
                onRunLayoutProduction={() => void startLayoutProduction(false)}
                onRerunLayoutProduction={() => void startLayoutProduction(true)}
                onOpenPage={(page) => {
                  setReaderPageRequest(page)
                  setReaderViewPage(page)
                }}
                onBackToStudy={() => setRightMode("study")}
              />
            )}
          </ResizablePanel>
        </ResizablePanelGroup>

        {batchPanelOpen && (
          <BatchQueuePanel
            status={layoutBatchStatus}
            upload={batchUploadProgress}
            onClose={() => {
              setBatchPanelOpen(false)
              if (layoutBatchStatus && ["completed", "completed_with_errors", "failed"].includes(layoutBatchStatus.status)) {
                try { window.localStorage.removeItem("paper-translator:last-layout-batch") } catch {}
              }
            }}
            onOpenOutput={(documentId, stage) => void requestOpenLayoutArtifactFolder(documentId, stage)}
            onOpenQa={(documentId, stage) => openLayoutArtifactFile(documentId, "qa", stage)}
            onOpenPdf={(documentId, stage) => openLayoutArtifactFile(documentId, "pdf", stage)}
          />
        )}
      </div>
    </main>
  )
}

function TopBar({
  chapter,
  score,
  total,
  reviewCount,
  reviewMode,
  onToggleReview,
  onReset,
  documentReady,
  rightMode,
  translationStatus,
  onToggleJapanese,
}: {
  chapter: string
  score: number
  total: number
  reviewCount: number
  reviewMode: boolean
  onToggleReview: () => void
  onReset: () => void
  documentReady: boolean
  rightMode: RightPanelMode
  translationStatus: DocumentTranslationStatus
  onToggleJapanese: () => void
}) {
  return (
    <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-white/[0.06] bg-zinc-900/40 px-5 backdrop-blur-sm">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-indigo-500/20 bg-indigo-500/[0.12]">
            <BookOpen className="h-3.5 w-3.5 text-indigo-400" />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[15px] font-semibold uppercase tracking-[0.12em] text-zinc-200">
              Translate Quiz
            </span>
            <span className="rounded border border-indigo-500/20 bg-indigo-500/[0.08] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-indigo-400">
              Beta
            </span>
          </div>
        </div>

        <div className="h-8 w-px bg-white/[0.07]" />

        <nav className="flex min-w-0 items-center gap-2 text-[14px] text-zinc-500">
          <span className="truncate text-zinc-400">Library</span>
          <ChevronRight className="h-3.5 w-3.5 text-zinc-700" />
          <span className="truncate text-zinc-400">Research Papers</span>
          <ChevronRight className="h-3.5 w-3.5 text-zinc-700" />
          <span className="truncate font-medium text-zinc-200">{chapter}</span>
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-1.5 rounded-md border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-[13px] text-zinc-400 md:flex">
          <Zap className="h-3 w-3 text-amber-400/60" />
          <span className="font-mono text-zinc-200">{score}</span>
          <span className="font-mono text-zinc-700">/ {total}</span>
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleReview}
          disabled={!reviewMode && reviewCount === 0}
          title="85点未満・未訳/誤訳・未達キーポイントを自動で復習対象にします"
          className={cn(
            "h-9 rounded-md border px-3 text-[13px] transition-all duration-150",
            reviewMode
              ? "border-indigo-500/25 bg-indigo-500/[0.10] text-indigo-300 hover:bg-indigo-500/[0.14]"
              : "border-white/[0.06] bg-white/[0.025] text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200",
            !reviewMode && reviewCount === 0 && "opacity-35"
          )}
        >
          <List className="mr-1.5 h-3.5 w-3.5" />
          {reviewMode ? "復習中" : `復習 ${reviewCount}`}
        </Button>

        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleJapanese}
          disabled={!documentReady}
          title="論文本文をOllamaで自動翻訳し、日本語版として読みます"
          className={cn(
            "h-9 rounded-md border px-3 text-[13px] transition-all duration-150",
            rightMode === "japanese"
              ? "border-indigo-500/25 bg-indigo-500/[0.10] text-indigo-300 hover:bg-indigo-500/[0.14]"
              : "border-white/[0.06] bg-white/[0.025] text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200",
            !documentReady && "opacity-35"
          )}
        >
          <Languages className="mr-1.5 h-3.5 w-3.5" />
          {translationStatus.status === "running" || translationStatus.status === "queued"
            ? `日本語版 ${translationStatus.progress}%`
            : rightMode === "japanese"
              ? "学習へ戻る"
              : "日本語版"}
        </Button>

        <div className="hidden h-6 w-px bg-white/[0.07] md:block" />

        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          className="h-9 rounded-md px-3 text-[13px] text-zinc-500 transition-all duration-150 hover:bg-white/[0.04] hover:text-zinc-200"
        >
          <RotateCcw className="mr-1.5 h-3 w-3" />
          Reset
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 rounded-lg text-zinc-500 transition-all duration-150 hover:bg-white/[0.04] hover:text-zinc-200"
        >
          <Keyboard className="h-3.5 w-3.5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 rounded-lg text-zinc-500 transition-all duration-150 hover:bg-white/[0.04] hover:text-zinc-200"
        >
          <Settings className="h-3.5 w-3.5" />
        </Button>

        <button className="flex h-10 items-center gap-2 rounded-full border border-white/[0.06] bg-white/[0.04] pl-1.5 pr-2.5 transition-all duration-150 hover:bg-white/[0.06]">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-800 text-[12px] font-medium text-zinc-300">
            TM
          </span>
          <ChevronDown className="h-3 w-3 text-zinc-600" />
        </button>
      </div>
    </header>
  )
}

function PdfPanel({
  current,
  documentId,
  filename,
  pageCount,
  uploadState,
  uploadError,
  onFileSelected,
  onBatchFilesSelected,
  batchActive,
  batchRunning,
  onShowBatch,
  requestedPage,
  onViewPageChange,
}: {
  current: QuizItem | null
  documentId: string | null
  filename: string | null
  pageCount: number
  uploadState: UploadState
  uploadError: string | null
  onFileSelected: (file: File) => void
  onBatchFilesSelected: (files: File[]) => void
  batchActive: boolean
  batchRunning: boolean
  onShowBatch: () => void
  requestedPage: number | null
  onViewPageChange: (page: number) => void
}) {
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const batchFileInputRef = React.useRef<HTMLInputElement>(null)
  const targetPage = current?.pageRef ?? 1
  const [viewPage, setViewPage] = React.useState(targetPage)
  const [zoom, setZoom] = React.useState(1)
  const [imageLoading, setImageLoading] = React.useState(false)

  React.useEffect(() => {
    setViewPage(requestedPage ?? targetPage)
  }, [requestedPage, targetPage])

  React.useEffect(() => {
    setZoom(1)
  }, [documentId])

  React.useEffect(() => {
    onViewPageChange(viewPage)
  }, [viewPage, onViewPageChange])

  const imageSrc = documentId
    ? `${API_BASE_URL}/api/pdfs/${documentId}/pages/${viewPage}?scale=2.2`
    : null
  const pdfFileUrl = documentId ? `${API_BASE_URL}/api/pdfs/${documentId}/file` : null
  const zoomPercent = Math.round(zoom * 100)

  React.useEffect(() => {
    if (imageSrc) setImageLoading(true)
  }, [imageSrc])

  function selectFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) onFileSelected(file)
    event.target.value = ""
  }

  function selectBatchFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    if (files.length) onBatchFilesSelected(files)
    event.target.value = ""
  }

  function changePage(delta: number) {
    setViewPage((page) => Math.min(Math.max(page + delta, 1), Math.max(pageCount, 1)))
  }

  function changeZoom(delta: number) {
    setZoom((value) => Math.min(1.8, Math.max(0.7, Number((value + delta).toFixed(1)))))
  }

  function openPrintView() {
    if (pdfFileUrl) window.open(pdfFileUrl, "_blank", "noopener,noreferrer")
  }

  return (
    <section className="flex h-full min-w-0 flex-col border-r border-white/[0.04] bg-[#080a0f]">
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,.pdf"
        onChange={selectFile}
        className="hidden"
      />
      <input
        ref={batchFileInputRef}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        onChange={selectBatchFiles}
        className="hidden"
      />

      <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.06] bg-zinc-900/45 px-5">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex min-w-0 items-center gap-2.5 rounded-lg px-1 py-1 text-left transition-colors hover:text-white"
          title="PDFを選択"
        >
          <FileText className="h-4 w-4 shrink-0 text-zinc-500" />
          <span className="max-w-[340px] truncate text-[14px] font-medium text-zinc-200">
            {filename ?? "PDFを選択"}
          </span>
          <Badge
            variant="outline"
            className="h-5 border-white/[0.08] bg-transparent px-1.5 text-[10px] font-medium text-zinc-500"
          >
            PDF
          </Badge>
        </button>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => batchRunning ? onShowBatch() : batchFileInputRef.current?.click()}
            className="h-8 rounded-lg px-2.5 text-[11px] text-zinc-500 transition-all duration-150 hover:bg-white/[0.05] hover:text-zinc-200"
            title={batchRunning ? "実行中のバッチキューを表示" : "複数PDFを安全生成キューへ追加"}
          >
            {batchRunning ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin text-indigo-400" /> : <Files className="mr-1.5 h-3.5 w-3.5" />}
            {batchRunning ? "バッチ実行中" : "複数PDF"}
          </Button>
          {batchActive && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onShowBatch}
              className="h-8 rounded-lg px-2 text-[11px] text-indigo-300/80 hover:bg-indigo-500/[0.08] hover:text-indigo-200"
              title="バッチキューを表示"
            >
              <List className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => fileInputRef.current?.click()}
            className="h-8 w-8 rounded-lg text-zinc-600 transition-all duration-150 hover:bg-white/[0.05] hover:text-zinc-300"
            title="別のPDFを開く"
          >
            <MoreVertical className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1 bg-[#080a0f] p-4 xl:p-5">
        <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#11141b] shadow-[0_24px_80px_rgba(0,0,0,0.42)] ring-1 ring-black/20">
          <div className="flex h-[52px] shrink-0 items-center justify-between border-b border-white/[0.07] bg-[#151922]/95 px-3.5">
            <div className="flex min-w-[112px] items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">
              <BookOpen className="h-3.5 w-3.5 text-indigo-400/55" />
              Reader
            </div>

            <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-black/15 p-1">
              <Button
                variant="ghost"
                size="icon"
                disabled={!documentId || viewPage <= 1}
                onClick={() => changePage(-1)}
                className="h-8 w-8 rounded-md text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"
                title="前のページ"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>

              <div className="flex min-w-[92px] items-baseline justify-center gap-1.5 px-2 font-mono">
                <span className="text-[13px] text-zinc-100">{documentId ? viewPage : "—"}</span>
                <span className="text-[11px] text-zinc-700">/</span>
                <span className="text-[12px] text-zinc-500">{pageCount || "—"}</span>
              </div>

              <Button
                variant="ghost"
                size="icon"
                disabled={!documentId || viewPage >= pageCount}
                onClick={() => changePage(1)}
                className="h-8 w-8 rounded-md text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"
                title="次のページ"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex min-w-[112px] items-center justify-end gap-1">
              <Button
                variant="ghost"
                size="icon"
                disabled={!documentId || zoom <= 0.7}
                onClick={() => changeZoom(-0.1)}
                className="h-8 w-8 rounded-md text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"
                title="縮小"
              >
                <Minus className="h-4 w-4" />
              </Button>
              <button
                type="button"
                disabled={!documentId}
                onClick={() => setZoom(1)}
                className="min-w-[52px] rounded-md px-1.5 py-1 font-mono text-[11px] text-zinc-400 transition-colors hover:bg-white/[0.05] hover:text-zinc-100 disabled:text-zinc-800"
                title="幅に合わせる"
              >
                {zoomPercent}%
              </button>
              <Button
                variant="ghost"
                size="icon"
                disabled={!documentId || zoom >= 1.8}
                onClick={() => changeZoom(0.1)}
                className="h-8 w-8 rounded-md text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"
                title="拡大"
              >
                <Plus className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                disabled={!documentId}
                onClick={() => setZoom(1)}
                className="h-8 w-8 rounded-md text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"
                title="ページ幅に合わせる"
              >
                <Maximize2 className="h-3.5 w-3.5" />
              </Button>
              <div className="mx-1 h-5 w-px bg-white/[0.07]" />
              <Button
                variant="ghost"
                size="icon"
                disabled={!documentId}
                onClick={openPrintView}
                className="h-8 w-8 rounded-md text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"
                title="印刷用にPDFを開く"
              >
                <Printer className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          <div className="relative min-h-0 flex-1 overflow-auto bg-[#0b0e14]">
            {imageSrc ? (
              <div
                className={cn(
                  "flex min-h-full min-w-full items-start px-6 py-6 xl:px-9 xl:py-8",
                  zoom <= 1 ? "justify-center" : "justify-start"
                )}
              >
                <div
                  className="relative shrink-0 transition-[width] duration-150 ease-out"
                  style={{ width: `${zoomPercent}%`, maxWidth: zoom <= 1 ? "860px" : "none" }}
                >
                  <div className="absolute -inset-x-3 -inset-y-2 rounded-[18px] border border-white/[0.055] bg-[#171b24] shadow-[0_28px_75px_rgba(0,0,0,0.5)]" />
                  <div className="absolute -bottom-1 -left-2 top-3 w-2 rounded-l-xl bg-black/30 shadow-[-8px_0_18px_rgba(0,0,0,0.22)]" />
                  <div className="relative overflow-hidden rounded-[5px] bg-white shadow-[0_8px_28px_rgba(0,0,0,0.38)] ring-1 ring-black/20">
                    {imageLoading && (
                      <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/90">
                        <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
                      </div>
                    )}
                    <img
                      key={imageSrc}
                      src={imageSrc}
                      alt={`${filename ?? "PDF"} ${viewPage}ページ`}
                      className="block h-auto w-full select-none bg-white"
                      draggable={false}
                      onLoad={() => setImageLoading(false)}
                      onError={() => setImageLoading(false)}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center p-6">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="group flex max-w-sm flex-col items-center rounded-2xl border border-dashed border-white/[0.09] bg-zinc-900/30 px-10 py-12 text-center transition-all hover:border-indigo-500/30 hover:bg-zinc-900/45"
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-indigo-500/15 bg-indigo-500/[0.08]">
                    <FileText className="h-4 w-4 text-indigo-400/75" />
                  </div>
                  <p className="mt-4 text-[14px] font-medium text-zinc-300">論文PDFを選択</p>
                  <p className="mt-2 text-[12px] leading-relaxed text-zinc-600">
                    本文を抽出し、翻訳問題を自動で作成します
                  </p>
                </button>
              </div>
            )}
          </div>
        </div>

        {uploadState === "uploading" && (
          <div className="absolute inset-4 flex items-center justify-center rounded-2xl bg-zinc-950/70 backdrop-blur-[2px] xl:inset-5">
            <div className="flex items-center gap-2.5 rounded-xl border border-white/[0.08] bg-zinc-900/95 px-4 py-2.5 text-[13px] text-zinc-300 shadow-xl">
              <Loader2 className="h-4 w-4 animate-spin text-indigo-400/80" />
              PDFを解析中…
            </div>
          </div>
        )}

        {uploadState === "error" && uploadError && (
          <div className="absolute bottom-8 left-8 right-8 rounded-xl border border-red-500/[0.16] bg-red-950/95 px-4 py-3 text-[13px] leading-relaxed text-red-300/85 shadow-xl xl:bottom-9 xl:left-9 xl:right-9">
            {uploadError}
          </div>
        )}
      </div>

      <div className="flex h-14 shrink-0 items-center justify-between border-t border-white/[0.06] bg-zinc-900/30 px-5">
        <Button
          variant="ghost"
          size="sm"
          disabled
          className="h-8 rounded-lg px-2 text-[12px] text-zinc-700"
        >
          <Search className="mr-2 h-3.5 w-3.5" />
          検索
        </Button>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled
            className="h-8 rounded-lg border-white/[0.05] bg-zinc-900/40 px-3 text-[12px] text-zinc-700"
          >
            <span className="mr-2 h-2.5 w-2.5 rounded-full bg-indigo-500/30" />
            ハイライト
          </Button>

          <Button
            variant="outline"
            size="sm"
            disabled
            className="h-8 rounded-lg border-white/[0.05] bg-zinc-900/40 px-3 text-[12px] text-zinc-700"
          >
            <List className="mr-2 h-3.5 w-3.5" />
            目次
          </Button>
        </div>
      </div>
    </section>
  )
}

function BatchQueuePanel({
  status,
  upload,
  onClose,
  onOpenOutput,
  onOpenQa,
  onOpenPdf,
}: {
  status: LayoutBatchStatus | null
  upload: BatchUploadProgress
  onClose: () => void
  onOpenOutput: (documentId: string, stage: "auto" | "preflight" | "full") => void
  onOpenQa: (documentId: string, stage: "auto" | "preflight" | "full") => void
  onOpenPdf: (documentId: string, stage: "auto" | "preflight" | "full") => void
}) {
  const terminal = status && ["completed", "completed_with_errors", "failed"].includes(status.status)
  const summary = status
    ? `${status.completed}/${status.total} 完了${status.failed ? ` · ${status.failed} 失敗` : ""}`
    : upload.active
      ? `${upload.uploaded}/${upload.total} PDFを準備中`
      : "バッチを準備できませんでした"

  return (
    <aside className="fixed bottom-5 right-5 z-50 flex max-h-[72vh] w-[430px] max-w-[calc(100vw-40px)] flex-col overflow-hidden rounded-2xl border border-white/[0.10] bg-[#11141b]/98 shadow-[0_28px_90px_rgba(0,0,0,0.58)] backdrop-blur-xl">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Files className="h-4 w-4 text-indigo-400" />
            <p className="text-[13px] font-medium text-zinc-200">安全生成バッチ</p>
          </div>
          <p className="mt-1 text-[11px] text-zinc-600">{summary}</p>
          {(status?.quality_profile || status?.app_build) && (
            <div className="mt-0.5 max-w-[340px] font-mono text-[9px] leading-4 text-zinc-700">
              {status?.app_build && (
                <p className="truncate" title={status.app_build}>build: {status.app_build}{status.historical_build ? " · 旧build" : ""}</p>
              )}
              {status?.quality_profile && (
                <p className="truncate" title={status.quality_profile}>profile: {status.quality_profile}</p>
              )}
            </div>
          )}
          {status?.stale_quality_profile && (
            <p className="mt-1 text-[10px] font-medium text-amber-300/80">旧quality profileの履歴です。現在版の検証結果ではありません。</p>
          )}
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8 text-zinc-600 hover:text-zinc-200">
          <XCircle className="h-4 w-4" />
        </Button>
      </div>

      <div className="h-1 bg-white/[0.04]">
        <div
          className="h-full bg-indigo-500/70 transition-all duration-500"
          style={{ width: `${status?.progress ?? (upload.total ? Math.round((upload.uploaded / upload.total) * 100) : 0)}%` }}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {upload.active && (
          <div className="flex items-center gap-2 rounded-xl border border-indigo-500/[0.12] bg-indigo-500/[0.05] px-3 py-3 text-[12px] text-zinc-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
            PDFを解析してキューを作成しています…
          </div>
        )}

        {upload.error && (
          <div className="mb-2 whitespace-pre-wrap rounded-xl border border-amber-500/[0.14] bg-amber-500/[0.05] px-3 py-2.5 text-[11px] leading-5 text-amber-200/75">
            {upload.error}
          </div>
        )}

        <div className="space-y-2">
          {status?.items.map((item, index) => {
            const running = item.status === "running"
            const completed = item.status === "completed"
            const failed = item.status === "failed"
            const stageLabel = item.cached
              ? "既存PASSを再利用"
              : item.stage === "preflight"
                ? "1ページテスト"
                : item.stage === "full"
                  ? "全文生成 + QA"
                  : completed
                    ? "完了"
                    : failed
                      ? item.failure_stage === "preflight"
                        ? "停止 · 1ページテスト"
                        : item.failure_stage === "full"
                          ? "停止 · 全文QA"
                          : "停止"
                      : "待機"
            return (
              <div key={`${item.document_id}-${index}`} className="rounded-xl border border-white/[0.06] bg-black/15 px-3 py-3">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">
                    {running ? (
                      <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
                    ) : completed ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400/80" />
                    ) : failed ? (
                      <XCircle className="h-4 w-4 text-red-400/80" />
                    ) : (
                      <span className="flex h-4 w-4 items-center justify-center rounded-full border border-white/[0.12] font-mono text-[9px] text-zinc-600">{index + 1}</span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-medium text-zinc-300">{item.filename}</p>
                    <div className="mt-1 flex items-center justify-between gap-3 text-[10px] text-zinc-600">
                      <span>{stageLabel}</span>
                      <span className="font-mono">{item.progress}%</span>
                    </div>
                    {(running || item.status === "queued") && (
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.05]">
                        <div className="h-full bg-indigo-500/55 transition-all duration-500" style={{ width: `${Math.max(item.progress, running ? 2 : 0)}%` }} />
                      </div>
                    )}
                    {item.error && <p className="mt-2 text-[10px] leading-4 text-red-300/75">{item.error}</p>}
                  </div>
                  {(completed || failed) && (
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onOpenOutput(item.document_id, item.artifact_stage === "preflight" ? "preflight" : item.artifact_stage === "full" ? "full" : "auto")}
                        className="h-7 px-2 text-[10px] text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200"
                        title={failed ? "失敗時のQA・確認PDF・ログが残る証拠フォルダを開く" : "翻訳結果の保存先を開く"}
                      >
                        <FolderOpen className="mr-1 h-3 w-3" />
                        {failed ? "証拠" : "保存先"}
                      </Button>
                      <div className="flex items-center gap-1">
                        {item.qa_available && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onOpenQa(item.document_id, item.qa_stage ?? "auto")}
                            className="h-6 px-1.5 text-[9px] text-zinc-600 hover:bg-white/[0.05] hover:text-zinc-200"
                            title="この項目で実際に使われたQA JSONを開く"
                          >
                            <Download className="mr-1 h-2.5 w-2.5" />
                            QA
                          </Button>
                        )}
                        {item.pdf_available && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onOpenPdf(item.document_id, item.pdf_stage ?? "auto")}
                            className="h-6 px-1.5 text-[9px] text-zinc-600 hover:bg-white/[0.05] hover:text-zinc-200"
                            title="失敗時を含む確認用PDFを開く"
                          >
                            <FileText className="mr-1 h-2.5 w-2.5" />
                            PDF
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {status && (
        <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-3 text-[10px] text-zinc-600">
          <span>{terminal ? "処理終了" : "順番に1件ずつ処理します"}</span>
          <span className="font-mono">{status.progress}%</span>
        </div>
      )}
    </aside>
  )
}

function JapaneseReaderPanel({
  documentId,
  pageCount,
  currentPage,
  viewMode,
  onViewModeChange,
  status,
  result,
  layoutStatus,
  layoutProductionStatus,
  onGenerate,
  onRegenerate,
  onGenerateLayout,
  onRegenerateLayout,
  onRunLayoutPreflight,
  onRunLayoutProduction,
  onRerunLayoutProduction,
  onOpenPage,
  onBackToStudy,
}: {
  documentId: string | null
  pageCount: number
  currentPage: number
  viewMode: JapaneseViewMode
  onViewModeChange: (mode: JapaneseViewMode) => void
  status: DocumentTranslationStatus
  result: DocumentTranslationResult | null
  layoutStatus: LayoutTranslationStatus
  layoutProductionStatus: LayoutProductionStatus
  onGenerate: () => void
  onRegenerate: () => void
  onGenerateLayout: () => void
  onRegenerateLayout: () => void
  onRunLayoutPreflight: () => void
  onRunLayoutProduction: () => void
  onRerunLayoutProduction: () => void
  onOpenPage: (page: number) => void
  onBackToStudy: () => void
}) {
  const pages = React.useMemo(() => {
    const grouped = new Map<number, TranslatedSegment[]>()
    for (const segment of result?.segments ?? []) {
      const current = grouped.get(segment.pageRef) ?? []
      current.push(segment)
      grouped.set(segment.pageRef, current)
    }
    return [...grouped.entries()].sort((a, b) => a[0] - b[0])
  }, [result])

  const running = status.status === "queued" || status.status === "running"
  const completed = status.status === "completed" && Boolean(result)
  const readingPdfUrl = documentId
    ? `${API_BASE_URL}/api/pdfs/${documentId}/translation/file`
    : null
  const layoutMonoUrl = documentId
    ? `${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/mono`
    : null
  const layoutDualUrl = documentId
    ? `${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/dual`
    : null
  const [folderOpenState, setFolderOpenState] = React.useState<"idle" | "opening" | "opened" | "error">("idle")

  async function handleOpenOutputFolder() {
    if (!documentId || folderOpenState === "opening") return
    setFolderOpenState("opening")
    try {
      await requestOpenLayoutOutputFolder(documentId)
      setFolderOpenState("opened")
      window.setTimeout(() => setFolderOpenState("idle"), 2200)
    } catch (error) {
      console.error("Open output folder error:", error)
      setFolderOpenState("error")
      window.setTimeout(() => setFolderOpenState("idle"), 3000)
    }
  }

  return (
    <section className="flex h-full min-w-0 flex-col bg-zinc-950">
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.06] bg-zinc-900/30 px-5">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <Languages className="h-4 w-4 text-indigo-400/75" />
            <div>
              <p className="text-[13px] font-medium text-zinc-200">日本語版</p>
              <p className="mt-0.5 text-[10px] text-zinc-600">Paper body / layout-preserved PDF</p>
            </div>
          </div>
          <div className="hidden items-center rounded-lg border border-white/[0.06] bg-black/15 p-1 lg:flex">
            <button
              type="button"
              onClick={() => onViewModeChange("reading")}
              className={cn(
                "rounded-md px-3 py-1.5 text-[11px] transition-colors",
                viewMode === "reading"
                  ? "bg-white/[0.07] text-zinc-200"
                  : "text-zinc-600 hover:text-zinc-300"
              )}
            >
              本文訳
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange("layout")}
              className={cn(
                "rounded-md px-3 py-1.5 text-[11px] transition-colors",
                viewMode === "layout"
                  ? "bg-white/[0.07] text-zinc-200"
                  : "text-zinc-600 hover:text-zinc-300"
              )}
            >
              レイアウト翻訳
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {viewMode === "reading" && completed && readingPdfUrl && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => window.open(readingPdfUrl, "_blank", "noopener,noreferrer")}
              className="h-9 rounded-md border border-white/[0.06] bg-white/[0.025] px-3 text-[12px] text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
            >
              <Download className="mr-1.5 h-3.5 w-3.5" />
              読書用PDF
            </Button>
          )}
          {viewMode === "layout" && layoutStatus.mono_ready && layoutMonoUrl && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => window.open(layoutMonoUrl, "_blank", "noopener,noreferrer")}
              className="h-9 rounded-md border border-white/[0.06] bg-white/[0.025] px-3 text-[12px] text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
            >
              <Download className="mr-1.5 h-3.5 w-3.5" />
              日本語PDF
            </Button>
          )}
          {viewMode === "layout" && layoutStatus.dual_ready && layoutDualUrl && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => window.open(layoutDualUrl, "_blank", "noopener,noreferrer")}
              className="h-9 rounded-md border border-white/[0.06] bg-white/[0.025] px-3 text-[12px] text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-100"
            >
              英日対訳PDF
            </Button>
          )}
          {viewMode === "layout" && documentId && (layoutStatus.mono_ready || layoutStatus.dual_ready || layoutStatus.preflight?.mono_ready || layoutStatus.qa) && (
            <Button
              variant="ghost"
              size="sm"
              disabled={folderOpenState === "opening"}
              onClick={() => void handleOpenOutputFolder()}
              title={layoutStatus.output_dir || "Open the saved output folder"}
              className={cn(
                "h-9 rounded-md border border-white/[0.06] bg-white/[0.025] px-3 text-[12px] hover:bg-white/[0.05] hover:text-zinc-100",
                folderOpenState === "error" ? "text-red-300" : folderOpenState === "opened" ? "text-emerald-300" : "text-zinc-400"
              )}
            >
              {folderOpenState === "opening" ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="mr-1.5 h-3.5 w-3.5" />}
              {folderOpenState === "opened"
                ? "\u958b\u304d\u307e\u3057\u305f"
                : folderOpenState === "error"
                  ? "\u958b\u3051\u307e\u305b\u3093"
                  : "\u4fdd\u5b58\u5148\u3092\u958b\u304f"}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onBackToStudy}
            className="h-9 rounded-md px-3 text-[12px] text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-200"
          >
            学習へ戻る
          </Button>
        </div>
      </div>

      <div className="flex lg:hidden border-b border-white/[0.05] bg-zinc-900/20 px-4 py-2">
        <button
          onClick={() => onViewModeChange("reading")}
          className={cn("flex-1 rounded-md py-2 text-[11px]", viewMode === "reading" ? "bg-white/[0.06] text-zinc-200" : "text-zinc-600")}
        >本文訳</button>
        <button
          onClick={() => onViewModeChange("layout")}
          className={cn("flex-1 rounded-md py-2 text-[11px]", viewMode === "layout" ? "bg-white/[0.06] text-zinc-200" : "text-zinc-600")}
        >レイアウト翻訳</button>
      </div>

      {viewMode === "layout" ? (
        <LayoutTranslationPanel
          documentId={documentId}
          pageCount={pageCount}
          currentPage={currentPage}
          status={layoutStatus}
          productionStatus={layoutProductionStatus}
          onGenerate={onGenerateLayout}
          onRegenerate={onRegenerateLayout}
          onRunPreflight={onRunLayoutPreflight}
          onRunProduction={onRunLayoutProduction}
          onRerunProduction={onRerunLayoutProduction}
          onOpenPage={onOpenPage}
        />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 xl:px-8 xl:py-7 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/[0.08]">
          {!documentId ? (
            <div className="flex min-h-[420px] items-center justify-center text-center">
              <div>
                <BookOpen className="mx-auto h-5 w-5 text-zinc-700" />
                <p className="mt-4 text-[13px] text-zinc-400">先に論文PDFを読み込んでください</p>
              </div>
            </div>
          ) : running ? (
            <div className="mx-auto flex min-h-[420px] max-w-xl items-center">
              <div className="w-full rounded-2xl border border-white/[0.07] bg-zinc-900/35 p-6">
                <div className="flex items-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
                  <div>
                    <p className="text-[15px] font-medium text-zinc-200">論文本文を翻訳しています</p>
                    <p className="mt-1 text-[12px] text-zinc-600">Ollamaを使うため、論文の長さによって数分かかります</p>
                  </div>
                </div>
                <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full bg-indigo-500/70 transition-all duration-500" style={{ width: `${Math.max(status.progress, 2)}%` }} />
                </div>
                <div className="mt-3 flex items-center justify-between font-mono text-[11px] text-zinc-600">
                  <span>{status.translated_segments} / {status.total_segments || "—"} segments</span>
                  <span>{status.progress}%</span>
                </div>
              </div>
            </div>
          ) : status.status === "failed" ? (
            <div className="mx-auto flex min-h-[420px] max-w-xl items-center">
              <div className="w-full rounded-2xl border border-red-500/[0.12] bg-red-950/10 p-6">
                <AlertTriangle className="h-5 w-5 text-red-400" />
                <p className="mt-4 text-[15px] font-medium text-zinc-200">全文翻訳に失敗しました</p>
                <p className="mt-2 whitespace-pre-wrap text-[12px] leading-6 text-zinc-500">{status.error}</p>
                <Button onClick={onRegenerate} className="mt-5 h-9 bg-indigo-600 px-4 text-[12px] hover:bg-indigo-500">再試行</Button>
              </div>
            </div>
          ) : completed ? (
            <div className="mx-auto max-w-4xl space-y-6 pb-20">
              <div className="rounded-2xl border border-white/[0.07] bg-zinc-900/35 px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[12px] uppercase tracking-[0.16em] text-zinc-600">Japanese Reading Copy</p>
                    <p className="mt-2 text-[17px] font-medium leading-7 text-zinc-200">{result?.title}</p>
                    <p className="mt-2 text-[11px] text-zinc-600">Model: {result?.model}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={onRegenerate} className="h-8 rounded-md border border-white/[0.06] px-3 text-[11px] text-zinc-600 hover:bg-white/[0.04] hover:text-zinc-300">
                    <RotateCcw className="mr-1.5 h-3 w-3" />再生成
                  </Button>
                </div>
                <p className="mt-3 text-[11px] leading-5 text-zinc-600">本文を読みやすい日本語へ変換した補助版です。元の図表・数式配置を保った版は「レイアウト翻訳」で生成できます。</p>
              </div>

              {pages.map(([pageRef, segments]) => (
                <section key={pageRef} className="rounded-2xl border border-white/[0.06] bg-zinc-900/28">
                  <button type="button" onClick={() => onOpenPage(pageRef)} className="flex w-full items-center justify-between border-b border-white/[0.05] px-5 py-3 text-left hover:bg-white/[0.02]">
                    <span className="font-mono text-[11px] text-indigo-400/75">原文 p.{pageRef}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-zinc-700" />
                  </button>
                  <div className="divide-y divide-white/[0.045]">
                    {segments.map((segment) => (
                      <article key={segment.id} className="px-5 py-5">
                        <p className="text-[16px] leading-[1.95] text-zinc-200">{segment.translation}</p>
                        <p className="mt-3 text-[11px] leading-[1.75] text-zinc-600">{segment.sourceText}</p>
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <div className="mx-auto flex min-h-[420px] max-w-xl items-center">
              <div className="w-full rounded-2xl border border-white/[0.07] bg-zinc-900/35 p-6">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-indigo-500/20 bg-indigo-500/[0.10]"><Sparkles className="h-4 w-4 text-indigo-400" /></div>
                <p className="mt-5 text-[17px] font-medium text-zinc-100">この論文の日本語本文版を生成</p>
                <p className="mt-2 text-[13px] leading-6 text-zinc-500">既に抽出している論文本文をQwenでまとめて翻訳します。翻訳プロンプトと専門用語集はレイアウト翻訳と共通化しています。</p>
                <Button onClick={onGenerate} className="mt-6 h-10 bg-indigo-600 px-5 text-[13px] hover:bg-indigo-500"><Languages className="mr-2 h-4 w-4" />全文を日本語化</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function LayoutTranslationPanel({
  documentId,
  pageCount,
  currentPage,
  status,
  productionStatus,
  onGenerate,
  onRegenerate,
  onRunPreflight,
  onRunProduction,
  onRerunProduction,
  onOpenPage,
}: {
  documentId: string | null
  pageCount: number
  currentPage: number
  status: LayoutTranslationStatus
  productionStatus: LayoutProductionStatus
  onGenerate: () => void
  onRegenerate: () => void
  onRunPreflight: () => void
  onRunProduction: () => void
  onRerunProduction: () => void
  onOpenPage: (page: number) => void
}) {
  const [zoom, setZoom] = React.useState(1)
  const [loading, setLoading] = React.useState(false)
  const [showQa, setShowQa] = React.useState(false)
  const ready = status.status === "completed" && status.mono_ready
  const running = status.status === "queued" || status.status === "running"
  const productionRunning = productionStatus.status === "queued" || productionStatus.status === "running"
  const productionFailed = productionStatus.status === "failed"
  const preflight = status.preflight
  const preflightRunning = preflight?.status === "queued" || preflight?.status === "running"
  const preflightPassed = preflight?.status === "completed" && preflight?.qa?.status === "pass"
  const preflightFailed = preflight?.status === "failed" || preflight?.qa?.status === "fail"
  const page = Math.min(Math.max(currentPage || 1, 1), Math.max(pageCount, 1))
  const imageSrc = documentId && ready
    ? `${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/pages/${page}?scale=2.2`
    : null
  const preflightPdfUrl = documentId && preflight?.mono_ready
    ? `${API_BASE_URL}/api/pdfs/${documentId}/layout-translation/preflight/mono`
    : null
  const zoomPercent = Math.round(zoom * 100)

  React.useEffect(() => {
    if (imageSrc) setLoading(true)
  }, [imageSrc])

  if (!documentId) {
    return <div className="flex min-h-0 flex-1 items-center justify-center text-[13px] text-zinc-500">先に論文PDFを読み込んでください</div>
  }

  if (productionRunning) {
    const stageIsPreflight = productionStatus.stage === "queued" || productionStatus.stage === "preflight"
    const stageTitle = stageIsPreflight ? "1ページテストで安全確認しています" : "品質ゲート通過後、全文を生成しています"
    const stageDetail = stageIsPreflight
      ? "このテストがPASSした場合だけ全文生成へ自動で進みます。"
      : `PDFMathTranslate-next + ${status.model || "Ollama"}`
    const activeProxy = stageIsPreflight ? productionStatus.preflight?.proxy_requests : productionStatus.full?.proxy_requests
    const activeGuard = stageIsPreflight ? productionStatus.preflight?.guard_events : productionStatus.full?.guard_events
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-8">
        <div className="w-full max-w-xl rounded-2xl border border-indigo-500/[0.12] bg-zinc-900/35 p-6">
          <div className="flex items-center gap-3"><Loader2 className="h-5 w-5 animate-spin text-indigo-400" /><div><p className="text-[15px] font-medium text-zinc-200">{stageTitle}</p><p className="mt-1 text-[12px] text-zinc-600">{stageDetail}</p></div></div>
          <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-indigo-500/70 transition-all duration-500" style={{ width: `${Math.max(productionStatus.progress, 2)}%` }} /></div>
          <div className="mt-3 flex justify-between font-mono text-[11px] text-zinc-600"><span>{stageIsPreflight ? "preflight → full" : "full translation"}</span><span>{productionStatus.progress}%</span></div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
            <div className={cn("rounded-lg border px-3 py-2", stageIsPreflight ? "border-indigo-500/20 bg-indigo-500/[0.06] text-indigo-300/80" : "border-emerald-500/15 bg-emerald-500/[0.04] text-emerald-300/75")}>1. 1ページテスト {stageIsPreflight ? "実行中" : "PASS"}</div>
            <div className={cn("rounded-lg border px-3 py-2", stageIsPreflight ? "border-white/[0.05] bg-black/10 text-zinc-700" : "border-indigo-500/20 bg-indigo-500/[0.06] text-indigo-300/80")}>2. 全文生成 {stageIsPreflight ? "待機" : "実行中"}</div>
          </div>
          {(activeProxy !== undefined || activeGuard !== undefined) && (
            <div className="mt-3 rounded-lg border border-white/[0.05] bg-black/15 px-3 py-2 text-[11px] leading-5 text-zinc-500">
              <span>翻訳Proxy {activeProxy ?? 0}件</span><span className="mx-2 text-zinc-700">/</span><span>Guard {activeGuard ?? 0}件</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (running) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-8">
        <div className="w-full max-w-xl rounded-2xl border border-white/[0.07] bg-zinc-900/35 p-6">
          <div className="flex items-center gap-3"><Loader2 className="h-5 w-5 animate-spin text-indigo-400" /><div><p className="text-[15px] font-medium text-zinc-200">元レイアウトを保って翻訳しています</p><p className="mt-1 text-[12px] text-zinc-600">PDFMathTranslate-next + {status.model || "Ollama"}</p></div></div>
          <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-indigo-500/70 transition-all duration-500" style={{ width: `${Math.max(status.progress, 2)}%` }} /></div>
          <div className="mt-3 flex justify-between font-mono text-[11px] text-zinc-600"><span>layout translation</span><span>{status.progress}%</span></div>
          <div className="mt-3 rounded-lg border border-white/[0.05] bg-black/15 px-3 py-2 text-[11px] leading-5 text-zinc-500">
            <span>翻訳Proxy {status.proxy_requests ?? 0}件</span>
            <span className="mx-2 text-zinc-700">/</span>
            <span>Guard {status.guard_events ?? 0}件</span>
            <p className="mt-1 text-zinc-600">ローカルLLMの1リクエスト処理中は進捗%が数分止まることがあります。上の件数が増えていれば処理は継続中です。</p>
          </div>
        </div>
      </div>
    )
  }

  if (productionFailed && status.status !== "completed") {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-8">
        <div className="w-full max-w-xl rounded-2xl border border-red-500/[0.12] bg-red-950/10 p-6">
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <p className="mt-4 text-[15px] font-medium text-zinc-200">安全な一括生成を停止しました</p>
          <p className="mt-2 whitespace-pre-wrap text-[12px] leading-6 text-zinc-500">{productionStatus.error}</p>
          <p className="mt-3 text-[11px] leading-5 text-zinc-600">{productionStatus.stage === "preflight" ? "1ページテストが通らなかったため、全文生成は開始していません。" : "全文生成または最終QAで停止しました。"}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="outline" disabled={!status.worker_ready} onClick={onRerunProduction} className="h-9 border-white/[0.08] bg-white/[0.025] px-4 text-[12px] text-zinc-300 hover:bg-white/[0.05]"><RotateCcw className="mr-2 h-4 w-4" />最初から再実行</Button>
            <Button variant="ghost" disabled={preflightRunning || !status.worker_ready} onClick={onRunPreflight} className="h-9 border border-white/[0.06] px-4 text-[12px] text-zinc-500 hover:bg-white/[0.04]">1ページテストだけ</Button>
          </div>
        </div>
      </div>
    )
  }

  if (status.status === "failed") {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-8">
        <div className="w-full max-w-xl rounded-2xl border border-red-500/[0.12] bg-red-950/10 p-6">
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <p className="mt-4 text-[15px] font-medium text-zinc-200">レイアウト翻訳に失敗しました</p>
          <p className="mt-2 whitespace-pre-wrap text-[12px] leading-6 text-zinc-500">{status.error}</p>
          {!status.worker_ready && <p className="mt-4 rounded-lg border border-amber-500/[0.12] bg-amber-500/[0.05] px-3 py-2 text-[11px] leading-5 text-amber-300/70">初回のみ、プロジェクト直下の setup_layout_translation.ps1 を実行してください。</p>}

          <div className="mt-4 rounded-xl border border-white/[0.06] bg-black/15 px-4 py-3 text-[11px] leading-5 text-zinc-500">
            {preflightRunning ? (
              <p className="flex items-center gap-2 text-indigo-300/80"><Loader2 className="h-3 w-3 animate-spin" />1ページテスト実行中 {preflight?.progress ?? 0}%</p>
            ) : preflightPassed ? (
              <p className="text-emerald-300/80">1ページテスト: PASS / 日本語化率 {preflight?.qa?.japanese_percent?.toFixed(1) ?? "—"}%</p>
            ) : preflightFailed ? (
              <p className="text-red-300/85">1ページテスト: FAIL — {preflight?.error || preflight?.qa?.problems?.[0]?.message || "出力を確認してください"}</p>
            ) : (
              <p>全文生成が失敗していても、Abstractページの1ページテストは独立して再実行できます。</p>
            )}
            {preflightPdfUrl && <button type="button" onClick={() => window.open(preflightPdfUrl, "_blank", "noopener,noreferrer")} className="mt-1 text-indigo-300/70 hover:text-indigo-200">テストPDFを開く</button>}
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="outline" disabled={preflightRunning || !status.worker_ready} onClick={onRunPreflight} className="h-9 border-white/[0.08] bg-white/[0.025] px-4 text-[12px] text-zinc-300 hover:bg-white/[0.05]">
              {preflightRunning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
              {preflightRunning ? "1ページテスト実行中" : "1ページテスト"}
            </Button>
            <Button disabled={!status.worker_ready} onClick={onRerunProduction} className="h-9 bg-indigo-600 px-4 text-[12px] hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-35"><RotateCcw className="mr-2 h-4 w-4" />安全に再実行</Button>
            <Button variant="ghost" disabled={!preflightPassed} onClick={onRegenerate} className="h-9 border border-white/[0.06] px-4 text-[11px] text-zinc-500 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-30">全文を再生成</Button>
          </div>
        </div>
      </div>
    )
  }

  if (!ready) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-8">
        <div className="w-full max-w-xl rounded-2xl border border-white/[0.07] bg-zinc-900/35 p-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-indigo-500/20 bg-indigo-500/[0.10]"><FileText className="h-4 w-4 text-indigo-400" /></div>
          <p className="mt-5 text-[17px] font-medium text-zinc-100">元PDFの配置を保った日本語版を生成</p>
          <p className="mt-2 text-[13px] leading-6 text-zinc-500">図・数式・段組・ページ構成をできるだけ維持した mono PDF と、英日対訳 dual PDF を生成します。</p>
          <div className="mt-4 rounded-xl border border-white/[0.06] bg-black/15 px-4 py-3 text-[11px] leading-5 text-zinc-500">
            <p>翻訳モデル: <span className="text-zinc-300">{status.model || "バックエンド設定"}</span></p>
            <p className="mt-1">翻訳品質: 専門用語集 + 厳格プロンプト + 生成後QA</p>
            {status.cache_stale && (
              <p className="mt-2 rounded-lg border border-amber-500/[0.14] bg-amber-500/[0.05] px-3 py-2 text-amber-300/80">翻訳エンジンが更新されています。旧キャッシュは再利用せず、1ページテストから再検証します。</p>
            )}
            {!status.worker_ready && <p className="mt-2 text-amber-300/75">初回セットアップが必要です: setup_layout_translation.ps1</p>}
            <div className="mt-3 border-t border-white/[0.05] pt-3">
              {preflightRunning ? (
                <p className="flex items-center gap-2 text-indigo-300/80"><Loader2 className="h-3 w-3 animate-spin" />1ページテスト実行中 {preflight?.progress ?? 0}%</p>
              ) : preflightPassed ? (
                <p className="text-emerald-300/80">1ページテスト: PASS / 日本語化率 {preflight?.qa?.japanese_percent?.toFixed(1) ?? "—"}%</p>
              ) : preflightFailed ? (
                <p className="text-red-300/85">1ページテスト: FAIL — {preflight?.error || preflight?.qa?.problems?.[0]?.message || "出力を確認してください"}</p>
              ) : (
                <p>Phase 14では、全文生成前にAbstractページだけで翻訳経路を検証します。</p>
              )}
              {preflightPdfUrl && <button type="button" onClick={() => window.open(preflightPdfUrl, "_blank", "noopener,noreferrer")} className="mt-1 text-indigo-300/70 hover:text-indigo-200">テストPDFを開く</button>}
            </div>
          </div>
          <div className="mt-6">
            <Button disabled={!status.worker_ready || preflightRunning || running} onClick={onRunProduction} className="h-11 w-full bg-indigo-600 px-5 text-[13px] hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-35"><Zap className="mr-2 h-4 w-4" />安全に一括生成</Button>
            <p className="mt-2 text-center text-[10px] leading-5 text-zinc-600">1ページテスト → PASS確認 → 全文生成 → 最終QAまで自動で進みます</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2 border-t border-white/[0.05] pt-4">
              <Button variant="outline" disabled={preflightRunning || !status.worker_ready} onClick={onRunPreflight} className="h-9 border-white/[0.08] bg-white/[0.025] px-4 text-[11px] text-zinc-400 hover:bg-white/[0.05]"><Sparkles className="mr-2 h-3.5 w-3.5" />1ページテストだけ</Button>
              <Button variant="ghost" disabled={!preflightPassed} onClick={onGenerate} className="h-9 border border-white/[0.06] px-4 text-[11px] text-zinc-500 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-35"><Languages className="mr-2 h-3.5 w-3.5" />全文だけ生成</Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[#080a0f]">
      <div className="flex h-[52px] shrink-0 items-center justify-between border-b border-white/[0.06] bg-[#151922]/95 px-3.5">
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-600"><Languages className="h-3.5 w-3.5 text-indigo-400/55" />Translated</div>
        <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-black/15 p-1">
          <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => onOpenPage(page - 1)} className="h-8 w-8 rounded-md text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"><ChevronLeft className="h-4 w-4" /></Button>
          <div className="flex min-w-[92px] items-baseline justify-center gap-1.5 px-2 font-mono"><span className="text-[13px] text-zinc-100">{page}</span><span className="text-[11px] text-zinc-700">/</span><span className="text-[12px] text-zinc-500">{pageCount}</span></div>
          <Button variant="ghost" size="icon" disabled={page >= pageCount} onClick={() => onOpenPage(page + 1)} className="h-8 w-8 rounded-md text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-100 disabled:text-zinc-800"><ChevronRight className="h-4 w-4" /></Button>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" disabled={zoom <= 0.7} onClick={() => setZoom((v) => Math.max(0.7, Number((v - 0.1).toFixed(1))))} className="h-8 w-8 rounded-md text-zinc-500 hover:bg-white/[0.06]"><Minus className="h-4 w-4" /></Button>
          <button onClick={() => setZoom(1)} className="min-w-[50px] rounded-md px-1.5 py-1 font-mono text-[11px] text-zinc-400 hover:bg-white/[0.05]">{zoomPercent}%</button>
          <Button variant="ghost" size="icon" disabled={zoom >= 1.8} onClick={() => setZoom((v) => Math.min(1.8, Number((v + 0.1).toFixed(1))))} className="h-8 w-8 rounded-md text-zinc-500 hover:bg-white/[0.06]"><Plus className="h-4 w-4" /></Button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1 overflow-auto bg-[#0b0e14]">
        {imageSrc && (
          <div className={cn("flex min-h-full min-w-full items-start px-6 py-6 xl:px-9 xl:py-8", zoom <= 1 ? "justify-center" : "justify-start")}>
            <div className="relative shrink-0 transition-[width] duration-150 ease-out" style={{ width: `${zoomPercent}%`, maxWidth: zoom <= 1 ? "860px" : "none" }}>
              <div className="absolute -inset-x-3 -inset-y-2 rounded-[18px] border border-white/[0.055] bg-[#171b24] shadow-[0_28px_75px_rgba(0,0,0,0.5)]" />
              <div className="relative overflow-hidden rounded-[5px] bg-white shadow-[0_8px_28px_rgba(0,0,0,0.38)] ring-1 ring-black/20">
                {loading && <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/90"><Loader2 className="h-5 w-5 animate-spin text-zinc-500" /></div>}
                <img key={imageSrc} src={imageSrc} alt={`翻訳PDF ${page}ページ`} className="block h-auto w-full select-none bg-white" draggable={false} onLoad={() => setLoading(false)} onError={() => setLoading(false)} />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-white/[0.06] bg-zinc-900/30">
        {showQa && status.qa?.warnings?.length ? (
          <div className="max-h-48 overflow-y-auto border-b border-white/[0.05] px-4 py-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] font-medium text-zinc-300">翻訳QAの確認候補</p>
              <span className="font-mono text-[10px] text-zinc-600">{status.qa.warning_count}件</span>
            </div>
            <div className="space-y-2">
              {status.qa.warnings.slice(0, 12).map((warning, index) => (
                <div key={`${warning.code}-${warning.page ?? "all"}-${index}`} className="rounded-lg border border-white/[0.055] bg-black/15 px-3 py-2">
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className={cn("rounded px-1.5 py-0.5 font-mono uppercase", warning.severity === "critical" ? "bg-red-500/20 text-red-200" : warning.severity === "high" ? "bg-orange-500/10 text-orange-300/80" : "bg-amber-500/10 text-amber-300/80")}>{warning.severity}</span>
                    {warning.page && <button type="button" onClick={() => onOpenPage(warning.page!)} className="text-indigo-300/75 hover:text-indigo-200">p.{warning.page}</button>}
                    <span className="font-mono text-zinc-700">{warning.code}</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-5 text-zinc-400">{warning.message}</p>
                  {warning.suggestion && <p className="mt-1 text-[10px] leading-5 text-zinc-600">推奨: {warning.suggestion}</p>}
                </div>
              ))}
            </div>
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <button type="button" onClick={() => status.qa?.warnings?.length && setShowQa((value) => !value)} className="min-w-0 text-left">
            <div className="flex items-center gap-2 text-[11px]">
              {status.qa?.status === "ok" ? <><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /><span className="text-emerald-300/80">翻訳QA: 品質ゲート通過</span></> : status.qa?.status === "failed" ? <><AlertTriangle className="h-3.5 w-3.5 text-red-400" /><span className="text-red-300/90">翻訳QA: 重大エラー {status.qa?.critical_count ?? 0}件</span></> : <><AlertTriangle className="h-3.5 w-3.5 text-amber-400" /><span className="text-amber-300/80">翻訳QA: {status.qa?.warning_count ?? 0}件の確認候補</span></>}
              {typeof status.qa?.coverage?.japanese_percent === "number" ? <span className={cn("font-mono", status.qa.coverage.japanese_percent >= status.qa.coverage.minimum_percent ? "text-emerald-400/70" : "text-red-300/80")}>日本語化率 {status.qa.coverage.japanese_percent.toFixed(1)}%</span> : null}
              {status.qa?.warnings?.length ? <span className="text-zinc-700">{showQa ? "閉じる" : "詳細"}</span> : null}
            </div>
            {status.qa?.warnings?.[0] && <p className="mt-1 truncate text-[10px] text-zinc-600">{status.qa.warnings[0].message}</p>}
          </button>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="ghost" size="sm" disabled={preflightRunning} onClick={onRunPreflight} className="h-8 rounded-md border border-white/[0.06] px-3 text-[11px] text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300">{preflightRunning ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : <Sparkles className="mr-1.5 h-3 w-3" />}1ページテスト</Button>
            {preflightPdfUrl && <Button variant="ghost" size="sm" onClick={() => window.open(preflightPdfUrl, "_blank", "noopener,noreferrer")} className="h-8 rounded-md border border-white/[0.06] px-3 text-[11px] text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300">テストPDF</Button>}
            <Button variant="ghost" size="sm" disabled={!status.worker_ready} onClick={onRerunProduction} className="h-8 rounded-md border border-white/[0.06] px-3 text-[11px] text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300 disabled:opacity-30"><RotateCcw className="mr-1.5 h-3 w-3" />安全に再生成</Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function QuizPanel({
  current,
  currentIndex,
  total,
  progress,
  reviewMode,
  answer,
  setAnswer,
  status,
  submitAnswer,
  goNext,
  goPrevious,
  isLastQuestion,
  score,
  evaluation,
  attempts,
  onRetry,
  reportOpen,
  setReportOpen,
  reportText,
  setReportText,
  reportSent,
  submitReport,
  uploadState,
}: {
  current: QuizItem | null
  currentIndex: number
  total: number
  progress: number
  reviewMode: boolean
  answer: string
  setAnswer: (value: string) => void
  status: QuizStatus
  submitAnswer: () => void
  goNext: () => void
  goPrevious: () => void
  isLastQuestion: boolean
  score: number
  evaluation: Evaluation | null
  attempts: AttemptRecord[]
  onRetry: () => void
  reportOpen: boolean
  setReportOpen: (value: boolean) => void
  reportText: string
  setReportText: (value: string) => void
  reportSent: boolean
  submitReport: () => void
  uploadState: UploadState
}) {
  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault()
      submitAnswer()
    }
  }

  return (
    <section className="flex h-full min-w-0 flex-col bg-zinc-950">
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.06] bg-zinc-900/30 px-5">
        <div className="flex items-center gap-3">
          <span className={cn(
            "text-[12px] font-medium uppercase tracking-[0.18em]",
            reviewMode ? "text-indigo-400/80" : "text-zinc-500"
          )}>
            {reviewMode ? "Review" : "Question"}
          </span>
          <span className="font-mono text-[13px] text-zinc-300">
            {total > 0 ? `${currentIndex + 1} / ${total}` : "0 / 0"}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="h-px w-36 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full bg-indigo-500/45 transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="w-10 text-right font-mono text-[12px] text-zinc-600">
            {Math.round(progress)}%
          </span>

          <Button
            variant="ghost"
            size="icon"
            disabled={currentIndex <= 0 || status === "checking"}
            onClick={goPrevious}
            className="h-7 w-7 rounded-md text-zinc-600 transition-all duration-150 hover:bg-white/[0.05] hover:text-zinc-300 disabled:text-zinc-800"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            disabled={!evaluation || isLastQuestion || status === "checking"}
            onClick={goNext}
            className="h-7 w-7 rounded-md text-zinc-600 transition-all duration-150 hover:bg-white/[0.05] hover:text-zinc-300 disabled:text-zinc-800"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div
        className={cn(
          "min-h-0 flex-1 overflow-y-auto px-6 py-6 xl:px-8 xl:py-7",
          "scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/[0.06]",
          "[&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent",
          "[&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/[0.08]"
        )}
      >
        {!current ? (
          <div className="flex min-h-[420px] items-center justify-center">
            <div className="max-w-sm text-center">
              {uploadState === "uploading" ? (
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-indigo-400/60" />
              ) : (
                <BookOpen className="mx-auto h-5 w-5 text-zinc-700" />
              )}
              <p className="mt-4 text-[13px] font-medium text-zinc-400">
                {uploadState === "uploading" ? "問題を作成しています" : "PDFを読み込むと学習を開始できます"}
              </p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-700">
                英語本文をページ情報付きで抽出し、翻訳問題として順番に出題します
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <section className="rounded-xl border border-white/[0.06] bg-zinc-900/40">
              <div className="px-5 pb-5 pt-4.5">
                <div className="flex items-start justify-between gap-4">
                  <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-zinc-500">
                    Source · English
                  </p>

                  <span className="rounded-md border border-indigo-500/[0.18] bg-indigo-500/[0.08] px-2 py-0.5 font-mono text-[10px] text-indigo-400/70">
                    p.{current.pageRef}
                  </span>
                </div>

                <p className="mt-4 max-w-[980px] text-[19px] leading-[1.7] text-zinc-100">
                  {current.sourceText}
                </p>
              </div>
            </section>

            <section className="rounded-xl border border-white/[0.04] bg-transparent px-5 py-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">
                AI Reference
              </p>
              <p className="mt-3 flex gap-2.5 text-[15px] italic leading-[1.72] text-zinc-400">
                <Sparkles className="mt-1 h-3 w-3 shrink-0 text-zinc-700" />
                <span>
                  {evaluation
                    ? evaluation.referenceTranslation
                    : "模範訳は採点後に表示されます。"}
                </span>
              </p>
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">
                  Your Translation · Japanese
                </p>
                <span className="text-[12px] text-zinc-600">
                  ⌘ / Ctrl + Return to submit
                </span>
              </div>

              <div className="relative">
                <Textarea
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                  onKeyDown={handleKeyDown}
                  maxLength={1200}
                  placeholder="日本語で翻訳してください…"
                  disabled={status !== "idle"}
                  className={cn(
                    "min-h-[176px] resize-none rounded-xl border border-white/[0.08]",
                    "bg-zinc-900/60 px-5 py-4 text-[18px] leading-[1.7] text-zinc-100",
                    "placeholder:text-[17px] placeholder:italic placeholder:text-zinc-600",
                    "transition-all duration-200 hover:border-white/[0.10]",
                    "focus:border-white/[0.15] focus:ring-1 focus:ring-zinc-800 focus:ring-offset-0",
                    "focus-visible:ring-1 focus-visible:ring-zinc-800 focus-visible:ring-offset-0"
                  )}
                />

                <span className="absolute bottom-3 right-3 font-mono text-[11px] text-zinc-600">
                  {answer.length} / 1200
                </span>
              </div>

              <div className="flex min-h-8 items-center justify-between">
                <div>
                  {status === "checking" && (
                    <div className="flex animate-in items-center gap-2 fade-in duration-200">
                      <Loader2 className="h-3 w-3 animate-spin text-indigo-400/60" />
                      <span className="text-[12px] italic text-zinc-600">Scoring…</span>
                    </div>
                  )}
                </div>

                {status === "idle" && (
                  <Button
                    onClick={submitAnswer}
                    disabled={!answer.trim()}
                    size="sm"
                    className="h-10 rounded-lg border border-white/[0.10] bg-indigo-600 px-5 text-[14px] font-medium text-white transition-all duration-150 hover:border-white/[0.18] hover:bg-indigo-500 disabled:opacity-30"
                  >
                    <Send className="mr-1.5 h-3 w-3" />
                    採点する
                  </Button>
                )}
              </div>
            </section>

            {(status === "correct" || status === "partial" || status === "incorrect") && evaluation && (
              <FeedbackCard
                type={status}
                evaluation={evaluation}
                isLastQuestion={isLastQuestion}
                goNext={goNext}
                score={score}
                total={total}
                attempts={attempts}
                onRetry={onRetry}
                reviewMode={reviewMode}
              />
            )}
          </div>
        )}
      </div>

      <FooterReport
        reportOpen={reportOpen}
        setReportOpen={setReportOpen}
        reportText={reportText}
        setReportText={setReportText}
        reportSent={reportSent}
        submitReport={submitReport}
      />
    </section>
  )
}

function FeedbackCard({
  type,
  evaluation,
  isLastQuestion,
  goNext,
  score,
  total,
  attempts,
  onRetry,
  reviewMode,
}: {
  type: "correct" | "partial" | "incorrect"
  evaluation: Evaluation
  isLastQuestion: boolean
  goNext: () => void
  score: number
  total: number
  attempts: AttemptRecord[]
  onRetry: () => void
  reviewMode: boolean
}) {
  const [detailsOpen, setDetailsOpen] = React.useState(false)
  const isCorrect = type === "correct"
  const isPartial = type === "partial"

  const tone = isCorrect
    ? {
        border: "border-emerald-500/[0.15] bg-emerald-950/20",
        text: "text-emerald-400",
        ring: "rgba(52,211,153,0.75)",
        title: "AI判定：合格",
      }
    : isPartial
      ? {
          border: "border-amber-500/[0.15] bg-amber-950/15",
          text: "text-amber-400",
          ring: "rgba(251,191,36,0.75)",
          title: "AI判定：要修正",
        }
      : {
          border: "border-red-500/[0.14] bg-red-950/15",
          text: "text-red-400",
          ring: "rgba(248,113,113,0.75)",
          title: "AI判定：再確認が必要",
        }

  const issueLabels: Record<IssueCategory, string> = {
    omission: "未訳・脱落",
    mistranslation: "誤訳",
    wording: "表現改善",
    terminology: "専門用語",
  }

  const issueCounts = evaluation.issues.reduce(
    (counts, issue) => {
      counts[issue.category] += 1
      return counts
    },
    {
      omission: 0,
      mistranslation: 0,
      wording: 0,
      terminology: 0,
    } satisfies Record<IssueCategory, number>
  )

  const visibleIssues = detailsOpen ? evaluation.issues : evaluation.issues.slice(0, 4)
  const previousAttempt = attempts.length >= 2 ? attempts[attempts.length - 2] : null
  const scoreDelta = previousAttempt ? evaluation.score - previousAttempt.evaluation.score : null
  const hasLegacyDetails =
    evaluation.issues.length === 0 &&
    (evaluation.meaningErrors.length > 0 || evaluation.missingInformation.length > 0)
  const canExpand = evaluation.issues.length > 4

  return (
    <section
      className={cn(
        "animate-in rounded-xl border bg-zinc-900/35 fade-in slide-in-from-bottom-2 duration-300",
        tone.border
      )}
    >
      <div className="grid grid-cols-[1fr_120px] border-b border-white/[0.05]">
        <div className="px-4 py-4">
          <div className="flex flex-wrap items-center gap-2">
            {isCorrect ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            ) : isPartial ? (
              <AlertTriangle className="h-4 w-4 text-amber-400" />
            ) : (
              <XCircle className="h-4 w-4 text-red-400" />
            )}
            <p className={cn("text-[16px] font-medium", tone.text)}>{tone.title}</p>

            {attempts.length > 0 && (
              <span className="ml-1 rounded-md border border-white/[0.06] bg-white/[0.025] px-2 py-0.5 font-mono text-[11px] text-zinc-500">
                {attempts.length}回目
              </span>
            )}

            {scoreDelta !== null && (
              <span
                className={cn(
                  "rounded-md border px-2 py-0.5 font-mono text-[11px]",
                  scoreDelta > 0 &&
                    "border-emerald-500/[0.14] bg-emerald-500/[0.06] text-emerald-400/85",
                  scoreDelta === 0 &&
                    "border-white/[0.06] bg-white/[0.025] text-zinc-500",
                  scoreDelta < 0 &&
                    "border-red-500/[0.14] bg-red-500/[0.06] text-red-400/85"
                )}
              >
                前回比 {scoreDelta > 0 ? "+" : ""}
                {scoreDelta}
              </span>
            )}
          </div>

          <p className="mt-3 max-w-[760px] whitespace-pre-wrap text-[16px] leading-[1.72] text-zinc-300">
            {evaluation.feedback}
          </p>

          {attempts.length > 1 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-[11px] text-zinc-600">スコア履歴</span>
              {attempts.slice(-5).map((attempt, index) => {
                const absoluteIndex = Math.max(attempts.length - 5, 0) + index + 1
                return (
                  <span
                    key={`${attempt.createdAt}-${absoluteIndex}`}
                    className="rounded-md border border-white/[0.05] bg-black/10 px-2 py-1 font-mono text-[11px] text-zinc-500"
                  >
                    {absoluteIndex}: {attempt.evaluation.score}
                  </span>
                )
              })}
            </div>
          )}
        </div>

        <div className="flex items-center justify-center border-l border-white/[0.05]">
          <div className="relative flex h-[92px] w-[92px] items-center justify-center">
            <svg viewBox="0 0 100 100" className="h-[92px] w-[92px]">
              <circle
                cx="50"
                cy="50"
                r="38"
                fill="none"
                stroke="rgba(255,255,255,0.08)"
                strokeWidth="7"
              />
              <circle
                cx="50"
                cy="50"
                r="38"
                fill="none"
                stroke={tone.ring}
                strokeWidth="7"
                strokeLinecap="round"
                strokeDasharray={`${(evaluation.score / 100) * 238} 238`}
                transform="rotate(-90 50 50)"
              />
            </svg>

            <div className="absolute text-center">
              <div className="font-mono text-[30px] leading-none text-zinc-100">
                {evaluation.score}
              </div>
              <div className="mt-1 font-mono text-[11px] text-zinc-500">/100</div>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        {(evaluation.issues.length > 0 || hasLegacyDetails) && (
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="mr-1 text-[13px] font-medium text-zinc-400">学習ポイント</p>

              {(Object.keys(issueCounts) as IssueCategory[])
                .filter((category) => issueCounts[category] > 0)
                .map((category) => (
                  <span
                    key={category}
                    className={cn(
                      "rounded-md border px-2 py-0.5 text-[11px]",
                      (category === "omission" || category === "mistranslation") &&
                        "border-red-500/[0.14] bg-red-500/[0.05] text-red-300/80",
                      category === "wording" &&
                        "border-amber-500/[0.14] bg-amber-500/[0.05] text-amber-300/80",
                      category === "terminology" &&
                        "border-indigo-500/[0.14] bg-indigo-500/[0.05] text-indigo-300/80"
                    )}
                  >
                    {issueLabels[category]} {issueCounts[category]}
                  </span>
                ))}
            </div>

            {evaluation.issues.length > 0 && (
              <div className="mt-3 grid gap-2">
                {visibleIssues.map((issue, index) => (
                  <div
                    key={`${issue.category}-${issue.sourceSpan}-${index}`}
                    className="rounded-lg border border-white/[0.055] bg-black/10 px-3.5 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          "rounded-md border px-2 py-0.5 text-[11px] font-medium",
                          issue.category === "omission" &&
                            "border-red-500/[0.16] bg-red-500/[0.06] text-red-300/85",
                          issue.category === "mistranslation" &&
                            "border-red-500/[0.16] bg-red-500/[0.06] text-red-300/85",
                          issue.category === "wording" &&
                            "border-amber-500/[0.16] bg-amber-500/[0.06] text-amber-300/85",
                          issue.category === "terminology" &&
                            "border-indigo-500/[0.16] bg-indigo-500/[0.06] text-indigo-300/85"
                        )}
                      >
                        {issueLabels[issue.category]}
                      </span>

                      {issue.sourceSpan && (
                        <span className="font-mono text-[12px] text-zinc-500">
                          {issue.sourceSpan}
                        </span>
                      )}
                    </div>

                    <p className="mt-2 text-[14px] leading-[1.7] text-zinc-300">
                      {issue.message}
                    </p>

                    {issue.suggestion && (
                      <p className="mt-1.5 text-[13px] leading-[1.65] text-zinc-500">
                        修正案: {issue.suggestion}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {hasLegacyDetails && (
              <div className="mt-3 space-y-2 rounded-lg border border-white/[0.055] bg-black/10 px-3.5 py-3">
                {evaluation.missingInformation.map((item, index) => (
                  <p key={`missing-${index}`} className="text-[14px] leading-[1.7] text-zinc-300">
                    <span className="mr-2 text-red-400">未訳・脱落</span>
                    {item}
                  </p>
                ))}
                {evaluation.meaningErrors.map((item, index) => (
                  <p key={`meaning-${index}`} className="text-[14px] leading-[1.7] text-zinc-300">
                    <span className="mr-2 text-red-400">誤訳</span>
                    {item}
                  </p>
                ))}
              </div>
            )}

            {canExpand && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDetailsOpen((prev) => !prev)}
                className="mt-2 h-8 rounded-lg px-2.5 text-[12px] text-zinc-500 transition-all duration-150 hover:bg-white/[0.04] hover:text-zinc-300"
              >
                {detailsOpen ? "指摘を折りたたむ" : `残り${evaluation.issues.length - 4}件を表示`}
                <ChevronDown
                  className={cn(
                    "ml-1.5 h-3 w-3 transition-transform",
                    detailsOpen && "rotate-180"
                  )}
                />
              </Button>
            )}
          </div>
        )}

        {evaluation.syntaxInsight && evaluation.syntaxInsight.relations.length > 0 && (
          <div className="border-t border-white/[0.05] pt-4">
            <div className="flex items-center gap-2">
              <p className="text-[13px] font-medium text-zinc-400">構文の対応関係</p>
              <span className="rounded-md border border-indigo-500/[0.14] bg-indigo-500/[0.05] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-indigo-300/70">
                Syntax Focus
              </span>
            </div>

            {evaluation.syntaxInsight.summary && (
              <p className="mt-2 text-[14px] leading-[1.7] text-zinc-400">
                {evaluation.syntaxInsight.summary}
              </p>
            )}

            <div className="mt-3 grid gap-2">
              {evaluation.syntaxInsight.relations.map((relation, index) => (
                <div
                  key={`${relation.left}-${relation.relation}-${relation.right}-${index}`}
                  className="rounded-lg border border-white/[0.055] bg-black/10 px-3.5 py-3"
                >
                  <div className="flex flex-wrap items-center gap-2 text-[13px] leading-[1.6]">
                    <span className="rounded-md border border-white/[0.07] bg-white/[0.025] px-2.5 py-1 text-zinc-300">
                      {relation.left}
                    </span>
                    <span className="font-mono text-[11px] text-indigo-300/75">
                      ── {relation.relation} ──▶
                    </span>
                    <span className="rounded-md border border-white/[0.07] bg-white/[0.025] px-2.5 py-1 text-zinc-300">
                      {relation.right}
                    </span>
                  </div>
                  {relation.explanation && (
                    <p className="mt-2 text-[12px] leading-[1.65] text-zinc-500">
                      {relation.explanation}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="border-t border-white/[0.05] pt-4">
          <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">
            Model Answer
          </p>
          <p className="mt-3 text-[16px] leading-[1.72] text-zinc-300">
            {evaluation.referenceTranslation}
          </p>
        </div>

        {evaluation.keyPoints.length > 0 && (
          <div className="border-t border-white/[0.05] pt-4">
            <p className="text-[13px] font-medium text-zinc-400">キーポイント</p>
            <p className="mt-1 text-[11px] text-zinc-600">
              原文の重要表現と、その意味に対応する日本語
            </p>

            <div className="mt-3 grid gap-2 lg:grid-cols-2">
              {evaluation.keyPoints.map((point, index) => (
                <div
                  key={`${point.source}-${index}`}
                  className={cn(
                    "flex items-start gap-2.5 rounded-lg border px-3 py-3",
                    point.status === "correct" &&
                      "border-emerald-500/[0.14] bg-emerald-500/[0.06]",
                    point.status === "warning" &&
                      "border-amber-500/[0.18] bg-amber-500/[0.07]",
                    point.status === "missing" &&
                      "border-red-500/[0.14] bg-red-500/[0.06]"
                  )}
                >
                  {point.status === "warning" && (
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400/80" />
                  )}
                  {point.status === "correct" && (
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400/80" />
                  )}
                  {point.status === "missing" && (
                    <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-400/80" />
                  )}

                  <div className="min-w-0">
                    <p className="text-[13px] leading-[1.6] text-zinc-300">{point.source}</p>
                    <p className="mt-1.5 text-[13px] leading-[1.6] text-zinc-500">
                      → {point.translation || "日本語対応は再採点で更新されます"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex min-h-10 items-center justify-between border-t border-white/[0.05] pt-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={onRetry}
            className="h-9 rounded-lg border border-white/[0.06] bg-white/[0.025] px-3.5 text-[12px] text-zinc-400 transition-all duration-150 hover:bg-white/[0.05] hover:text-zinc-200"
          >
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            訳文を修正して再採点
          </Button>

          {isLastQuestion ? (
            <div className="flex animate-in items-center gap-2 fade-in duration-300">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400/70" />
              <span className="text-[12px] text-zinc-500">
                {reviewMode ? (
                  "復習セッション完了"
                ) : (
                  <>
                    完了 <span className="font-mono text-zinc-200">{score}</span>
                    <span className="font-mono text-zinc-700">/{total}</span>
                  </>
                )}
              </span>
            </div>
          ) : (
            <Button
              variant={isCorrect ? "default" : "ghost"}
              size="sm"
              onClick={goNext}
              className={cn(
                "h-9 rounded-lg px-4 text-[12px] transition-all duration-150",
                isCorrect
                  ? "border border-white/[0.10] bg-indigo-600 text-white hover:bg-indigo-500"
                  : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-200"
              )}
            >
              {reviewMode ? "次の復習へ" : "次の問題へ"}
              <ArrowRight className="ml-1.5 h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
    </section>
  )
}

function FooterReport({
  reportOpen,
  setReportOpen,
  reportText,
  setReportText,
  reportSent,
  submitReport,
}: {
  reportOpen: boolean
  setReportOpen: (value: boolean) => void
  reportText: string
  setReportText: (value: string) => void
  reportSent: boolean
  submitReport: () => void
}) {
  return (
    <footer className="flex shrink-0 items-center justify-between border-t border-white/[0.05] bg-zinc-900/20 px-4 py-2.5">
      {!reportOpen && !reportSent && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setReportOpen(true)}
          className="group -ml-1 h-8 rounded-md px-2 text-[12px] text-zinc-700 transition-all duration-150 hover:bg-transparent hover:text-zinc-500"
        >
          <AlertTriangle className="mr-1.5 h-3 w-3 text-zinc-700 transition-colors duration-200 group-hover:text-amber-500/60" />
          AIに翻訳ミスを報告する
        </Button>
      )}

      {reportSent && (
        <div className="flex animate-in items-center gap-1.5 fade-in duration-200">
          <CheckCircle2 className="h-3 w-3 text-emerald-400/60" />
          <span className="text-[12px] text-zinc-500">
            Reported — thank you
          </span>
        </div>
      )}

      {reportOpen && !reportSent && (
        <div className="w-full animate-in slide-in-from-bottom-1 duration-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3 text-amber-500/50" />
              <span className="text-[9px] font-medium uppercase tracking-[0.16em] text-zinc-600">
                Describe the issue
              </span>
            </div>

            <button
              onClick={() => setReportOpen(false)}
              className="text-[10px] text-zinc-700 transition-colors duration-150 hover:text-zinc-400"
            >
              Cancel
            </button>
          </div>

          <div className="mt-1.5 flex gap-2">
            <input
              value={reportText}
              onChange={(event) => setReportText(event.target.value)}
              placeholder="誤訳・採点ミスの内容を短く入力..."
              className={cn(
                "h-7 flex-1 rounded-md border border-white/[0.07] bg-zinc-900/70 px-3",
                "text-[11px] text-zinc-300 placeholder:text-zinc-700",
                "transition-all duration-150 focus:border-white/[0.15]",
                "focus:outline-none focus:ring-1 focus:ring-zinc-800 focus:ring-offset-0"
              )}
            />

            <Button
              size="sm"
              onClick={submitReport}
              disabled={!reportText.trim()}
              className="h-7 rounded-md border border-amber-500/[0.18] bg-amber-500/[0.10] px-2.5 text-[11px] text-amber-400/80 transition-all duration-150 hover:bg-amber-500/[0.15] hover:text-amber-300 disabled:opacity-25"
            >
              <Send className="h-3 w-3" />
            </Button>
          </div>
        </div>
      )}

      {!reportOpen && !reportSent && (
        <div className="ml-auto flex items-center gap-4 text-[12px] text-zinc-700">
          <div className="flex items-center gap-1.5">
            <Lightbulb className="h-3 w-3" />
            <span>ヒントを見る</span>
          </div>

          <div className="hidden items-center gap-1.5 md:flex">
            <HelpCircle className="h-3 w-3" />
            <span>ショートカット</span>
          </div>
        </div>
      )}
    </footer>
  )
}
