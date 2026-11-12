"use client"

import * as React from "react"
import { Inter, JetBrains_Mono } from "next/font/google"
import {
  AlertTriangle,
  Bell,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  GitBranch,
  Files,
  FolderOpen,
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
  Settings2,
  Sun,
  Moon,
  Send,
  ShieldCheck,
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
import { KnowledgeGraphPanel } from "@/components/knowledge-graph-panel"
import {
  JOB_MONITOR_STORAGE_KEY, createTrackedJob, isTerminalJob,
  jobStatusLabel, jobStatusUrl, keepRecentJobs, restoreTrackedJobs, updateTrackedJob,
  type TrackedJobKind, type TrackedTranslationJob,
} from "@/lib/translation-job-monitor"

const inter = Inter({
  subsets: ["latin", "latin-ext"],
  variable: "--font-inter",
})

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

type UiTheme = "dark" | "light"
type DisplayPreferences = {
  theme: UiTheme
  sourceSize: number
  answerSize: number
  feedbackSize: number
  referenceSize: number
}
const DISPLAY_PREFERENCES_KEY = "pepertranslator:display-preferences:v1"
const DEFAULT_DISPLAY_PREFERENCES: DisplayPreferences = {
  theme: "dark", sourceSize: 20, answerSize: 18, feedbackSize: 16, referenceSize: 16,
}
function normalizedDisplayPreferences(raw: unknown): DisplayPreferences {
  const candidate = raw && typeof raw === "object" ? raw as Partial<DisplayPreferences> : {}
  const clamp = (value: unknown, fallback: number, lo: number, hi: number) =>
    typeof value === "number" && Number.isFinite(value) ? Math.round(Math.max(lo, Math.min(hi, value))) : fallback
  return {
    theme: candidate.theme === "light" ? "light" : "dark",
    sourceSize: clamp(candidate.sourceSize, 20, 15, 28),
    answerSize: clamp(candidate.answerSize, 18, 14, 26),
    feedbackSize: clamp(candidate.feedbackSize, 16, 12, 22),
    referenceSize: clamp(candidate.referenceSize, 16, 13, 24),
  }
}

type QuizStatus = "idle" | "checking" | "correct" | "partial" | "incorrect"

type KeyPointStatus = "correct" | "warning" | "missing"

type IssueCategory = "omission" | "mistranslation" | "wording" | "terminology"
type SemanticUnitStatus = "correct" | "partial" | "missing" | "wrong"
type SemanticImportance = "core" | "support" | "detail"

type SemanticUnit = {
  id: string
  source: string
  translation: string
  importance: SemanticImportance
  status: SemanticUnitStatus
  note: string
  earnedPoints: number
  maxPoints: number
}

type ScoreBreakdown = {
  meaning: number
  terminology: number
  japanese: number
  rawTotal: number
  total: number
  capReason: string
}

type JapaneseQuality = {
  level: "natural" | "minor" | "awkward" | "broken"
  note: string
}

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

type ExternalAudit = {
  provider: "azure" | "local"
  status: "verified" | "minor_difference" | "disagreement" | "local_only" | "quota_exhausted" | "unavailable"
  translation: string
  message: string
  monthUsage: number
  monthlySoftLimit: number
  cached: boolean
}

type Evaluation = {
  verdict: "correct" | "partial" | "incorrect"
  score: number
  feedback: string
  referenceTranslation: string
  referenceReview?: { status: string; flags: string[]; revision: string; reviewId: string }
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
  semanticUnits?: SemanticUnit[]
  scoreBreakdown?: ScoreBreakdown | null
  japaneseQuality?: JapaneseQuality | null
  externalAudit?: ExternalAudit | null
  syntaxInsight: SyntaxInsight | null
}

type AttemptRecord = {
  answer: string
  evaluation: Evaluation
  createdAt: string
  graderVersion?: string
}

type QuestionRecord = {
  answer: string
  evaluation: Evaluation | null
  attempts: AttemptRecord[]
  updatedAt: string
}

type SavedSession = {
  version: 6
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
  document_kind?: "paper" | "slides" | "japanese" | "image_pdf" | "unstructured"
  source_language?: string
  quiz_enabled?: boolean
  quiz_notice?: string
  chunks: {
    id: number
    pageRef: number
    sourceText: string
  }[]
  library?: {
    reused?: boolean
    reused_exact?: boolean
    reading_ready?: boolean
    layout_ready?: boolean
    possible_duplicates?: string[]
  }
}

type LibraryItem = {
  document_id: string
  paper_key: string
  title: string
  filenames: string[]
  page_count: number
  total_chunks: number
  added_at: string
  last_opened_at: string
  doi?: string | null
  notes?: string
  document_kind?: string
  reading_ready: boolean
  layout_ready: boolean
  mono_ready: boolean
  dual_ready: boolean
  qa_ready: boolean
  quality_gate?: "pass" | "fail" | null
  cache_stale?: boolean
  variant_count: number
  variants: {
    document_id: string
    filename?: string | null
    layout_ready: boolean
    reading_ready: boolean
    last_opened_at: string
  }[]
}

type VocabularyDirection = "en-ja" | "ja-en"
type VocabularyKind = "term" | "word" | "phrase" | "pattern"
type VocabularyKindFilter = "all" | VocabularyKind

type VocabularyCard = {
  cardId: string
  source: string
  translation: string
  kind: VocabularyKind
  origin: string
  surfaceForms: string[]
  contexts: string[]
  documentIds: string[]
  seenCount: number
  duplicateIds: string[]
  duplicateStatus: "none" | "alias" | "conflict"
  correctEnJa: number
  wrongEnJa: number
  correctJaEn: number
  wrongJaEn: number
  lastReviewedAt: string | null
}

type VocabularyCandidate = {
  source: string
  translation: string
  kind?: VocabularyKind
  origin?: string
  surface?: string
  context?: string
}

type RightPanelMode = "study" | "japanese" | "vocabulary"

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
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000"

const QUIZ_CLIENT_CACHE_VERSION = "quiz-grader-v1.7.27"

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

function normalizeQuizAnswer(text: string) {
  return text.normalize("NFKC").replace(/\s+/g, "").trim()
}

function mapVocabularyCards(raw: unknown): VocabularyCard[] {
  if (!Array.isArray(raw)) return []
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return []
    const value = item as Record<string, unknown>
    const cardId = String(value.card_id ?? "")
    const source = String(value.source ?? "").trim()
    const translation = String(value.translation ?? "").trim()
    if (!cardId || !source || !translation) return []
    const rawKind = String(value.kind ?? "term")
    const kind: VocabularyKind = (["term", "word", "phrase", "pattern"] as string[]).includes(rawKind)
      ? rawKind as VocabularyKind
      : "term"
    const surfaceForms = Array.isArray(value.surface_forms)
      ? value.surface_forms.map((entry) => String(entry)).filter(Boolean)
      : []
    const contexts = Array.isArray(value.contexts)
      ? value.contexts.map((entry) => String(entry)).filter(Boolean)
      : []
    return [{
      cardId,
      source,
      translation,
      kind,
      origin: String(value.origin ?? "glossary"),
      surfaceForms,
      contexts,
      documentIds: Array.isArray(value.document_ids) ? value.document_ids.map((entry) => String(entry)).filter(Boolean) : [],
      seenCount: Number(value.seen_count ?? Math.max(1, contexts.length)),
      duplicateIds: Array.isArray(value.duplicate_ids) ? value.duplicate_ids.map((entry) => String(entry)).filter(Boolean) : [],
      duplicateStatus: value.duplicate_status === "conflict" ? "conflict" : value.duplicate_status === "alias" ? "alias" : "none",
      correctEnJa: Number(value.correct_en_ja ?? 0),
      wrongEnJa: Number(value.wrong_en_ja ?? 0),
      correctJaEn: Number(value.correct_ja_en ?? 0),
      wrongJaEn: Number(value.wrong_ja_en ?? 0),
      lastReviewedAt: value.last_reviewed_at ? String(value.last_reviewed_at) : null,
    }]
  })
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
  if ((evaluation.semanticUnits ?? []).some((unit) => unit.status !== "correct")) return true
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
        const rubricCompatible = Boolean(parsed.version === 6 && evaluation && (evaluation.semanticUnits?.length ?? 0) > 0)
        const attempts = rubricCompatible
          ? (Array.isArray(record.attempts) && record.attempts.length > 0
              ? record.attempts.filter((attempt) => (attempt.evaluation.semanticUnits?.length ?? 0) > 0)
              : evaluation
                ? [{ answer: record.answer ?? "", evaluation, createdAt: record.updatedAt ?? new Date().toISOString() }]
                : [])
          : []

        // Quiz v1.3.8 added relation-role auditing; preserve answers but invalidate older scores. Preserve the learner's answer, but
        // invalidate old opaque scores so they are not mixed with rubric-based scores.
        const currentEvaluation = rubricCompatible && hasBilingualKeyPoints(evaluation) ? evaluation : null

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
      version: 6,
      currentIndex: parsed.currentIndex,
      records,
    }
  } catch {
    return null
  }
}


export default function Page() {
  const [displayPreferences, setDisplayPreferences] = React.useState<DisplayPreferences>(DEFAULT_DISPLAY_PREFERENCES)
  const [preferencesReady, setPreferencesReady] = React.useState(false)
  React.useEffect(() => {
    try {
      const stored = window.localStorage.getItem(DISPLAY_PREFERENCES_KEY)
      if (stored) setDisplayPreferences(normalizedDisplayPreferences(JSON.parse(stored)))
    } catch { /* No local settings: continue using defaults. */ }
    setPreferencesReady(true)
  }, [])
  React.useEffect(() => {
    if (!preferencesReady) return
    try { window.localStorage.setItem(DISPLAY_PREFERENCES_KEY, JSON.stringify(displayPreferences)) }
    catch { /* Read-only browser storage does not prevent reading. */ }
  }, [displayPreferences, preferencesReady])
  const [questions, setQuestions] = React.useState<QuizItem[]>([])
  const [currentIndex, setCurrentIndex] = React.useState(0)
  const [answer, setAnswer] = React.useState("")
  const [status, setStatus] = React.useState<QuizStatus>("idle")
  const [evaluation, setEvaluation] = React.useState<Evaluation | null>(null)
  const [records, setRecords] = React.useState<Record<string, QuestionRecord>>({})
  const [reviewSequence, setReviewSequence] = React.useState<number[] | null>(null)

  const [gradingReportStatus, setGradingReportStatus] = React.useState<"idle" | "saving" | "saved" | "error">("idle")
  const [gradingElapsedMs, setGradingElapsedMs] = React.useState(0)
  const [gradingNotice, setGradingNotice] = React.useState("")
  const [vocabularyCards, setVocabularyCards] = React.useState<VocabularyCard[]>([])
  const [vocabularyLoading, setVocabularyLoading] = React.useState(false)
  const [vocabularyError, setVocabularyError] = React.useState<string | null>(null)

  const [paperTitle, setPaperTitle] = React.useState("No paper loaded")
  const [filename, setFilename] = React.useState<string | null>(null)
  const [pageCount, setPageCount] = React.useState(0)
  const [documentId, setDocumentId] = React.useState<string | null>(null)
  const [uploadState, setUploadState] = React.useState<UploadState>("empty")
  const [uploadError, setUploadError] = React.useState<string | null>(null)
  const [quizNotice, setQuizNotice] = React.useState("")
  const [documentKind, setDocumentKind] = React.useState("paper")
  const [resumeDocumentId, setResumeDocumentId] = React.useState<string | null>(null)
  const [libraryOpen, setLibraryOpen] = React.useState(false)
  const [knowledgeGraphOpen, setKnowledgeGraphOpen] = React.useState(false)
  const [knowledgeGraphInitialDocumentId, setKnowledgeGraphInitialDocumentId] = React.useState<string | null>(null)
  const [libraryItems, setLibraryItems] = React.useState<LibraryItem[]>([])
  const [libraryLoading, setLibraryLoading] = React.useState(false)
  const [libraryError, setLibraryError] = React.useState<string | null>(null)

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
  const [japaneseViewMode, setJapaneseViewMode] = React.useState<JapaneseViewMode>("layout")
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
  // Job tracking is independent of the selected document. No backend translation
  // is started or cancelled when switching Library documents or right-hand tabs.
  const activeDocumentRef = React.useRef<string | null>(null)
  const [trackedJobs, setTrackedJobs] = React.useState<TrackedTranslationJob[]>([])
  const trackedJobsRef = React.useRef<TrackedTranslationJob[]>([])
  const [jobMonitorReady, setJobMonitorReady] = React.useState(false)
  const [jobCenterOpen, setJobCenterOpen] = React.useState(false)
  const [desktopNotificationsAllowed, setDesktopNotificationsAllowed] = React.useState(false)
  const announcedThisPage = React.useRef(new Set<string>())
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
      version: 6,
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
    if (status !== "checking") return
    const startedAt = performance.now()
    setGradingElapsedMs(0)
    const timer = window.setInterval(() => {
      setGradingElapsedMs(performance.now() - startedAt)
    }, 100)
    return () => {
      setGradingElapsedMs(performance.now() - startedAt)
      window.clearInterval(timer)
    }
  }, [status])

  React.useEffect(() => {
    try { setTrackedJobs(keepRecentJobs(restoreTrackedJobs(window.localStorage.getItem(JOB_MONITOR_STORAGE_KEY)))) }
    catch { /* Private browsing still supports in-app notifications for this session. */ }
    setDesktopNotificationsAllowed(typeof Notification !== "undefined" && Notification.permission === "granted")
    setJobMonitorReady(true)
  }, [])

  React.useEffect(() => {
    if (!jobMonitorReady) return
    trackedJobsRef.current = trackedJobs
    try { window.localStorage.setItem(JOB_MONITOR_STORAGE_KEY, JSON.stringify(trackedJobs)) } catch {}
  }, [trackedJobs, jobMonitorReady])

  // Poll jobs even while another paper is open, while a quiz runs, or while the
  // vocabulary panel is active. Browser notifications require the window open.
  React.useEffect(() => {
    if (!jobMonitorReady) return
    let stopped = false
    let polling = false
    async function pollJobs() {
      if (polling) return
      const active = trackedJobsRef.current.filter((job) => !isTerminalJob(job))
      if (!active.length) return
      polling = true
      try {
        const observations = await Promise.all(active.map(async (job) => {
          try {
            const response = await fetch(jobStatusUrl(job, API_BASE_URL), { cache: "no-store" })
            if (!response.ok) return null // Network or transient API errors must not imply success/failure.
            return { id: job.id, payload: await response.json() }
          } catch { return null }
        }))
        if (stopped) return
        const updates = new Map<string, unknown>()
        for (const entry of observations) if (entry) updates.set(entry.id, entry.payload)
        if (!updates.size) return
        setTrackedJobs((previous) => {
          let changed = false
          const next = previous.map((job) => {
            if (!updates.has(job.id)) return job
            const updated = updateTrackedJob(job, updates.get(job.id))
            if (updated.status === job.status && updated.progress === job.progress &&
                updated.error === job.error && updated.missedPolls === job.missedPolls) return job
            changed = true
            return updated
          })
          return changed ? keepRecentJobs(next) : previous
        })
      } finally { polling = false }
    }
    void pollJobs()
    const timer = window.setInterval(() => { void pollJobs() }, 2600)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [jobMonitorReady])

  // A terminal transition produces one persistent in-app notice, and an optional
  // OS notification when the user has explicitly granted permission.
  React.useEffect(() => {
    if (!jobMonitorReady) return
    const fresh = trackedJobs.filter((job) => isTerminalJob(job) && !job.announced && !announcedThisPage.current.has(job.id))
    if (!fresh.length) return
    for (const job of fresh) {
      announcedThisPage.current.add(job.id)
      if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        try { new Notification(`PeperTranslator: ${jobStatusLabel(job)}`, { body: job.title }) } catch {}
      }
    }
    setTrackedJobs((previous) => previous.map((job) => fresh.some((item) => item.id === job.id)
      ? { ...job, announced: true } : job))
  }, [trackedJobs, jobMonitorReady])

  function trackNewJob(kind: TrackedJobKind, targetId: string, title: string) {
    const newJob = createTrackedJob(kind, targetId, title)
    announcedThisPage.current.delete(newJob.id)
    setTrackedJobs((previous) => keepRecentJobs([newJob, ...previous.filter((job) => job.id !== newJob.id)]))
  }

  function acknowledgeJob(id: string) {
    setTrackedJobs((previous) => previous.map((job) => job.id === id ? { ...job, acknowledged: true } : job))
  }

  function enableDesktopNotifications() {
    if (typeof Notification === "undefined") return
    // Only invoked by an explicit button click; never request permission on load.
    void Notification.requestPermission().then((permission) => setDesktopNotificationsAllowed(permission === "granted"))
      .catch(() => setDesktopNotificationsAllowed(false))
  }

  function openTrackedJob(job: TrackedTranslationJob) {
    acknowledgeJob(job.id)
    if (job.kind === "batch") {
      void refreshLayoutBatch(job.targetId, true)
      return
    }
    void openLibraryDocument(job.targetId).then((opened) => {
      if (!opened) return
      setJapaneseViewMode(job.kind === "reading" ? "reading" : "layout")
      setRightMode("japanese")
    })
  }

  React.useEffect(() => {
    void refreshVocabulary()
    try { setResumeDocumentId(window.localStorage.getItem("pepertranslator:last-document-id")) } catch {}
  }, [])

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

  async function refreshVocabulary() {
    setVocabularyLoading(true)
    setVocabularyError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/quiz/vocabulary`)
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || "単語カードを読み込めませんでした。")
      setVocabularyCards(mapVocabularyCards(data?.cards))
    } catch (error) {
      setVocabularyError(error instanceof Error ? error.message : "単語カードを読み込めませんでした。")
    } finally {
      setVocabularyLoading(false)
    }
  }

  async function addVocabularyCandidates(candidates: VocabularyCandidate[], questionId: number) {
    if (!candidates.length) return
    try {
      const response = await fetch(`${API_BASE_URL}/api/quiz/vocabulary/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cards: candidates.map((candidate) => ({
            source: candidate.source,
            translation: candidate.translation,
            kind: candidate.kind ?? "term",
            origin: candidate.origin ?? "glossary",
            surface: candidate.surface ?? "",
            context: candidate.context ?? "",
            document_id: documentId ?? "",
            question_id: questionId,
          })),
        }),
      })
      const data = await response.json().catch(() => null)
      if (response.ok) setVocabularyCards(mapVocabularyCards(data?.cards))
    } catch (error) {
      console.warn("Vocabulary auto-add failed:", error)
    }
  }

  async function syncVocabularyFromSource(sourceText: string, questionId: number) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/quiz/vocabulary/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_text: sourceText,
          document_id: documentId ?? "",
          question_id: questionId,
        }),
      })
      const data = await response.json().catch(() => null)
      if (response.ok) setVocabularyCards(mapVocabularyCards(data?.cards))
    } catch (error) {
      console.warn("Vocabulary cache-hit sync failed:", error)
    }
  }

  async function reviewVocabularyCard(cardId: string, direction: VocabularyDirection, known: boolean) {
    const response = await fetch(`${API_BASE_URL}/api/quiz/vocabulary/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card_id: cardId, direction, known }),
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) throw new Error(data?.detail || "単語カードの記録に失敗しました。")
    await refreshVocabulary()
  }

  async function refreshDocumentTranslation(targetDocumentId: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdfs/${targetDocumentId}/translation`)
      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || "全文翻訳の状態取得に失敗しました。")
      }

      const nextStatus = data as DocumentTranslationStatus
      if (activeDocumentRef.current !== targetDocumentId) return
      setDocumentTranslationStatus(nextStatus)

      if (nextStatus.status === "completed") {
        const resultResponse = await fetch(
          `${API_BASE_URL}/api/pdfs/${targetDocumentId}/translation/result`
        )
        const resultData = await resultResponse.json().catch(() => null)
        if (!resultResponse.ok) {
          throw new Error(resultData?.detail || "日本語版の読み込みに失敗しました。")
        }
        if (activeDocumentRef.current === targetDocumentId) setDocumentTranslation(resultData as DocumentTranslationResult)
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
      if (activeDocumentRef.current === documentId) setDocumentTranslationStatus(data as DocumentTranslationStatus)
      if (data?.status === "queued" || data?.status === "running") trackNewJob("reading", documentId, paperTitle)
      if (data?.status === "completed") {
        await refreshDocumentTranslation(documentId)
      }
    } catch (error) {
      if (activeDocumentRef.current !== documentId) return
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
      if (activeDocumentRef.current === targetDocumentId) setLayoutTranslationStatus(data as LayoutTranslationStatus)
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
      if (activeDocumentRef.current === targetDocumentId) setLayoutProductionStatus(next)
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
      if (activeDocumentRef.current === documentId) setLayoutTranslationStatus(data as LayoutTranslationStatus)
      if (data?.status === "queued" || data?.status === "running") trackNewJob("layout", documentId, paperTitle)
    } catch (error) {
      if (activeDocumentRef.current !== documentId) return
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
      trackNewJob("preflight", documentId, paperTitle)
      await refreshLayoutTranslation(documentId)
    } catch (error) {
      if (activeDocumentRef.current !== documentId) return
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
      if (activeDocumentRef.current === documentId) setLayoutProductionStatus(data as LayoutProductionStatus)
      if (data?.status === "queued" || data?.status === "running") trackNewJob("production", documentId, paperTitle)
      await refreshLayoutTranslation(documentId)
    } catch (error) {
      if (activeDocumentRef.current !== documentId) return
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
      if (next.status === "queued" || next.status === "running") trackNewJob("batch", next.batch_id, `${next.total}件の論文バッチ`)
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

  function resetDocumentUi(nextFilename: string | null = null) {
    activeDocumentRef.current = null
    setUploadError(null)
    setQuizNotice("")
    setDocumentKind("paper")
    setQuestions([])
    setCurrentIndex(0)
    setAnswer("")
    setStatus("idle")
    setEvaluation(null)
    setGradingNotice("")
    setRecords({})
    setReviewSequence(null)
    setRightMode("study")
    setDocumentTranslation(null)
    setDocumentTranslationStatus({
      status: "not_started", progress: 0, translated_segments: 0, total_segments: 0, error: null, updated_at: null,
    })
    setJapaneseViewMode("layout")
    setLayoutTranslationStatus({
      status: "not_started", progress: 0, error: null, updated_at: null, worker_ready: false, worker_path: null, model: "", mono_ready: false, dual_ready: false, qa: null,
    })
    setLayoutProductionStatus({
      status: "not_started", stage: "idle", progress: 0, error: null, page: 2, updated_at: null,
    })
    setReaderPageRequest(null)
    setReaderViewPage(1)
    setDocumentId(null)
    setPageCount(0)
    setFilename(nextFilename)
    setPaperTitle(nextFilename ? nextFilename.replace(/\.pdf$/i, "") : "No paper loaded")
  }

  function applyLoadedDocument(upload: UploadResponse) {
    activeDocumentRef.current = upload.document_id
    setFilename(upload.filename)
    setPaperTitle(upload.title || upload.filename)
    setDocumentId(upload.document_id)
    setPageCount(upload.page_count)
    setQuestions(upload.chunks)
    setDocumentKind(upload.document_kind ?? "paper")
    setQuizNotice(upload.quiz_notice ?? "")
    try {
      window.localStorage.setItem("pepertranslator:last-document-id", upload.document_id)
      setResumeDocumentId(upload.document_id)
    } catch {}

    const savedSession = readSavedSession(upload.document_id)
    const restoredRecords = savedSession?.records ?? {}
    const restoredIndex = Math.min(
      Math.max(savedSession?.currentIndex ?? 0, 0),
      Math.max(upload.chunks.length - 1, 0)
    )
    const restoredQuestion = upload.chunks[restoredIndex]
    const restoredRecord = restoredQuestion ? restoredRecords[String(restoredQuestion.id)] : undefined
    setRecords(restoredRecords)
    setCurrentIndex(restoredIndex)
    setAnswer(restoredRecord?.answer ?? "")
    setEvaluation(restoredRecord?.evaluation ?? null)
    setStatus(restoredRecord?.evaluation?.verdict ?? "idle")
    setUploadState("ready")
    void refreshDocumentTranslation(upload.document_id)
    void refreshLayoutTranslation(upload.document_id)
    void refreshLayoutProduction(upload.document_id)
  }

  async function refreshLibrary(openPanel = false) {
    if (openPanel) setLibraryOpen(true)
    setLibraryLoading(true)
    setLibraryError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/library`)
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || "Libraryを読み込めませんでした。")
      setLibraryItems(Array.isArray(data?.items) ? data.items : [])
    } catch (error) {
      setLibraryError(error instanceof Error ? error.message : "Libraryを読み込めませんでした。")
    } finally {
      setLibraryLoading(false)
    }
  }

  async function exportMobileBundle(targetDocumentId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/offline/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: [targetDocumentId], include_vocabulary: true }),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail || `オフラインZIPの作成に失敗しました (${response.status})`)
    }
    const archive = await response.blob()
    if (!archive.size) throw new Error("オフラインZIPが空です。")
    const href = URL.createObjectURL(archive)
    try {
      const a = document.createElement("a")
      a.href = href
      a.download = `PeperTranslator_Offline_${targetDocumentId.slice(0, 12)}.zip`
      document.body.appendChild(a)
      a.click()
      a.remove()
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(href), 5000)
    }
  }

  async function openLibraryDocument(targetDocumentId: string) {
    setUploadState("uploading")
    resetDocumentUi(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/library/${targetDocumentId}`)
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || "LibraryのPDFを開けませんでした。")
      applyLoadedDocument(data as UploadResponse)
      setLibraryOpen(false)
      void refreshLibrary(false)
      return true
    } catch (error) {
      setUploadState("error")
      setUploadError(error instanceof Error ? error.message : "LibraryのPDFを開けませんでした。")
      return false
    }
  }

  async function loadPdf(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
      setUploadState("error")
      setUploadError("PDFファイルを選択してください。")
      return
    }

    setUploadState("uploading")
    resetDocumentUi(file.name)

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
      applyLoadedDocument(upload)
      void refreshLibrary(false)
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
    setGradingReportStatus("idle")
    setGradingNotice("")

    const previous = records[String(current.id)]
    const normalizedAnswer = normalizeQuizAnswer(answer)
    const localMatch = [...(previous?.attempts ?? [])]
      .reverse()
      .find((attempt) =>
        attempt.graderVersion === QUIZ_CLIENT_CACHE_VERSION &&
        normalizeQuizAnswer(attempt.answer) === normalizedAnswer
      )
    if (localMatch) {
      setEvaluation(localMatch.evaluation)
      setStatus(localMatch.evaluation.verdict)
      setGradingElapsedMs(0)
      await syncVocabularyFromSource(current.sourceText, current.id)
      setGradingNotice("同じ回答の保存済み採点を再利用しました。LLM/Azureは呼び出さず、単語カードだけ同期しました。")
      setRecords((prev) => {
        const existing = prev[String(current.id)]
        if (!existing) return prev
        return {
          ...prev,
          [String(current.id)]: {
            ...existing,
            answer,
            evaluation: localMatch.evaluation,
            updatedAt: new Date().toISOString(),
          },
        }
      })
      return
    }

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
      const cacheHit = Boolean(data.cache_hit)
      setGradingNotice(cacheHit ? "同じ回答のサーバー保存済み採点を再利用しました。" : "")
      const candidates = Array.isArray(data.vocabulary_candidates) ? data.vocabulary_candidates as VocabularyCandidate[] : []
      void addVocabularyCandidates(candidates, current.id)

      const nextEvaluation: Evaluation = {
        verdict: apiEvaluation.verdict,
        score: apiEvaluation.score,
        feedback: apiEvaluation.feedback,
        referenceTranslation: apiEvaluation.reference_translation,
        referenceReview: apiEvaluation.reference_review
          ? {
              status: String(apiEvaluation.reference_review.status ?? "unchecked"),
              flags: Array.isArray(apiEvaluation.reference_review.flags) ? apiEvaluation.reference_review.flags : [],
              revision: String(apiEvaluation.reference_review.revision ?? ""),
              reviewId: String(apiEvaluation.reference_review.review_id ?? ""),
            }
          : undefined,
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
        semanticUnits: (apiEvaluation.semantic_units ?? []).map(
          (unit: {
            id?: string
            source?: string
            translation?: string
            importance?: SemanticImportance
            status?: SemanticUnitStatus
            note?: string
            earned_points?: number
            max_points?: number
          }) => ({
            id: unit.id ?? "",
            source: unit.source ?? "",
            translation: unit.translation ?? "",
            importance: unit.importance ?? "support",
            status: unit.status ?? "partial",
            note: unit.note ?? "",
            earnedPoints: unit.earned_points ?? 0,
            maxPoints: unit.max_points ?? 0,
          })
        ),
        scoreBreakdown: apiEvaluation.score_breakdown
          ? {
              meaning: apiEvaluation.score_breakdown.meaning ?? 0,
              terminology: apiEvaluation.score_breakdown.terminology ?? 15,
              japanese: apiEvaluation.score_breakdown.japanese ?? 15,
              rawTotal: apiEvaluation.score_breakdown.raw_total ?? apiEvaluation.score,
              total: apiEvaluation.score_breakdown.total ?? apiEvaluation.score,
              capReason: apiEvaluation.score_breakdown.cap_reason ?? "",
            }
          : null,
        japaneseQuality: apiEvaluation.japanese_quality
          ? {
              level: apiEvaluation.japanese_quality.level ?? "natural",
              note: apiEvaluation.japanese_quality.note ?? "",
            }
          : null,
        externalAudit: apiEvaluation.external_audit
          ? {
              provider: apiEvaluation.external_audit.provider ?? "local",
              status: apiEvaluation.external_audit.status ?? "local_only",
              translation: apiEvaluation.external_audit.translation ?? "",
              message: apiEvaluation.external_audit.message ?? "",
              monthUsage: apiEvaluation.external_audit.month_usage ?? 0,
              monthlySoftLimit: apiEvaluation.external_audit.monthly_soft_limit ?? 0,
              cached: Boolean(apiEvaluation.external_audit.cached),
            }
          : null,
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
          graderVersion: QUIZ_CLIENT_CACHE_VERSION,
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
      setGradingNotice("")
      alert(error instanceof Error ? error.message : "採点に失敗しました。")
    }
  }

  async function reportBadGrading() {
    if (!current || !evaluation || gradingReportStatus === "saving") return
    setGradingReportStatus("saving")
    try {
      const response = await fetch(`${API_BASE_URL}/api/quiz/grading-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: documentId ?? "",
          paper_title: paperTitle,
          filename: filename ?? "",
          question_id: current.id,
          page_ref: current.pageRef,
          source_text: current.sourceText,
          user_answer: answer,
          evaluation,
          note: "ユーザーがUIから採点異常として報告",
        }),
      })
      if (!response.ok) throw new Error("改善ログの保存に失敗しました。")
      setGradingReportStatus("saved")
    } catch (error) {
      console.error("quiz grading report error", error)
      setGradingReportStatus("error")
    }
  }

  async function openGradingReportFolder() {
    try {
      await fetch(`${API_BASE_URL}/api/quiz/grading-report/open-folder`, { method: "POST" })
    } catch (error) {
      console.error("open grading report folder error", error)
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
    setGradingReportStatus("idle")
  }

  function openReviewQuestion(index: number) {
    if (index < 0 || index >= questions.length) return
    const nextQuestion = questions[index]
    const record = records[String(nextQuestion.id)]
    setCurrentIndex(index)
    setAnswer(record?.answer ?? "")
    setEvaluation(record?.evaluation ?? null)
    setStatus(record?.evaluation?.verdict ?? "idle")
    setGradingReportStatus("idle")
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

  function jumpToNavigationPosition(position: number) {
    if (!Number.isFinite(position) || position < 0 || position >= navigationTotal) return
    if (reviewSequence) {
      openReviewQuestion(reviewSequence[position])
      return
    }
    openQuestion(position)
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
    setGradingNotice("")
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

  return (
    <main
      className={cn(
        inter.className,
        jetBrainsMono.variable,
        "h-screen overflow-hidden bg-zinc-950 text-zinc-50 antialiased",
        displayPreferences.theme === "light" && "pt-theme-light",
        "selection:bg-indigo-500/20 selection:text-indigo-100"
      )}
      style={{
        "--pt-source-size": `${displayPreferences.sourceSize}px`,
        "--pt-answer-size": `${displayPreferences.answerSize}px`,
        "--pt-feedback-size": `${displayPreferences.feedbackSize}px`,
        "--pt-reference-size": `${displayPreferences.referenceSize}px`,
      } as React.CSSProperties}
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
          onOpenLibrary={() => void refreshLibrary(true)}
          documentReady={Boolean(documentId)}
          rightMode={rightMode}
          translationStatus={documentTranslationStatus}
          activeJobCount={trackedJobs.filter((job) => !isTerminalJob(job)).length}
          unreadJobCount={trackedJobs.filter((job) => isTerminalJob(job) && !job.acknowledged).length}
          onShowJobs={() => setJobCenterOpen((value) => !value)}
          onToggleJapanese={() => { setJapaneseViewMode("layout"); setRightMode((mode) => (mode === "japanese" ? "study" : "japanese")) }}
          vocabularyCount={vocabularyCards.length}
          onToggleVocabulary={() => {
            setRightMode((mode) => (mode === "vocabulary" ? "study" : "vocabulary"))
            void refreshVocabulary()
          }}
          displayPreferences={displayPreferences}
          onDisplayPreferencesChange={setDisplayPreferences}
        />

        <ResizablePanelGroup orientation="horizontal" resizeTargetMinimumSize={{ fine: 18, coarse: 28 }} className="min-h-0 flex-1">
          <ResizablePanel
            id="pdf-reader"
            defaultSize="48%"
            minSize="34%"
            maxSize="64%"
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
              canResume={Boolean(resumeDocumentId && !documentId)}
              onResume={() => { if (resumeDocumentId) void openLibraryDocument(resumeDocumentId) }}
            />
          </ResizablePanel>

          <ResizableHandle
            withHandle
            title="左右にドラッグしてPDFと学習画面の幅を変更（ダブルクリックで初期化）"
            aria-label="PDFと学習画面の表示幅を変更"
            className={cn(
              "relative z-10 w-2 bg-indigo-500/15 transition-colors duration-200 cursor-col-resize hover:bg-indigo-500/35",
              "data-[resize-handle-state=hover]:bg-indigo-500/25",
              "data-[resize-handle-state=drag]:bg-indigo-500/45",
              "after:absolute after:left-1/2 after:top-1/2 after:h-10 after:w-1.5",
              "after:-translate-x-1/2 after:-translate-y-1/2",
              "after:rounded-full after:bg-indigo-400/55 after:transition-colors after:duration-200"
            )}
          />

          <ResizablePanel
            id="study-pane"
            defaultSize="52%"
            minSize="36%"
            maxSize="66%"
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
                onJump={jumpToNavigationPosition}
                isLastQuestion={isLastQuestion}
                score={completedCount}
                evaluation={evaluation}
                attempts={currentAttempts}
                onRetry={startRevision}
                gradingReportStatus={gradingReportStatus}
                onReportGrading={reportBadGrading}
                onOpenGradingReports={openGradingReportFolder}
                gradingElapsedMs={gradingElapsedMs}
                gradingNotice={gradingNotice}
                uploadState={uploadState}
                quizNotice={quizNotice}
                onOpenJapanese={() => { setJapaneseViewMode("layout"); setRightMode("japanese") }}
              />
            ) : rightMode === "vocabulary" ? (
              <VocabularyPanel
                cards={vocabularyCards}
                loading={vocabularyLoading}
                error={vocabularyError}
                onRefresh={() => void refreshVocabulary()}
                onReview={(cardId, direction, known) => reviewVocabularyCard(cardId, direction, known)}
                onBackToStudy={() => setRightMode("study")}
                documentId={documentId}
                sourceContext={current?.sourceText ?? ""}
                onManualAdd={async (source, translation, kind, context) => {
                  const response = await fetch(`${API_BASE_URL}/api/quiz/vocabulary/add`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ cards: [{ source, translation, kind, origin: "manual", context, document_id: documentId ?? "", question_id: current?.id ?? null }] }),
                  })
                  const payload = await response.json().catch(() => null)
                  if (!response.ok) throw new Error(payload?.detail || "語彙の追加に失敗しました")
                  setVocabularyCards(mapVocabularyCards(payload?.cards))
                }}
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
                documentKind={documentKind}
              />
            )}
          </ResizablePanel>
        </ResizablePanelGroup>

        {libraryOpen && (
          <LibraryPanel
            items={libraryItems}
            loading={libraryLoading}
            error={libraryError}
            onClose={() => setLibraryOpen(false)}
            onRefresh={() => void refreshLibrary(false)}
            onOpen={(targetDocumentId) => void openLibraryDocument(targetDocumentId)}
            onExportOffline={exportMobileBundle}
            onOpenGraph={(targetDocumentId) => {
              setKnowledgeGraphInitialDocumentId(targetDocumentId)
              setKnowledgeGraphOpen(true)
            }}
            onSaveNotes={async (targetDocumentId, notes) => {
              const response = await fetch(`${API_BASE_URL}/api/library/${targetDocumentId}/notes`, {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes }),
              })
              const result = await response.json().catch(() => null)
              if (!response.ok) throw new Error(result?.detail || "メモ保存に失敗しました")
              await refreshLibrary(false)
            }}
          />
        )}

        {knowledgeGraphOpen && (
          <KnowledgeGraphPanel
            apiBase={API_BASE_URL}
            initialDocumentId={knowledgeGraphInitialDocumentId}
            onClose={() => setKnowledgeGraphOpen(false)}
            onOpenDocument={(id) => {
              setKnowledgeGraphOpen(false)
              void openLibraryDocument(id)
            }}
          />
        )}

        {jobCenterOpen && (
          <JobCenterPanel jobs={trackedJobs} desktopNotificationsAllowed={desktopNotificationsAllowed}
            onEnableDesktopNotifications={enableDesktopNotifications}
            onClose={() => setJobCenterOpen(false)} onAcknowledge={acknowledgeJob}
            onOpen={openTrackedJob} />
        )}

        {trackedJobs.filter((job) => isTerminalJob(job) && !job.acknowledged).slice(0, 1).map((job) => (
          <div key={job.id} role="status" aria-live="polite"
            className="fixed bottom-5 left-5 z-[70] w-[360px] max-w-[calc(100vw-40px)] rounded-xl border border-indigo-500/30 bg-zinc-900 p-4 shadow-2xl">
            <p className="text-sm font-medium text-zinc-100">{jobStatusLabel(job)}</p>
            <p className="mt-1 truncate text-xs text-zinc-400" title={job.title}>{job.title}</p>
            <div className="mt-3 flex gap-3 text-xs">
              <button onClick={() => openTrackedJob(job)} className="text-indigo-300 hover:underline">結果を確認</button>
              <button onClick={() => acknowledgeJob(job.id)} className="text-zinc-400 hover:underline">閉じる</button>
            </div>
          </div>
        ))}

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
  onOpenLibrary,
  documentReady,
  rightMode,
  translationStatus,
  activeJobCount,
  unreadJobCount,
  onShowJobs,
  onToggleJapanese,
  vocabularyCount,
  onToggleVocabulary,
  displayPreferences,
  onDisplayPreferencesChange,
}: {
  chapter: string
  score: number
  total: number
  reviewCount: number
  reviewMode: boolean
  onToggleReview: () => void
  onReset: () => void
  onOpenLibrary: () => void
  documentReady: boolean
  rightMode: RightPanelMode
  translationStatus: DocumentTranslationStatus
  activeJobCount: number
  unreadJobCount: number
  onShowJobs: () => void
  onToggleJapanese: () => void
  vocabularyCount: number
  onToggleVocabulary: () => void
  displayPreferences: DisplayPreferences
  onDisplayPreferencesChange: React.Dispatch<React.SetStateAction<DisplayPreferences>>
}) {
  const [showDisplaySettings, setShowDisplaySettings] = React.useState(false)
  return (
    <header className="relative z-30 flex h-[72px] shrink-0 items-center justify-between border-b border-white/[0.06] bg-zinc-900/40 px-5 backdrop-blur-sm">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-indigo-500/20 bg-indigo-500/[0.12]">
            <BookOpen className="h-3.5 w-3.5 text-indigo-400" />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[15px] font-semibold tracking-[0.08em] text-zinc-200">
              PeperTranslator
            </span>
          </div>
        </div>

        <div className="h-8 w-px bg-white/[0.07]" />

        <nav className="flex min-w-0 items-center gap-2 text-[14px] text-zinc-500">
          <button
            onClick={onOpenLibrary}
            className="rounded-md px-2 py-1 text-zinc-400 transition-colors hover:bg-white/[0.05] hover:text-zinc-100"
          >
            Library
          </button>
          <ChevronRight className="h-3.5 w-3.5 text-zinc-700" />
          <span className="truncate text-zinc-400">Research Papers</span>
          <ChevronRight className="h-3.5 w-3.5 text-zinc-700" />
          <span className="truncate font-medium text-zinc-200">{chapter}</span>
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onShowJobs} title="別の論文で作業中でも翻訳の進捗と結果を確認"
          className="h-9 rounded-md border border-white/[0.06] bg-white/[0.025] px-3 text-[13px] text-zinc-300 hover:bg-white/[0.05]">
          <Bell className="mr-1.5 h-4 w-4" />ジョブ {activeJobCount}
          {unreadJobCount > 0 && <span className="ml-1 rounded-full bg-indigo-500/25 px-1.5 text-[11px] text-indigo-200">{unreadJobCount}</span>}
        </Button>
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
          onClick={onToggleVocabulary}
          title="論文で出てきた専門用語・一般単語・フレーズ・構文をカードで確認します"
          className={cn(
            "h-9 rounded-md border px-3 text-[13px] transition-all duration-150",
            rightMode === "vocabulary"
              ? "border-indigo-500/25 bg-indigo-500/[0.10] text-indigo-300 hover:bg-indigo-500/[0.14]"
              : "border-white/[0.06] bg-white/[0.025] text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200"
          )}
        >
          <BookOpen className="mr-1.5 h-3.5 w-3.5" />
          語彙 {vocabularyCount}
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

        <div className="relative">
          <Button type="button" variant="ghost" size="sm"
            aria-expanded={showDisplaySettings} aria-controls="pt-display-settings"
            onClick={() => setShowDisplaySettings((value) => !value)}
            className="h-9 rounded-md border border-white/[0.06] bg-white/[0.025] px-3 text-[13px] text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100">
            <Settings2 className="mr-1.5 h-4 w-4" />表示設定
          </Button>
          {showDisplaySettings && (
            <div id="pt-display-settings" role="dialog" aria-label="表示設定" className="pt-display-settings absolute right-0 top-11 z-[60] w-[320px] max-w-[calc(100vw-24px)] rounded-xl border border-white/10 bg-zinc-900 p-4 shadow-2xl">
              <div className="mb-4 flex items-center justify-between gap-2"><p className="text-sm font-semibold text-zinc-100">表示設定</p><button type="button" className="text-xs text-zinc-400 hover:text-zinc-100" onClick={() => setShowDisplaySettings(false)}>閉じる</button></div>
              <p className="mb-2 text-xs text-zinc-400">画面テーマ</p>
              <div className="mb-4 grid grid-cols-2 gap-2">
                {(["dark", "light"] as UiTheme[]).map((theme) => (
                  <button type="button" key={theme} aria-pressed={displayPreferences.theme === theme}
                    onClick={() => onDisplayPreferencesChange((previous) => ({ ...previous, theme }))}
                    className={cn("flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm", displayPreferences.theme === theme ? "border-indigo-500 bg-indigo-500/15 text-indigo-300" : "border-white/10 text-zinc-400")}>
                    {theme === "dark" ? <Moon className="h-4 w-4"/> : <Sun className="h-4 w-4"/>}{theme === "dark" ? "ダーク" : "ライト"}
                  </button>
                ))}
              </div>
              <p className="mb-3 text-xs text-zinc-400">文字サイズ（タイトルや操作ボタンは変更しません）</p>
              {([
                { key: "sourceSize", label: "英文問題", min: 15, max: 28 },
                { key: "answerSize", label: "自分の訳文", min: 14, max: 26 },
                { key: "referenceSize", label: "模範訳", min: 13, max: 24 },
                { key: "feedbackSize", label: "採点解説", min: 12, max: 22 },
              ] as const).map(({ key, label, min, max }) => (
                <label key={key} className="mb-3 block">
                  <span className="mb-1 flex justify-between text-xs text-zinc-300"><span>{label}</span><span className="font-mono">{displayPreferences[key]} px</span></span>
                  <input type="range" min={min} max={max} step={1} value={displayPreferences[key]}
                    onChange={(event) => { const next = Number(event.target.value); onDisplayPreferencesChange((old) => ({ ...old, [key]: next })) }}
                    className="w-full accent-indigo-500"/>
                </label>
              ))}
              <button type="button" onClick={() => onDisplayPreferencesChange(DEFAULT_DISPLAY_PREFERENCES)} className="mt-1 rounded-md border border-white/10 px-3 py-2 text-xs text-zinc-400 hover:bg-white/5">標準設定に戻す</button>
              <p className="mt-3 text-[11px] text-zinc-500">このPCにのみ設定を保存します。PDF原本・学習履歴は変更しません。</p>
            </div>
          )}
        </div>

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
  canResume,
  onResume,
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
  canResume: boolean
  onResume: () => void
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
              <div className="flex h-full flex-col items-center justify-center p-6">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="group flex max-w-sm flex-col items-center rounded-2xl border border-dashed border-white/[0.09] bg-zinc-900/30 px-10 py-12 text-center transition-all hover:border-indigo-500/30 hover:bg-zinc-900/45"
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-indigo-500/15 bg-indigo-500/[0.08]">
                    <FileText className="h-4 w-4 text-indigo-400/75" />
                  </div>
                  <p className="mt-4 text-[14px] font-medium text-zinc-300">PDFを選択して開始</p>
                  <p className="mt-2 text-[12px] leading-relaxed text-zinc-600">
                    英語論文はクイズに、スライドや日本語資料は閲覧用に登録します
                  </p>
                </button>
                {canResume && (
                  <button type="button" onClick={onResume} className="mt-4 text-[12px] text-indigo-300 hover:text-indigo-100">
                    前回の資料を再開する →
                  </button>
                )}
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

function JobCenterPanel({
  jobs, desktopNotificationsAllowed, onEnableDesktopNotifications, onClose, onAcknowledge, onOpen,
}: {
  jobs: TrackedTranslationJob[]
  desktopNotificationsAllowed: boolean
  onEnableDesktopNotifications: () => void
  onClose: () => void
  onAcknowledge: (id: string) => void
  onOpen: (job: TrackedTranslationJob) => void
}) {
  const ordered = [...jobs].sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  const activeCount = jobs.filter((job) => !isTerminalJob(job)).length
  return (
    <aside role="dialog" aria-label="翻訳ジョブ" className="fixed right-5 top-[82px] z-[80] flex max-h-[72vh] w-[390px] max-w-[calc(100vw-40px)] flex-col overflow-hidden rounded-xl border border-white/10 bg-zinc-900 shadow-2xl">
      <div className="flex items-center justify-between border-b border-white/10 p-4">
        <div><p className="text-sm font-semibold text-zinc-100">翻訳ジョブ</p><p className="mt-1 text-xs text-zinc-400">実行中 {activeCount} 件 · 別論文で学習を続けられます</p></div>
        <button onClick={onClose} aria-label="ジョブ一覧を閉じる" className="text-zinc-400 hover:text-zinc-100"><XCircle className="h-4 w-4" /></button>
      </div>
      <div className="border-b border-white/10 px-4 py-3 text-xs text-zinc-400">
        {desktopNotificationsAllowed ? "OS通知：許可済み" : (
          <button onClick={onEnableDesktopNotifications} className="text-indigo-300 hover:underline">OSの完了通知を有効化（任意）</button>
        )}
        <p className="mt-1 text-[11px] text-zinc-500">アプリが開いている間に監視します。PCのスリープ中やアプリ終了後は通知できません。</p>
      </div>
      <div className="min-h-0 overflow-y-auto p-3">
        {!ordered.length && <p className="px-2 py-4 text-sm text-zinc-500">監視対象の翻訳はありません。</p>}
        {ordered.map((job) => (
          <div key={job.id} className="mb-2 rounded-lg border border-white/10 p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 truncate text-sm text-zinc-200" title={job.title}>{job.title}</p>
              {!job.acknowledged && isTerminalJob(job) && <span className="shrink-0 text-[10px] text-indigo-300">新着</span>}
            </div>
            <p className={cn("mt-1 text-xs", job.status === "completed" ? "text-emerald-300" : isTerminalJob(job) ? "text-amber-300" : "text-indigo-300")}>{jobStatusLabel(job)}</p>
            {!isTerminalJob(job) && <div className="mt-2 h-1.5 rounded-full bg-white/10"><div className="h-full rounded-full bg-indigo-400" style={{width: `${job.progress}%`}} /></div>}
            {job.error && <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-[11px] text-zinc-400" title={job.error}>{job.error}</p>}
            <div className="mt-2 flex gap-3 text-xs">
              <button onClick={() => onOpen(job)} className="text-indigo-300 hover:underline">{job.kind === "batch" ? "バッチを確認" : "論文を開く"}</button>
              {isTerminalJob(job) && !job.acknowledged && <button onClick={() => onAcknowledge(job.id)} className="text-zinc-400 hover:underline">確認済み</button>}
            </div>
          </div>
        ))}
      </div>
    </aside>
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
  documentKind,
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
  documentKind: string
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

  if (documentKind === "japanese") {
    return <section className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"><BookOpen className="h-6 w-6 text-indigo-400"/><h3 className="text-lg text-zinc-200">このPDFは日本語資料です</h3><p className="max-w-md text-sm leading-relaxed text-zinc-400">英文翻訳クイズと日本語への再翻訳は行いません。左側のPDFで内容を閲覧してください。Libraryには保存されています。</p><button onClick={onBackToStudy} className="rounded-md border border-white/10 px-3 py-2 text-xs text-zinc-400">学習画面へ戻る</button></section>
  }

  return (
    <section className="flex h-full min-w-0 flex-col bg-zinc-950">
      {documentKind === "slides" && <p className="border-b border-amber-500/15 bg-amber-500/5 px-5 py-3 text-xs leading-relaxed text-amber-200/80">スライドPDFの日本語レイアウト翻訳はベータ版です。図表・箇条書きの品質は未保証で、QA不合格なら停止します。</p>}
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
              {layoutStatus.qa?.quality_gate === "fail" ? "確認用PDF" : "日本語PDF"}
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
  // Phase94: an existing PDF can be viewed as a diagnostic artifact even if
  // Postflight QA fails.  The backend status and QA gate remain unchanged.
  const ready = status.mono_ready && (
    status.status === "completed" ||
    (status.status === "failed" && status.qa?.quality_gate === "fail")
  )
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

  if (productionFailed && !ready) {
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

  if (status.status === "failed" && !ready) {
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

      {status.qa?.quality_gate === "fail" && (
        <div role="alert" className="shrink-0 border-b border-amber-500/20 bg-amber-500/[0.07] px-4 py-2 text-[11px] leading-5 text-amber-200/90">
          このPDFは生成済みですが、品質検査は不合格です（Critical {status.qa.critical_count ?? 0}件 / High {status.qa.high_count ?? 0}件）。
          正式な翻訳完了ではありません。原文と照合し、下部のQA詳細を確認してください。
        </div>
      )}
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
  onJump,
  isLastQuestion,
  score,
  evaluation,
  attempts,
  onRetry,
  gradingReportStatus,
  onReportGrading,
  onOpenGradingReports,
  gradingElapsedMs,
  gradingNotice,
  uploadState,
  quizNotice,
  onOpenJapanese,
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
  onJump: (position: number) => void
  isLastQuestion: boolean
  score: number
  evaluation: Evaluation | null
  attempts: AttemptRecord[]
  onRetry: () => void
  gradingReportStatus: "idle" | "saving" | "saved" | "error"
  onReportGrading: () => void
  onOpenGradingReports: () => void
  gradingElapsedMs: number
  gradingNotice: string
  uploadState: UploadState
  quizNotice: string
  onOpenJapanese: () => void
}) {
  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault()
      submitAnswer()
    }
  }

  function jumpFromInput(value: string) {
    const next = Number(value)
    if (Number.isInteger(next) && next >= 1 && next <= total) onJump(next - 1)
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
          {total > 0 ? (
            <div className="flex items-center gap-1.5 font-mono text-[13px] text-zinc-300">
              <input
                key={`${reviewMode}-${currentIndex}-${total}`}
                type="number"
                min={1}
                max={total}
                defaultValue={currentIndex + 1}
                onBlur={(event) => jumpFromInput(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    jumpFromInput(event.currentTarget.value)
                    event.currentTarget.blur()
                  }
                }}
                title="問題番号を入力してEnterで直接移動できます"
                className="h-7 w-12 rounded-md border border-white/[0.07] bg-black/20 px-1.5 text-center font-mono text-[12px] text-zinc-300 outline-none focus:border-indigo-500/35"
              />
              <span className="text-zinc-600">/ {total}</span>
            </div>
          ) : (
            <span className="font-mono text-[13px] text-zinc-600">0 / 0</span>
          )}
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
            title="前の問題へ"
            className="h-7 w-7 rounded-md text-zinc-600 transition-all duration-150 hover:bg-white/[0.05] hover:text-zinc-300 disabled:text-zinc-800"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            disabled={isLastQuestion || status === "checking"}
            onClick={goNext}
            title="未回答でも次の問題へ移動できます"
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
                {uploadState === "uploading" ? "問題を作成しています" : quizNotice ? "この資料のクイズは生成していません" : "PDFを読み込むと学習を開始できます"}
              </p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-700">
                {quizNotice || "英語本文をページ情報付きで抽出し、翻訳問題として順番に出題します"}
              </p>
              {quizNotice && <button type="button" onClick={onOpenJapanese} className="mt-5 rounded-lg bg-indigo-600/80 px-4 py-2 text-xs text-white hover:bg-indigo-500">PDF日本語版・レイアウト翻訳（試験運用）へ</button>}
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

                <p className="pt-source-text mt-4 max-w-[980px] text-[19px] leading-[1.7] text-zinc-100">
                  {current.sourceText}
                </p>
              </div>
            </section>

            <section className="rounded-xl border border-white/[0.04] bg-transparent px-5 py-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">
                AI Reference
              </p>
              <p className="pt-reference-text mt-3 flex gap-2.5 text-[15px] italic leading-[1.72] text-zinc-400">
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
                    "pt-answer-text bg-zinc-900/60 px-5 py-4 text-[18px] leading-[1.7] text-zinc-100",
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
                    <div className="w-[360px] max-w-[55vw] animate-in rounded-lg border border-indigo-500/15 bg-indigo-500/[0.04] px-3 py-2.5 fade-in duration-200">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400/70" />
                          <span className="text-[12px] text-zinc-400">採点中</span>
                        </div>
                        <span className="font-mono text-[11px] text-zinc-500">{(gradingElapsedMs / 1000).toFixed(1)} s</span>
                      </div>
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.05]">
                        <div className="h-full w-2/5 animate-pulse rounded-full bg-indigo-400/55" />
                      </div>
                      <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
                        同じ英文・同じ回答なら次回は保存済み採点を即時再利用します。
                      </p>
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

            {(status === "correct" || status === "partial" || status === "incorrect") && gradingNotice && (
              <div className="rounded-lg border border-emerald-500/15 bg-emerald-500/[0.04] px-3 py-2 text-[11px] text-emerald-300/75">
                {gradingNotice}
              </div>
            )}

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
                gradingReportStatus={gradingReportStatus}
                onReportGrading={onReportGrading}
                onOpenGradingReports={onOpenGradingReports}
              />
            )}
          </div>
        )}
      </div>


    </section>
  )
}

function VocabularyPanel({
  cards,
  loading,
  error,
  onRefresh,
  onReview,
  onBackToStudy,
  documentId,
  sourceContext,
  onManualAdd,
}: {
  cards: VocabularyCard[]
  loading: boolean
  error: string | null
  onRefresh: () => void
  onReview: (cardId: string, direction: VocabularyDirection, known: boolean) => Promise<void>
  onBackToStudy: () => void
  documentId: string | null
  sourceContext: string
  onManualAdd: (source: string, translation: string, kind: VocabularyKind, context: string) => Promise<void>
}) {
  const [paperOnly, setPaperOnly] = React.useState(Boolean(documentId))
  const [manualOpen, setManualOpen] = React.useState(false)
  const [manualSource, setManualSource] = React.useState("")
  const [manualTranslation, setManualTranslation] = React.useState("")
  const [manualKind, setManualKind] = React.useState<VocabularyKind>("word")
  const [manualError, setManualError] = React.useState("")
  const [manualBusy, setManualBusy] = React.useState(false)
  const [direction, setDirection] = React.useState<VocabularyDirection>("en-ja")
  const [missedOnly, setMissedOnly] = React.useState(false)
  const [kindFilter, setKindFilter] = React.useState<VocabularyKindFilter>("all")
  const [viewMode, setViewMode] = React.useState<"cards" | "list">("cards")
  const [searchText, setSearchText] = React.useState("")
  const [duplicatesOnly, setDuplicatesOnly] = React.useState(false)
  const [index, setIndex] = React.useState(0)
  const [revealed, setRevealed] = React.useState(false)
  const [saving, setSaving] = React.useState(false)

  const baseFiltered = React.useMemo(() => {
    return cards.filter((card) => {
      if (paperOnly && documentId && !card.documentIds.includes(documentId)) return false
      if (kindFilter !== "all" && card.kind !== kindFilter) return false
      if (!missedOnly) return true
      return direction === "en-ja" ? card.wrongEnJa > card.correctEnJa : card.wrongJaEn > card.correctJaEn
    })
  }, [cards, direction, missedOnly, kindFilter, paperOnly, documentId])

  const listFiltered = React.useMemo(() => {
    const query = searchText.trim().toLocaleLowerCase()
    return baseFiltered.filter((card) => {
      if (duplicatesOnly && card.duplicateStatus === "none") return false
      if (!query) return true
      const haystack = [card.source, card.translation, ...card.surfaceForms, ...card.contexts].join("\n").toLocaleLowerCase()
      return haystack.includes(query)
    })
  }, [baseFiltered, searchText, duplicatesOnly])

  React.useEffect(() => {
    setIndex(0)
    setRevealed(false)
  }, [direction, missedOnly, kindFilter, paperOnly, documentId, cards.length])

  const card = baseFiltered[index] ?? null
  const front = card ? (direction === "en-ja" ? card.source : card.translation) : ""
  const back = card ? (direction === "en-ja" ? card.translation : card.source) : ""
  const knownCount = cards.reduce((sum, item) => sum + item.correctEnJa + item.correctJaEn, 0)
  const missedCount = cards.reduce((sum, item) => sum + item.wrongEnJa + item.wrongJaEn, 0)
  const duplicateCount = cards.filter((item) => item.duplicateStatus !== "none").length
  const kindLabels: Record<VocabularyKind, string> = {
    term: "専門用語",
    word: "一般単語",
    phrase: "フレーズ",
    pattern: "構文",
  }
  const latestContext = card ? (card.contexts[card.contexts.length - 1] ?? "") : ""
  const latestSurface = card ? (card.surfaceForms[card.surfaceForms.length - 1] ?? "") : ""

  async function record(known: boolean) {
    if (!card || saving) return
    setSaving(true)
    try {
      await onReview(card.cardId, direction, known)
      setRevealed(false)
      setIndex((value) => baseFiltered.length > 1 ? (value + 1) % baseFiltered.length : 0)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flex h-full min-w-0 flex-col bg-zinc-950">
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.06] bg-zinc-900/30 px-5">
        <div>
          <p className="text-[12px] font-medium uppercase tracking-[0.18em] text-zinc-500">Vocabulary</p>
          <p className="mt-1 text-[11px] text-zinc-600">原文から安全に抽出した単語・専門用語・フレーズ・構文</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setViewMode("cards")} className={cn("rounded-md border px-3 py-1.5 text-[11px]", viewMode === "cards" ? "border-indigo-500/25 bg-indigo-500/10 text-indigo-300" : "border-white/[0.06] text-zinc-500")}>カード</button>
          <button onClick={() => setViewMode("list")} className={cn("rounded-md border px-3 py-1.5 text-[11px]", viewMode === "list" ? "border-indigo-500/25 bg-indigo-500/10 text-indigo-300" : "border-white/[0.06] text-zinc-500")}>一覧</button>
          <button onClick={() => setDirection("en-ja")} className={cn("rounded-md border px-3 py-1.5 text-[11px]", direction === "en-ja" ? "border-indigo-500/25 bg-indigo-500/10 text-indigo-300" : "border-white/[0.06] text-zinc-500")}>英 → 日</button>
          <button onClick={() => setDirection("ja-en")} className={cn("rounded-md border px-3 py-1.5 text-[11px]", direction === "ja-en" ? "border-indigo-500/25 bg-indigo-500/10 text-indigo-300" : "border-white/[0.06] text-zinc-500")}>日 → 英</button>
          <button onClick={() => setMissedOnly((value) => !value)} className={cn("rounded-md border px-3 py-1.5 text-[11px]", missedOnly ? "border-amber-500/25 bg-amber-500/10 text-amber-300" : "border-white/[0.06] text-zinc-500")}>苦手だけ</button>
          <button onClick={onRefresh} className="rounded-md border border-white/[0.06] px-3 py-1.5 text-[11px] text-zinc-500 hover:text-zinc-200">更新</button>
          <button onClick={onBackToStudy} className="rounded-md px-3 py-1.5 text-[11px] text-zinc-500 hover:text-zinc-200">学習へ戻る</button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-8">
        <div className="mx-auto max-w-5xl">
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded-lg border border-white/[0.06] bg-zinc-900/35 px-4 py-3"><p className="text-[10px] text-zinc-600">カード</p><p className="mt-1 font-mono text-lg text-zinc-300">{cards.length}</p></div>
            <div className="rounded-lg border border-white/[0.06] bg-zinc-900/35 px-4 py-3"><p className="text-[10px] text-zinc-600">✓ 回数</p><p className="mt-1 font-mono text-lg text-emerald-300/80">{knownCount}</p></div>
            <div className="rounded-lg border border-white/[0.06] bg-zinc-900/35 px-4 py-3"><p className="text-[10px] text-zinc-600">× 回数</p><p className="mt-1 font-mono text-lg text-amber-300/80">{missedCount}</p></div>
            <div className="rounded-lg border border-white/[0.06] bg-zinc-900/35 px-4 py-3"><p className="text-[10px] text-zinc-600">重複候補</p><p className={cn("mt-1 font-mono text-lg", duplicateCount ? "text-amber-300/80" : "text-zinc-500")}>{duplicateCount}</p></div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {([
              ["all", "すべて"],
              ["term", "専門用語"],
              ["word", "一般単語"],
              ["phrase", "フレーズ"],
              ["pattern", "構文"],
            ] as [VocabularyKindFilter, string][]).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setKindFilter(value)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-[11px] transition-colors",
                  kindFilter === value
                    ? "border-indigo-500/25 bg-indigo-500/10 text-indigo-300"
                    : "border-white/[0.06] text-zinc-500 hover:text-zinc-200"
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <button disabled={!documentId} onClick={() => setPaperOnly((v) => !v)} className={cn("rounded-lg border px-3 py-2", paperOnly ? "border-indigo-400/30 bg-indigo-500/10 text-indigo-200" : "border-white/10 text-zinc-400", !documentId && "opacity-40")}>{paperOnly ? "✓ この論文のみ" : "この論文のみ表示"}</button>
            <button onClick={() => setManualOpen((v) => !v)} className="rounded-lg border border-white/10 px-3 py-2 text-zinc-300 hover:text-white">＋ 語彙を手動追加</button>
            <span className="text-zinc-600">自動登録は辞書・定型パターンに一致した語だけです</span>
          </div>
          {manualOpen && (
            <form className="mt-3 grid gap-2 rounded-xl border border-indigo-500/15 bg-zinc-900/50 p-4" onSubmit={async (event) => {
              event.preventDefault()
              if (!manualSource.trim() || !manualTranslation.trim()) return
              setManualBusy(true); setManualError("")
              try {
                await onManualAdd(manualSource.trim(), manualTranslation.trim(), manualKind, sourceContext)
                setManualSource(""); setManualTranslation(""); setManualOpen(false)
              } catch (error) { setManualError(error instanceof Error ? error.message : "登録エラー") }
              finally { setManualBusy(false) }
            }}>
              <p className="text-sm text-zinc-200">単語・フレーズを登録（現在の論文と紐付け）</p>
              <input required maxLength={240} value={manualSource} onChange={(e) => setManualSource(e.target.value)} placeholder="English" className="rounded-md border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" />
              <input required maxLength={240} value={manualTranslation} onChange={(e) => setManualTranslation(e.target.value)} placeholder="日本語訳（文脈に合う意味）" className="rounded-md border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" />
              <div className="flex items-center gap-2"><select value={manualKind} onChange={(e) => setManualKind(e.target.value as VocabularyKind)} className="rounded-md border border-white/10 bg-zinc-950 px-2 py-2 text-xs text-zinc-200"><option value="word">単語</option><option value="term">専門用語</option><option value="phrase">フレーズ</option><option value="pattern">構文</option></select><button type="submit" disabled={manualBusy} className="rounded-md bg-indigo-600 px-3 py-2 text-xs text-white disabled:opacity-40">保存</button></div>
              {manualError && <p className="text-xs text-red-300">{manualError}</p>}
            </form>
          )}
          {loading ? (
            <div className="mt-20 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-indigo-400/60" /></div>
          ) : error ? (
            <div className="mt-12 rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300/80">{error}</div>
          ) : viewMode === "list" ? (
            <div className="mt-6">
              <div className="flex flex-wrap items-center gap-3">
                <div className="relative min-w-[260px] flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-600" />
                  <input
                    value={searchText}
                    onChange={(event) => setSearchText(event.target.value)}
                    placeholder="英語・日本語・本文形・Contextを検索"
                    className="h-10 w-full rounded-lg border border-white/[0.07] bg-zinc-900/40 pl-12 pr-3 text-sm text-zinc-300 outline-none placeholder:text-zinc-700 focus:border-indigo-500/30"
                  />
                </div>
                <button
                  onClick={() => setDuplicatesOnly((value) => !value)}
                  className={cn("h-10 rounded-lg border px-4 text-[11px]", duplicatesOnly ? "border-amber-500/25 bg-amber-500/10 text-amber-300" : "border-white/[0.07] text-zinc-500")}
                >
                  重複候補だけ
                </button>
                <span className="text-[11px] text-zinc-600">{listFiltered.length} / {cards.length} 件</span>
              </div>

              <div className="mt-4 overflow-hidden rounded-xl border border-white/[0.06]">
                <div className="grid grid-cols-[minmax(150px,1.1fr)_minmax(180px,1.4fr)_90px_70px_70px_90px] gap-3 border-b border-white/[0.06] bg-zinc-900/55 px-4 py-2 text-[10px] uppercase tracking-[0.12em] text-zinc-600">
                  <span>English</span><span>日本語</span><span>種類</span><span>出現</span><span>論文</span><span>履歴</span>
                </div>
                {listFiltered.length === 0 ? (
                  <div className="px-4 py-12 text-center text-sm text-zinc-600">条件に一致するカードはありません。</div>
                ) : (
                  <div className="divide-y divide-white/[0.045]">
                    {listFiltered.map((item) => {
                      const correct = item.correctEnJa + item.correctJaEn
                      const wrong = item.wrongEnJa + item.wrongJaEn
                      return (
                        <div key={item.cardId} className="grid grid-cols-[minmax(150px,1.1fr)_minmax(180px,1.4fr)_90px_70px_70px_90px] gap-3 px-4 py-3 text-xs text-zinc-400 hover:bg-white/[0.02]">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="truncate font-medium text-zinc-200">{item.source}</span>
                              {item.duplicateStatus !== "none" && (
                                <span className={cn("shrink-0 rounded border px-1.5 py-0.5 text-[9px]", item.duplicateStatus === "conflict" ? "border-red-500/25 bg-red-500/10 text-red-300" : "border-amber-500/25 bg-amber-500/10 text-amber-300")}>
                                  {item.duplicateStatus === "conflict" ? "訳違い" : "表記重複"}
                                </span>
                              )}
                            </div>
                            {item.surfaceForms.length > 0 && <p className="mt-1 truncate text-[10px] text-zinc-650">本文形: {item.surfaceForms.join(" / ")}</p>}
                          </div>
                          <span className="min-w-0 break-words text-zinc-300">{item.translation}</span>
                          <span className="text-zinc-500">{kindLabels[item.kind]}</span>
                          <span className="font-mono text-zinc-500">{item.seenCount}</span>
                          <span className="font-mono text-zinc-500">{item.documentIds.length}</span>
                          <span className="font-mono"><span className="text-emerald-400/70">✓{correct}</span> <span className="text-amber-400/70">×{wrong}</span></span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
              <p className="mt-3 text-[10px] leading-relaxed text-zinc-650">完全一致は保存時に自動統合します。「表記重複」は大文字小文字・ハイフン・単複などを正規化すると同じ語になる候補、「訳違い」は同じ英語候補に別の日本語が保存されている候補です。</p>
            </div>
          ) : !card ? (
            <div className="mt-20 text-center">
              <BookOpen className="mx-auto h-6 w-6 text-zinc-700" />
              <p className="mt-4 text-sm text-zinc-400">{missedOnly ? "苦手カードはありません" : "単語カードはまだありません"}</p>
              <p className="mt-2 text-xs text-zinc-600">クイズを採点すると、原文に出た安全な語彙・フレーズ・構文が自動で追加されます。</p>
            </div>
          ) : (
            <div className="mx-auto mt-8 max-w-3xl">
              <div className="mb-3 flex items-center justify-between text-[11px] text-zinc-600">
                <span>{index + 1} / {baseFiltered.length}</span>
                <span>{direction === "en-ja" ? "English → 日本語" : "日本語 → English"}</span>
              </div>
              <button
                onClick={() => setRevealed(true)}
                className="flex min-h-[300px] w-full flex-col items-center justify-center rounded-2xl border border-white/[0.08] bg-zinc-900/50 px-10 py-12 text-center transition-colors hover:border-indigo-500/20"
              >
                <div className="flex items-center gap-2">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-zinc-600">{revealed ? "Answer" : "Card"}</p>
                  <span className="rounded-full border border-white/[0.07] bg-white/[0.025] px-2 py-0.5 text-[10px] text-zinc-500">
                    {kindLabels[card.kind]}
                  </span>
                </div>
                <p className="mt-6 text-2xl leading-relaxed text-zinc-100">{front}</p>
                {!revealed && latestSurface && latestSurface.toLocaleLowerCase() !== card.source.toLocaleLowerCase() && (
                  <p className="mt-3 text-[11px] text-zinc-600">本文形: {latestSurface}</p>
                )}
                {revealed ? (
                  <div className="mt-8 w-full border-t border-white/[0.06] pt-8">
                    <p className="text-xl leading-relaxed text-indigo-200">{back}</p>
                    {latestContext && (
                      <div className="mt-8 rounded-lg border border-white/[0.05] bg-black/15 px-4 py-3 text-left">
                        <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">Context</p>
                        <p className="mt-2 text-xs leading-relaxed text-zinc-500">{latestContext}</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="mt-8 text-xs text-zinc-600">クリックして答えを見る</p>
                )}
              </button>

              {revealed && (
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <Button disabled={saving} onClick={() => void record(false)} variant="ghost" className="h-12 border border-amber-500/20 bg-amber-500/[0.05] text-amber-300 hover:bg-amber-500/10">× もう一度</Button>
                  <Button disabled={saving} onClick={() => void record(true)} className="h-12 bg-emerald-600 text-white hover:bg-emerald-500">✓ 覚えた</Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
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
  gradingReportStatus,
  onReportGrading,
  onOpenGradingReports,
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
  gradingReportStatus: "idle" | "saving" | "saved" | "error"
  onReportGrading: () => void
  onOpenGradingReports: () => void
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
  const semanticUnits = evaluation.semanticUnits ?? []
  const [showAllUnits, setShowAllUnits] = React.useState(false)
  const hiddenCorrectUnits = semanticUnits.filter((unit) => unit.status === "correct").length
  const shownUnits = showAllUnits ? semanticUnits : semanticUnits.filter((unit) => unit.status !== "correct")
  const breakdown = evaluation.scoreBreakdown ?? null
  const japaneseQuality = evaluation.japaneseQuality ?? null
  const externalAudit = evaluation.externalAudit ?? null
  const unitStatusLabel: Record<SemanticUnitStatus, string> = {
    correct: "保持",
    partial: "一部",
    missing: "欠落",
    wrong: "誤り",
  }
  const importanceLabel: Record<SemanticImportance, string> = {
    core: "主要",
    support: "補足",
    detail: "詳細",
  }

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

          <p className="pt-feedback-text mt-3 max-w-[760px] whitespace-pre-wrap text-[16px] leading-[1.72] text-zinc-300">
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
        {externalAudit && (
          <div
            className={cn(
              "rounded-xl border px-3.5 py-3",
              externalAudit.status === "verified" && "border-emerald-500/[0.13] bg-emerald-500/[0.045]",
              externalAudit.status === "minor_difference" && "border-indigo-500/[0.14] bg-indigo-500/[0.045]",
              externalAudit.status === "disagreement" && "border-amber-500/[0.16] bg-amber-500/[0.05]",
              ["local_only", "quota_exhausted", "unavailable"].includes(externalAudit.status) && "border-white/[0.06] bg-white/[0.02]"
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {externalAudit.status === "verified" ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400/80" />
                ) : externalAudit.status === "disagreement" ? (
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400/80" />
                ) : (
                  <ShieldCheck className="h-3.5 w-3.5 text-indigo-300/70" />
                )}
                <span className="text-[12px] font-medium text-zinc-300">
                  {externalAudit.status === "verified"
                    ? "独立監査済み · Azure"
                    : externalAudit.status === "minor_difference"
                      ? "独立監査 · 表現差のみ"
                      : externalAudit.status === "disagreement"
                        ? "独立監査で意味差あり"
                        : externalAudit.status === "quota_exhausted"
                          ? "Azure無料枠ソフト上限 → ローカル監査"
                          : externalAudit.status === "unavailable"
                            ? "Azure一時利用不可 → ローカル監査"
                            : "ローカル監査"}
                </span>
              </div>
              {externalAudit.monthlySoftLimit > 0 && externalAudit.provider === "azure" && (
                <span className="font-mono text-[10px] text-zinc-600">
                  {externalAudit.monthUsage.toLocaleString()} / {externalAudit.monthlySoftLimit.toLocaleString()} chars
                </span>
              )}
            </div>
            {externalAudit.message && (
              <p className="mt-2 text-[11px] leading-[1.65] text-zinc-500">{externalAudit.message}</p>
            )}
            {externalAudit.status === "disagreement" && (
              <div className="mt-2 space-y-2">
                <p className="text-[11px] leading-[1.65] text-amber-200/65">
                  この差異だけで減点は追加していません。現在の採点はローカル基準を継続し、改善ログ対象として扱えます。
                </p>
                {externalAudit.translation && (
                  <div className="rounded-lg border border-amber-500/[0.10] bg-black/10 px-3 py-2.5">
                    <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-zinc-600">Independent MT</p>
                    <p className="mt-1.5 text-[12px] leading-[1.65] text-zinc-400">{externalAudit.translation}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {breakdown && (
          <div className="rounded-xl border border-white/[0.055] bg-black/10 px-3.5 py-3.5">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[13px] font-medium text-zinc-400">採点内訳</p>
              <span className="font-mono text-[11px] text-zinc-600">意味を70点、用語15点、日本語15点で評価</span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {[
                ["意味・情報", breakdown.meaning, 70],
                ["専門用語", breakdown.terminology, 15],
                ["日本語", breakdown.japanese, 15],
              ].map(([label, value, max]) => (
                <div key={String(label)} className="rounded-lg border border-white/[0.05] bg-white/[0.018] px-3 py-2.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[11px] text-zinc-500">{label}</span>
                    <span className="font-mono text-[13px] text-zinc-300">{value}/{max}</span>
                  </div>
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.05]">
                    <div
                      className="h-full rounded-full bg-indigo-400/70"
                      style={{ width: `${Math.max(0, Math.min(100, (Number(value) / Number(max)) * 100))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            {japaneseQuality?.note && japaneseQuality.level !== "natural" && (
              <div className="mt-3 rounded-lg border border-white/[0.05] bg-white/[0.018] px-3 py-2.5">
                <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-zinc-600">日本語品質 · {japaneseQuality.level}</p>
                <p className="pt-feedback-text mt-1.5 text-[12px] leading-[1.65] text-zinc-400">{japaneseQuality.note}</p>
              </div>
            )}
            {breakdown.capReason && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/[0.12] bg-amber-500/[0.045] px-3 py-2.5">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400/80" />
                <p className="text-[12px] leading-[1.65] text-amber-200/70">
                  素点 {breakdown.rawTotal} 点 → {breakdown.total} 点。{breakdown.capReason}
                </p>
              </div>
            )}
          </div>
        )}

        {semanticUnits.length > 0 && (
          <div className="border-t border-white/[0.05] pt-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[13px] font-medium text-zinc-400">意味単位ごとの答え合わせ</p>
                <p className="mt-1 text-[11px] text-zinc-600">模範訳の表面形ではなく、原文の情報が保持できたかを判定します</p>
              </div>
              <span className="font-mono text-[11px] text-zinc-600">{semanticUnits.reduce((sum, unit) => sum + unit.earnedPoints, 0)}/70</span>
            </div>
            {hiddenCorrectUnits > 0 && <button type="button" onClick={() => setShowAllUnits((v) => !v)} className="mt-3 rounded-md border border-white/10 px-3 py-2 text-xs text-zinc-400 hover:text-white">{showAllUnits ? "保持した項目を折りたたむ" : `保持済み ${hiddenCorrectUnits} 件を表示（詳細）`}</button>}
            {shownUnits.length === 0 && <p className="mt-3 text-xs text-emerald-300/70">主要な情報は保持されています。必要なら詳細を展開してください。</p>}
            <div className="mt-3 grid gap-2">
              {shownUnits.map((unit) => (
                <div
                  key={unit.id}
                  className={cn(
                    "rounded-lg border px-3.5 py-3",
                    unit.status === "correct" && "border-emerald-500/[0.13] bg-emerald-500/[0.045]",
                    unit.status === "partial" && "border-amber-500/[0.15] bg-amber-500/[0.045]",
                    (unit.status === "missing" || unit.status === "wrong") && "border-red-500/[0.14] bg-red-500/[0.045]"
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "rounded-md border px-2 py-0.5 text-[10px] font-medium",
                        unit.status === "correct" && "border-emerald-500/[0.16] text-emerald-300/80",
                        unit.status === "partial" && "border-amber-500/[0.16] text-amber-300/80",
                        (unit.status === "missing" || unit.status === "wrong") && "border-red-500/[0.16] text-red-300/80"
                      )}>
                        {unitStatusLabel[unit.status]}
                      </span>
                      <span className="rounded-md border border-white/[0.06] px-2 py-0.5 text-[10px] text-zinc-600">
                        {importanceLabel[unit.importance]}
                      </span>
                    </div>
                    <span className="font-mono text-[11px] text-zinc-500">{unit.earnedPoints}/{unit.maxPoints}</span>
                  </div>
                  <p className="pt-feedback-text mt-2.5 font-mono text-[12px] leading-[1.65] text-zinc-400">{unit.source}</p>
                  <p className="pt-feedback-text mt-1.5 text-[13px] leading-[1.65] text-zinc-300">→ {unit.translation}</p>
                  {unit.note && (
                    <p className="pt-feedback-text mt-2 text-[12px] leading-[1.65] text-zinc-500">{unit.note}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {(evaluation.issues.length > 0 || hasLegacyDetails) && (
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="mr-1 text-[13px] font-medium text-zinc-400">補足フィードバック</p>

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

                    <p className="pt-feedback-text mt-2 text-[14px] leading-[1.7] text-zinc-300">
                      {issue.message}
                    </p>

                    {issue.suggestion && (
                      <p className="pt-feedback-text mt-1.5 text-[13px] leading-[1.65] text-zinc-500">
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
                  <p key={`missing-${index}`} className="pt-feedback-text text-[14px] leading-[1.7] text-zinc-300">
                    <span className="mr-2 text-red-400">未訳・脱落</span>
                    {item}
                  </p>
                ))}
                {evaluation.meaningErrors.map((item, index) => (
                  <p key={`meaning-${index}`} className="pt-feedback-text text-[14px] leading-[1.7] text-zinc-300">
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
              <p className="pt-feedback-text mt-2 text-[14px] leading-[1.7] text-zinc-400">
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
                    <p className="pt-feedback-text mt-2 text-[12px] leading-[1.65] text-zinc-500">
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
          {evaluation.referenceReview?.status === "editorially_reviewed" && (
            <p className="mt-2 text-[11px] text-zinc-500">原文照合済みの表示用校閲訳（採点用の固定ルーブリックとは独立）</p>
          )}
          {evaluation.referenceReview?.status === "needs_review" && (
            <div className="mt-2 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[12px] text-amber-300">
              模範訳は要確認です。正解例としてそのまま暗記しないでください。
              {(evaluation.referenceReview.flags ?? []).map((flag, index) => (
                <p key={index} className="mt-1">{flag}</p>
              ))}
            </div>
          )}
          <p className="pt-reference-text mt-3 text-[16px] leading-[1.72] text-zinc-300">
            {evaluation.referenceTranslation}
          </p>
        </div>

        {semanticUnits.length === 0 && evaluation.keyPoints.length > 0 && (
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
                    <p className="pt-feedback-text text-[13px] leading-[1.6] text-zinc-300">{point.source}</p>
                    <p className="pt-feedback-text mt-1.5 text-[13px] leading-[1.6] text-zinc-500">
                      → {point.translation || "日本語対応は再採点で更新されます"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex min-h-10 items-center justify-between border-t border-white/[0.05] pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onRetry}
              className="h-9 rounded-lg border border-white/[0.06] bg-white/[0.025] px-3.5 text-[12px] text-zinc-400 transition-all duration-150 hover:bg-white/[0.05] hover:text-zinc-200"
            >
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              訳文を修正して再採点
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={gradingReportStatus === "saving" || gradingReportStatus === "saved"}
              onClick={onReportGrading}
              className="h-9 rounded-lg border border-red-500/[0.10] bg-red-500/[0.025] px-3 text-[12px] text-red-300/70 hover:bg-red-500/[0.06] hover:text-red-200 disabled:opacity-60"
            >
              <AlertTriangle className="mr-1.5 h-3.5 w-3.5" />
              {gradingReportStatus === "saving" ? "保存中…" : gradingReportStatus === "saved" ? "改善ログに保存済み" : gradingReportStatus === "error" ? "保存失敗・再試行" : "採点がおかしい"}
            </Button>
            {gradingReportStatus === "saved" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onOpenGradingReports}
                className="h-9 rounded-lg px-2.5 text-[12px] text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300"
              >
                <FolderOpen className="mr-1.5 h-3.5 w-3.5" />
                改善ログを開く
              </Button>
            )}
          </div>

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

function LibraryPanel({
  items,
  loading,
  error,
  onClose,
  onRefresh,
  onOpen,
  onSaveNotes,
  onExportOffline,
  onOpenGraph,
}: {
  items: LibraryItem[]
  loading: boolean
  error: string | null
  onClose: () => void
  onRefresh: () => void
  onOpen: (documentId: string) => void
  onSaveNotes: (documentId: string, notes: string) => Promise<void>
  onExportOffline: (documentId: string) => Promise<void>
  onOpenGraph: (documentId: string | null) => void
}) {
  const [query, setQuery] = React.useState("")
  const [searchScope, setSearchScope] = React.useState<"all" | "notes" | "bibliography">("all")
  const [sortMode, setSortMode] = React.useState<"recent" | "title" | "noted">("recent")
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [editingId, setEditingId] = React.useState<string | null>(null)
  const [draftNote, setDraftNote] = React.useState("")
  const [savingNote, setSavingNote] = React.useState(false)
  const [noteError, setNoteError] = React.useState("")
  const [previewError, setPreviewError] = React.useState(false)
  const [exportingOfflineId, setExportingOfflineId] = React.useState<string | null>(null)
  const [offlineExportError, setOfflineExportError] = React.useState("")
  const [offlineExportNotice, setOfflineExportNotice] = React.useState("")
  async function saveOfflineZip(targetDocumentId: string) {
    setExportingOfflineId(targetDocumentId)
    setOfflineExportError("")
    setOfflineExportNotice("")
    try {
      await onExportOffline(targetDocumentId)
      setOfflineExportNotice("オフライン持ち出しZIPを保存しました。スマホへコピーして展開してください。")
    } catch (error) {
      setOfflineExportError(error instanceof Error ? error.message : "持ち出しZIPの作成に失敗しました")
    } finally {
      setExportingOfflineId(null)
    }
  }
  const filtered = React.useMemo(() => {
    const tokens = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
    return items.filter((item) => {
      const metadata = [item.title, item.doi ?? "", ...(item.filenames ?? [])].join("\n")
      const notes = item.notes ?? ""
      if (searchScope === "notes" && !notes.trim()) return false
      const haystack = (searchScope === "notes" ? notes : searchScope === "bibliography" ? metadata : `${metadata}\n${notes}`).toLocaleLowerCase()
      return tokens.every((token) => haystack.includes(token))
    }).sort((a, b) => {
      if (sortMode === "noted") {
        const noteDelta = Number(Boolean(b.notes?.trim())) - Number(Boolean(a.notes?.trim()))
        if (noteDelta) return noteDelta
      }
      if (sortMode === "title") return a.title.localeCompare(b.title, "ja")
      return (Date.parse(b.last_opened_at || b.added_at) || 0) - (Date.parse(a.last_opened_at || a.added_at) || 0)
    })
  }, [items, query, searchScope, sortMode])
  const selected = filtered.find((item) => item.document_id === selectedId) ?? filtered[0] ?? null
  React.useEffect(() => { setPreviewError(false) }, [selected?.document_id])
  function quizProgress(documentId: string) {
    const session = readSavedSession(documentId)
    if (!session) return 0
    return Object.values(session.records).filter((record) => (record.attempts?.length ?? 0) > 0).length
  }
  function visibleTitle(item: LibraryItem) {
    return /^[a-f0-9]{10,64}$/i.test(item.title) ? (item.filenames[item.filenames.length - 1] || item.title) : item.title
  }

  return (
    <div className="fixed inset-0 z-50 flex bg-black/70 backdrop-blur-sm" role="presentation">
      <section role="dialog" aria-modal="true" aria-label="Library 論文と研究メモ" className="pt-library-dialog m-auto flex h-[94vh] w-[96vw] max-w-[1500px] flex-col overflow-hidden rounded-2xl border border-white/[0.10] bg-zinc-950 shadow-2xl">
        <div className="flex min-h-[72px] shrink-0 items-center justify-between border-b border-white/[0.07] px-5">
          <div><h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-100"><BookOpen className="h-5 w-5 text-indigo-400" />Library <span className="text-xs font-normal text-zinc-500">{items.length} 資料</span></h2>
            <p className="mt-1 text-xs text-zinc-500">左側で選択 → 右側で大きく確認してから開く。メモはローカル保存。</p>
          </div>
          <div className="flex items-center gap-2"><Button variant="ghost" size="sm" onClick={() => onOpenGraph(selected?.document_id ?? null)} className="h-9 border border-indigo-500/40 text-indigo-200"><GitBranch className="mr-1.5 h-4 w-4"/>知識グラフ</Button><Button variant="ghost" size="sm" onClick={onRefresh} disabled={loading} className="h-9 border border-white/10 text-zinc-400"><RotateCcw className={cn("mr-1.5 h-4 w-4", loading && "animate-spin")}/>更新</Button><Button variant="ghost" size="sm" onClick={onClose} className="h-9 border border-white/10 text-zinc-300">閉じる</Button></div>
        </div>
        <div className="shrink-0 space-y-3 border-b border-white/[0.07] px-5 py-3">
          <label htmlFor="pt-library-search" className="block text-xs text-zinc-400">資料の検索</label>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-[220px] flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500"/><input id="pt-library-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="検索語を入力（例：磁場分布、REBCO、4 mm）" className="h-11 w-full rounded-lg border border-white/10 bg-zinc-900/60 pl-10 pr-3 text-sm text-zinc-100 placeholder:text-zinc-500"/></div>
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-white/10 p-1" aria-label="検索対象">
              {([ ["all", "全項目"], ["notes", "メモのみ"], ["bibliography", "書誌情報のみ"] ] as const).map(([scope, label]) => <button key={scope} type="button" aria-pressed={searchScope === scope} onClick={() => setSearchScope(scope)} className={cn("rounded-md px-3 py-2 text-xs", searchScope === scope ? "bg-indigo-600 text-white" : "text-zinc-400 hover:bg-white/5")}>{label}</button>)}
            </div>
            <select aria-label="資料の並び順" value={sortMode} onChange={(event) => setSortMode(event.target.value as typeof sortMode)} className="h-10 rounded-lg border border-white/10 bg-zinc-900 px-3 text-xs text-zinc-200">
              <option value="recent">最近開いた順</option><option value="title">タイトル順</option><option value="noted">メモあり優先</option>
            </select>
          </div>
          <p className="text-[11px] text-zinc-500">{filtered.length} 件表示。書誌情報＝タイトル・DOI・ファイル名。本文全文は検索しません。メモのみではメモ未登録の資料を除外します。</p>
        </div>
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <div className="min-h-0 w-full shrink-0 overflow-y-auto border-b border-white/[0.08] p-3 lg:w-[38%] lg:border-b-0 lg:border-r" aria-label="資料一覧">
            {loading && items.length === 0 ? <div className="p-7 text-sm text-zinc-500"><Loader2 className="mr-2 inline h-4 w-4 animate-spin"/>読み込み中</div>
              : error ? <div className="p-4 text-sm text-red-400">{error}</div>
                : filtered.length === 0 ? <div className="p-6 text-sm text-zinc-500">該当する資料がありません。検索対象とメモ登録状況を確認してください。</div>
                  : <div className="space-y-2">{filtered.map((item) => {
                    const active = selected?.document_id === item.document_id
                    return <button key={item.paper_key} type="button" aria-pressed={active} onClick={() => { setSelectedId(item.document_id); setEditingId(null); setNoteError("") }} className={cn("w-full rounded-xl border p-3 text-left transition-colors", active ? "border-indigo-500/55 bg-indigo-500/10" : "border-white/[0.06] bg-zinc-900/40 hover:bg-white/[0.06]")}>
                      <div className="flex items-start gap-3"><FileText className="mt-1 h-4 w-4 shrink-0 text-indigo-400"/><div className="min-w-0 flex-1"><p className="line-clamp-2 text-[14px] font-medium leading-relaxed text-zinc-200">{visibleTitle(item)}</p><p className="mt-1 truncate text-xs text-zinc-500">{item.filenames.at(-1) || item.document_id}</p><p className="mt-2 flex flex-wrap gap-2 text-[11px] text-zinc-500"><span>{item.page_count}ページ</span><span>Quiz {quizProgress(item.document_id)}/{item.total_chunks}</span>{item.layout_ready ? <span className="text-emerald-400">翻訳済</span> : item.mono_ready && item.quality_gate === "fail" ? <span className="text-amber-300">確認用PDFあり（QA不合格）</span> : null}{item.notes?.trim() && <span className="text-indigo-300">メモあり</span>}</p>{item.notes?.trim() && <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-zinc-400">{item.notes}</p>}</div><ChevronRight className={cn("h-4 w-4 shrink-0", active ? "text-indigo-400" : "text-zinc-600")}/></div>
                    </button>
                  })}</div>}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4 lg:p-6" aria-label="選択した資料の詳細">
            {!selected ? <div className="flex h-full items-center justify-center text-sm text-zinc-500">左の一覧から資料を選択してください。</div> : <div className="mx-auto flex max-w-[850px] flex-col items-center gap-4">
              <h3 className="w-full text-center text-lg font-semibold leading-relaxed text-zinc-100">{visibleTitle(selected)}</h3>
              <div className="flex w-full max-w-[720px] items-center justify-center rounded-xl border border-white/10 bg-zinc-900/60 p-3" style={{ minHeight: 240 }}>
                {previewError ? <div className="p-8 text-center text-sm text-zinc-500">表紙を表示できません。PDF本体は「開く」から確認できます。</div>
                  : <img key={selected.document_id} loading="lazy" src={`${API_BASE_URL}/api/pdfs/${selected.document_id}/pages/1?scale=1.25`} alt={`${visibleTitle(selected)} の1ページ目プレビュー`} onError={() => setPreviewError(true)} className="max-h-[55vh] w-full object-contain"/>}
              </div>
              <div className="grid w-full grid-cols-2 gap-3 text-xs text-zinc-500 sm:grid-cols-4"><span>{selected.page_count} ページ</span><span>Quiz {quizProgress(selected.document_id)}/{selected.total_chunks}</span><span>{selected.layout_ready ? "レイアウト翻訳済" : selected.mono_ready && selected.quality_gate === "fail" ? "確認用PDFあり" : selected.reading_ready ? "本文訳あり" : "未翻訳"}</span><span>{selected.quality_gate === "fail" ? "QA要確認" : selected.cache_stale ? "再検証必要" : "Library登録済"}</span></div>
              {selected.doi && <p className="w-full break-all text-xs text-zinc-500">DOI: {selected.doi}</p>}
              <Button onClick={() => onOpen(selected.document_id)} className="h-11 w-full max-w-sm bg-indigo-600 text-white hover:bg-indigo-500">この資料を開く <ArrowRight className="ml-2 h-4 w-4"/></Button>
              <div className="flex w-full max-w-sm flex-col gap-2">
                <Button variant="ghost" className="h-11 border border-indigo-500/30 text-indigo-200 hover:bg-indigo-500/10"
                  disabled={Boolean(exportingOfflineId)}
                  onClick={() => void saveOfflineZip(selected.document_id)}>
                  {exportingOfflineId === selected.document_id ? "スマホ用ZIPを作成中..." : "スマホ用に論文＋語彙を持ち出す（ZIP）"}
                </Button>
                <p className="text-[11px] leading-relaxed text-zinc-500">原文・保存済み日本語PDF・全語彙を含みます。スマホへコピーしてオフラインで開けます。翻訳品質が不合格でも判定を保持します。</p>
                {offlineExportError && <p role="alert" className="text-xs text-red-400">{offlineExportError}</p>}
                {offlineExportNotice && <p role="status" className="text-xs text-emerald-300">{offlineExportNotice}</p>}
              </div>
              <div className="w-full rounded-xl border border-white/10 bg-zinc-900/45 p-4"><div className="mb-2 flex items-center justify-between"><h4 className="text-sm font-semibold text-zinc-200">研究メモ</h4>{editingId !== selected.document_id && <button type="button" className="text-xs text-indigo-300 hover:underline" onClick={() => { setEditingId(selected.document_id); setDraftNote(selected.notes ?? ""); setNoteError("") }}>{selected.notes?.trim() ? "編集" : "＋ 追加"}</button>}</div>
              {editingId === selected.document_id ? <form className="space-y-3" onSubmit={async (event) => { event.preventDefault(); setSavingNote(true); setNoteError(""); try { await onSaveNotes(selected.document_id, draftNote); setEditingId(null) } catch (err) { setNoteError(err instanceof Error ? err.message : "メモの保存に失敗しました") } finally { setSavingNote(false) } }}><label className="text-xs text-zinc-500" htmlFor="pt-library-note-editor">研究結果・図表番号・条件・出典の用途をメモ</label><textarea id="pt-library-note-editor" rows={5} maxLength={3000} value={draftNote} onChange={(event) => setDraftNote(event.target.value)} className="w-full rounded-lg border border-white/10 bg-zinc-900 p-3 text-sm text-zinc-100" placeholder="例：Fig. 3に磁場の実測値。gap 4 mm、20 Kで比較。"/><div className="flex gap-3"><button type="submit" disabled={savingNote} className="rounded-lg bg-indigo-600 px-4 py-2 text-xs text-white disabled:opacity-50">{savingNote ? "保存中" : "保存"}</button><button type="button" className="text-xs text-zinc-400" onClick={() => setEditingId(null)}>キャンセル</button></div>{noteError && <p role="alert" className="text-xs text-red-300">{noteError}</p>}</form> : <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-400">{selected.notes?.trim() || "まだ研究メモはありません。資料の用途や図番号を書いておくと、後からメモのみで探せます。"}</p>}
              </div>
            </div>}
          </div>
        </div>
      </section>
    </div>
  )
}
