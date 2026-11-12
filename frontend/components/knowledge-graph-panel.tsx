"use client"

import * as React from "react"
import { ArrowLeft, BookOpen, Download, FileText, GitBranch, Link2, Loader2, Plus, RotateCcw, Save, Search, Trash2, X } from "lucide-react"

type Paper = { id: string; kind: "paper"; document_id: string; title: string; doi?: string | null; notes: string; page_count: number; paper_key: string; quality_gate?: "pass" | "fail" | null; mono_ready?: boolean }
type FactKind = "term" | "measurement" | "figure" | "note"
type Fact = { id: string; kind: FactKind; title: string; document_id: string; body: string; page_number: number | null;
  figure_label: string; value_text: string; unit: string; source_quote: string; origin: "manual" }
type Link = { id: string; from_id: string; to_id: string; relation: string; note: string; origin: "derived" | "manual";
  evidence_document_id: string | null; evidence_page_number: number | null }
type Graph = { papers: Paper[]; facts: Fact[]; links: Link[]; manual_facts: number; manual_links: number;
  metadata: { relationships_auto_inferred: boolean; source_quotes_verified: boolean } }
type GraphNode = Paper | Fact
const emptyFact = { document_id: "", kind: "note" as FactKind, title: "", body: "", page_number: "",
  figure_label: "", value_text: "", unit: "", source_quote: "" }
const emptyLink = { from_id: "", to_id: "", relation: "related_to", note: "", evidence_document_id: "", evidence_page_number: "" }
const kinds: { id: FactKind; label: string; color: string }[] = [
  { id: "term", label: "専門用語", color: "#6ee7b7" },
  { id: "measurement", label: "測定値", color: "#fbbf24" },
  { id: "figure", label: "図表", color: "#93c5fd" },
  { id: "note", label: "研究メモ", color: "#c4b5fd" },
]
const relations = [
  ["related_to", "関連"], ["cites", "引用する"], ["compares", "比較する"],
  ["supports", "支持する"], ["contradicts", "矛盾する"], ["uses", "利用する"],
] as const
const relationName = (id: string) => relations.find((r) => r[0] === id)?.[1] ?? (id === "source_of" ? "出典" : id)
const bgInput = "w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-xs text-zinc-100 placeholder:text-zinc-600"
const smallButton = "rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-300 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
function idLabel(node: GraphNode) { return node.title.length > 20 ? node.title.slice(0, 19) + "…" : node.title }
function nodeColor(node: GraphNode) { return node.kind === "paper" ? "#818cf8" : kinds.find((v) => v.id === node.kind)?.color ?? "#a1a1aa" }
type Point = { x: number; y: number }
const bounded = (x: number, y: number): Point => ({ x: Math.max(90, Math.min(910, x)), y: Math.max(82, Math.min(413, y)) })
// Fixed-iteration, deterministic graph relaxation: no timers, external libraries, or inferred citations.
function layoutGraph(nodes: GraphNode[], focusId: string, links: Link[]): Map<string, Point> {
  const result = new Map<string, Point>()
  const papers = nodes.filter((n): n is Paper => n.kind === "paper")
  if (!papers.length) return result
  const golden = Math.PI * (3 - Math.sqrt(5))
  const positions = papers.map((paper, i) => {
    if (focusId && paper.id === focusId) return { x: 500, y: 240 }
    const radius = papers.length < 3 ? 170 : 340 * Math.sqrt((i + .8) / papers.length)
    return bounded(500 + radius * Math.cos(i * golden), 240 + radius * .53 * Math.sin(i * golden))
  })
  const lookup = new Map(papers.map((paper, i) => [paper.id, i]))
  // A light repulsive layout keeps disconnected Library papers visible, and manual relations attract peers.
  for (let iteration = 0; iteration < 85; iteration++) {
    const changes = positions.map(() => ({ x: 0, y: 0 }))
    for (let i = 0; i < positions.length; i++) for (let j = i + 1; j < positions.length; j++) {
      const dx = positions[i].x - positions[j].x
      const dy = (positions[i].y - positions[j].y) * 1.45
      const dist = Math.max(1, Math.hypot(dx, dy))
      const push = Math.max(0, (175 - dist) * .028)
      const fx = dx / dist * push
      const fy = dy / dist * push / 1.45
      changes[i].x += fx; changes[i].y += fy
      changes[j].x -= fx; changes[j].y -= fy
    }
    for (const edge of links) {
      if (edge.origin !== "manual") continue
      const i = lookup.get(edge.from_id), j = lookup.get(edge.to_id)
      if (i === undefined || j === undefined || i === j) continue
      const dx = positions[j].x - positions[i].x
      const dy = positions[j].y - positions[i].y
      const distance = Math.max(1, Math.hypot(dx, dy))
      const pull = Math.max(0, distance - 190) * .006
      changes[i].x += (dx / distance) * pull; changes[i].y += (dy / distance) * pull
      changes[j].x -= (dx / distance) * pull; changes[j].y -= (dy / distance) * pull
    }
    positions.forEach((at, i) => {
      if (focusId && papers[i].id === focusId) return
      positions[i] = bounded(at.x + changes[i].x, at.y + changes[i].y)
    })
  }
  papers.forEach((paper, i) => result.set(paper.id, positions[i]))
  const groups = new Map<string, Fact[]>()
  for (const node of nodes) if (node.kind !== "paper") {
    const items = groups.get(node.document_id) ?? []
    items.push(node)
    groups.set(node.document_id, items)
  }
  for (const [documentId, facts] of groups) {
    const center = result.get("paper_" + documentId) ?? { x: 500, y: 240 }
    facts.forEach((fact, i) => {
      const angle = i * golden - Math.PI / 3
      const radius = 74 + 42 * Math.floor(i / 8)
      result.set(fact.id, bounded(center.x + radius * Math.cos(angle), center.y + radius * .66 * Math.sin(angle)))
    })
  }
  return result
}

export function KnowledgeGraphPanel({ apiBase, initialDocumentId, onClose, onOpenDocument }: {
  apiBase: string; initialDocumentId: string | null; onClose: () => void; onOpenDocument: (id: string) => void
}) {
  const [graph, setGraph] = React.useState<Graph | null>(null)
  const [archives, setArchives] = React.useState<{ facts: Fact[]; links: Link[] }>({ facts: [], links: [] })
  const [archivesOpen, setArchivesOpen] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState("")
  const [notice, setNotice] = React.useState("")
  const [focus, setFocus] = React.useState("")
  const [search, setSearch] = React.useState("")
  const [selectedId, setSelectedId] = React.useState(initialDocumentId ? "paper_" + initialDocumentId : "")
  const [editMode, setEditMode] = React.useState<"fact" | "link">("fact")
  const [editingFactId, setEditingFactId] = React.useState<string | null>(null)
  const [editingLinkId, setEditingLinkId] = React.useState<string | null>(null)
  const [factForm, setFactForm] = React.useState(emptyFact)
  const [linkForm, setLinkForm] = React.useState(emptyLink)
  const titleInputRef = React.useRef<HTMLInputElement>(null)
  const [view, setView] = React.useState({ x: 0, y: 0, scale: 1 })
  const [nodeOffsets, setNodeOffsets] = React.useState<Record<string, Point>>({})
  const gestureRef = React.useRef<{ kind: "pan" | "node"; nodeId: string; at: Point; start: Point; pointerId: number; moved: boolean } | null>(null)

  const reload = React.useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(`${apiBase}/api/knowledge-graph`, { cache: "no-store" })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || "研究グラフの取得に失敗しました。")
      setGraph(body as Graph)
      setError("")
    } catch (exc) { setError(exc instanceof Error ? exc.message : "研究グラフの取得に失敗しました。") }
    finally { setLoading(false) }
  }, [apiBase])
  React.useEffect(() => { void reload() }, [reload])
  async function loadArchives() {
    try {
      const response = await fetch(`${apiBase}/api/knowledge-graph/archives`, { cache: "no-store" })
      if (!response.ok) throw new Error("アーカイブ一覧の取得に失敗しました。")
      setArchives(await response.json())
      setArchivesOpen(true)
    } catch (exc) { setError(exc instanceof Error ? exc.message : "アーカイブの取得に失敗しました。") }
  }

  const allNodes = React.useMemo<GraphNode[]>(() => graph ? [...graph.papers, ...graph.facts] : [], [graph])
  const nodeById = React.useMemo(() => new Map(allNodes.map((node) => [node.id, node])), [allNodes])
  const visible = React.useMemo(() => {
    if (!graph) return { nodes: [] as GraphNode[], links: [] as Link[], overflow: 0 }
    const query = search.trim().toLocaleLowerCase()
    let ids = new Set(allNodes.map((n) => n.id))
    if (query) {
      const matched = allNodes.filter((node) => (
        `${node.title} ${node.kind === "paper" ? `${node.notes} ${node.doi ?? ""}` : `${node.body} ${node.source_quote} ${node.value_text} ${node.unit}`}`
      ).toLocaleLowerCase().includes(query))
      ids = new Set(matched.map((n) => n.id))
      for (const n of matched) if (n.kind !== "paper") ids.add("paper_" + n.document_id)
    } else if (focus) {
      ids = new Set([focus])
      for (const f of graph.facts) if ("paper_" + f.document_id === focus) ids.add(f.id)
      for (const edge of graph.links) if (edge.origin === "manual" && (ids.has(edge.from_id) || ids.has(edge.to_id))) {
        ids.add(edge.from_id); ids.add(edge.to_id)
      }
    }
    const all = allNodes.filter((n) => ids.has(n.id))
    const shown = all.slice(0, focus && !query ? 48 : 100)
    const keep = new Set(shown.map((n) => n.id))
    return { nodes: shown, links: graph.links.filter((l) => keep.has(l.from_id) && keep.has(l.to_id)), overflow: Math.max(0, all.length - shown.length) }
  }, [graph, allNodes, search, focus])
  const baseCoords = React.useMemo(() => layoutGraph(visible.nodes, focus && !search ? focus : "", visible.links), [visible.nodes, visible.links, focus, search])
  const coords = React.useMemo(() => new Map([...baseCoords].map(([id, pos]) => [id, { x: pos.x + (nodeOffsets[id]?.x ?? 0), y: pos.y + (nodeOffsets[id]?.y ?? 0) }])), [baseCoords, nodeOffsets])
  const selected = nodeById.get(selectedId)
  const selectedManualLink = graph?.links.find((link) => link.id === selectedId && link.origin === "manual")

  React.useEffect(() => {
    if (!graph?.papers.length) return
    if (!factForm.document_id) setFactForm((f) => ({ ...f, document_id: initialDocumentId && graph.papers.some((p) => p.document_id === initialDocumentId) ? initialDocumentId : graph.papers[0].document_id }))
    if (!linkForm.from_id) setLinkForm((l) => ({ ...l, from_id: initialDocumentId && graph.papers.some((p) => p.document_id === initialDocumentId) ? "paper_" + initialDocumentId : graph.papers[0].id, to_id: "" }))
  }, [graph, initialDocumentId, factForm.document_id, linkForm.from_id])

  async function request(path: string, method: string, body?: unknown) {
    setSaving(true); setError(""); setNotice("")
    try {
      const response = await fetch(`${apiBase}${path}`, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.detail || `操作に失敗しました (${response.status})`)
      setNotice(method === "DELETE" ? "アーカイブしました（バックアップから復旧できます）" : "保存しました。")
      await reload()
      if (archivesOpen) await loadArchives()
      return true
    } catch (exc) { setError(exc instanceof Error ? exc.message : "保存に失敗しました。"); return false }
    finally { setSaving(false) }
  }
  async function saveFact(event: React.FormEvent) {
    event.preventDefault()
    setError("")
    if (!factForm.document_id || !graph?.papers.some((p) => p.document_id === factForm.document_id)) {
      setError("出典論文を選択してください。")
      return
    }
    if (!factForm.title.trim()) {
      setError("「名称（必須）」が空欄です。名称を入力してから、下の「登録」を押してください。")
      titleInputRef.current?.focus()
      return
    }
    const doc = graph.papers.find((p) => p.document_id === factForm.document_id)
    if (factForm.page_number && doc && Number(factForm.page_number) > doc.page_count) {
      setError(`根拠ページは1～${doc.page_count}の範囲で指定してください。`); return
    }
    const payload = { ...factForm, title: factForm.title.trim(), page_number: factForm.page_number ? Number(factForm.page_number) : null }
    const ok = await request(editingFactId ? `/api/knowledge-graph/facts/${editingFactId}` : "/api/knowledge-graph/facts", editingFactId ? "PUT" : "POST", payload)
    if (ok) {
      setFocus("paper_" + factForm.document_id)
      setSearch("")
      setEditingFactId(null)
      setFactForm({ ...emptyFact, document_id: factForm.document_id })
      setEditMode("fact")
      setNotice("登録完了：追加した項目を出典論文の周囲に表示しています。")
    }
  }
  async function saveLink(event: React.FormEvent) {
    event.preventDefault()
    const payload = { ...linkForm, evidence_document_id: linkForm.evidence_document_id || null,
      evidence_page_number: linkForm.evidence_page_number ? Number(linkForm.evidence_page_number) : null }
    const ok = await request(editingLinkId ? `/api/knowledge-graph/links/${editingLinkId}` : "/api/knowledge-graph/links", editingLinkId ? "PUT" : "POST", payload)
    if (ok) {
      setFocus("")
      setSearch("")
      setEditingLinkId(null)
      setLinkForm({ ...emptyLink, from_id: linkForm.from_id })
      setNotice("関係を登録しました。全体グラフの実線で確認できます。")
    }
  }
  function chooseNode(node: GraphNode) {
    setSelectedId(node.id)
    if (editMode === "link" && !editingLinkId) {
      if (linkForm.from_id && linkForm.from_id !== node.id) {
        setLinkForm((current) => ({ ...current, to_id: node.id }))
        setNotice(`終点「${node.title}」を選択しました。右側で関係を選んで登録してください。`)
      } else if (!linkForm.from_id) {
        setLinkForm((current) => ({ ...current, from_id: node.id }))
      }
      return
    }
    if (node.kind === "paper") {
      setFactForm({ ...emptyFact, document_id: node.document_id })
      setEditingFactId(null)
      setLinkForm((l) => ({ ...l, from_id: node.id }))
    } else {
      setEditMode("fact")
      setEditingFactId(node.id)
      setFactForm({ document_id: node.document_id, kind: node.kind, title: node.title,
        body: node.body, page_number: node.page_number == null ? "" : String(node.page_number),
        figure_label: node.figure_label, value_text: node.value_text, unit: node.unit, source_quote: node.source_quote })
    }
  }
  function chooseLink(link: Link) {
    if (link.origin !== "manual") return
    setSelectedId(link.id); setEditingLinkId(link.id); setEditMode("link")
    setLinkForm({ from_id: link.from_id, to_id: link.to_id, relation: link.relation, note: link.note,
      evidence_document_id: link.evidence_document_id ?? "",
      evidence_page_number: link.evidence_page_number == null ? "" : String(link.evidence_page_number) })
  }
  function beginGraphGesture(event: React.PointerEvent<SVGSVGElement>, kind: "pan" | "node", nodeId = "") {
    if (event.button !== 0) return
    const rect = event.currentTarget.getBoundingClientRect()
    const at = { x: (event.clientX - rect.left) * 1000 / rect.width, y: (event.clientY - rect.top) * 480 / rect.height }
    gestureRef.current = { kind, nodeId, at, start: kind === "pan" ? { x: view.x, y: view.y } : { x: nodeOffsets[nodeId]?.x ?? 0, y: nodeOffsets[nodeId]?.y ?? 0 }, pointerId: event.pointerId, moved: false }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function moveGraphGesture(event: React.PointerEvent<SVGSVGElement>) {
    const gesture = gestureRef.current
    if (!gesture || gesture.pointerId !== event.pointerId) return
    const rect = event.currentTarget.getBoundingClientRect()
    const at = { x: (event.clientX - rect.left) * 1000 / rect.width, y: (event.clientY - rect.top) * 480 / rect.height }
    const dx = at.x - gesture.at.x, dy = at.y - gesture.at.y
    if (Math.hypot(dx, dy) > 4) gesture.moved = true
    if (!gesture.moved) return
    if (gesture.kind === "pan") setView((current) => ({ ...current, x: gesture.start.x + dx, y: gesture.start.y + dy }))
    else setNodeOffsets((current) => ({ ...current, [gesture.nodeId]: { x: gesture.start.x + dx / view.scale, y: gesture.start.y + dy / view.scale } }))
  }
  function endGraphGesture(event: React.PointerEvent<SVGSVGElement>) {
    const gesture = gestureRef.current
    if (!gesture || gesture.pointerId !== event.pointerId) return
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    gestureRef.current = null
    if (gesture.kind === "node" && !gesture.moved) {
      const node = nodeById.get(gesture.nodeId)
      if (node) chooseNode(node)
    }
  }
  function zoomGraph(event: React.WheelEvent<SVGSVGElement>) {
    event.preventDefault()
    const rect = event.currentTarget.getBoundingClientRect()
    const anchorX = (event.clientX - rect.left) * 1000 / rect.width
    const anchorY = (event.clientY - rect.top) * 480 / rect.height
    setView((current) => {
      const next = Math.max(.55, Math.min(3.2, current.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12)))
      return { scale: next, x: anchorX - ((anchorX - current.x) / current.scale) * next, y: anchorY - ((anchorY - current.y) / current.scale) * next }
    })
  }
  function graphNodePointerDown(event: React.PointerEvent<SVGGElement>, id: string) {
    event.stopPropagation()
    const svg = event.currentTarget.ownerSVGElement
    if (!svg || event.button !== 0) return
    const rect = svg.getBoundingClientRect()
    const at = { x: (event.clientX - rect.left) * 1000 / rect.width, y: (event.clientY - rect.top) * 480 / rect.height }
    gestureRef.current = { kind: "node", nodeId: id, at, start: { x: nodeOffsets[id]?.x ?? 0, y: nodeOffsets[id]?.y ?? 0 }, pointerId: event.pointerId, moved: false }
    svg.setPointerCapture(event.pointerId)
  }

  async function backup() {
    setError("")
    try {
      const response = await fetch(`${apiBase}/api/knowledge-graph/export`, { cache: "no-store" })
      if (!response.ok) throw new Error("バックアップ取得に失敗しました。")
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      try {
        const anchor = document.createElement("a")
        anchor.href = url
        anchor.download = `PeperTranslator_KnowledgeGraph_${new Date().toISOString().slice(0, 10)}.json`
        document.body.appendChild(anchor); anchor.click(); anchor.remove()
      } finally { window.setTimeout(() => URL.revokeObjectURL(url), 5000) }
      setNotice("知識グラフのバックアップJSONを保存しました。")
    } catch (exc) { setError(exc instanceof Error ? exc.message : "バックアップ取得に失敗しました。") }
  }

  return <div className="fixed inset-0 z-[70] flex bg-black/80 p-2 backdrop-blur-sm md:p-4" role="presentation">
    <section data-graph-version="pt-graph-ux-98.4" role="dialog" aria-modal="true" aria-label="論文間知識グラフ" className="pt-kg-shell m-auto flex h-[97vh] w-full max-w-[1680px] flex-col overflow-hidden rounded-2xl border border-indigo-400/20 bg-zinc-950 shadow-2xl">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
        <div><h2 className="flex items-center gap-2 text-lg font-semibold text-white"><GitBranch className="h-5 w-5 text-indigo-400"/>論文間知識グラフ</h2>
          <p className="mt-1 text-xs text-zinc-500">Libraryを元に表示。論文間の関係・測定値・図表・メモは手動登録し、出典を保持します。</p></div>
        <div className="flex items-center gap-2">
          <button className={smallButton} onClick={() => void backup()}><Download className="mr-1 inline h-4 w-4"/>バックアップ</button>
          <button className={smallButton} onClick={() => void reload()} disabled={loading}><RotateCcw className="mr-1 inline h-4 w-4"/>更新</button>
          <button className={smallButton} onClick={onClose}><X className="mr-1 inline h-4 w-4"/>閉じる</button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
          <div className="flex flex-wrap items-center gap-2">
            <label className="min-w-[180px] flex-1 text-xs text-zinc-400">表示対象の論文
              <select className={bgInput + " mt-1"} value={focus} onChange={(e) => { setFocus(e.target.value); setSearch(""); if (e.target.value) setSelectedId(e.target.value) }}>
                <option value="">全論文を表示（既定）</option>
                {graph?.papers.map((paper) => <option value={paper.id} key={paper.id}>{paper.title.slice(0, 90)}</option>)}
              </select>
            </label>
            <label className="min-w-[190px] flex-1 text-xs text-zinc-400">検索（論文・メモ・測定値）
              <span className="relative mt-1 block"><Search className="absolute left-2 top-2.5 h-4 w-4 text-zinc-500"/>
                <input className={bgInput + " pl-8"} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="例：REBCO、Fig. 3、8 T"/></span>
            </label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
            <span>{graph?.papers.length ?? 0} 論文 ／ {graph?.manual_facts ?? 0} 件の登録項目 ／ {graph?.manual_links ?? 0} 件の手動関係</span>
            <span>{visible.overflow > 0 ? `表示上限：残り${visible.overflow}件` : `${visible.nodes.length} ノード表示`}</span>
          </div>
          <div className="relative min-h-[350px] overflow-hidden rounded-xl border border-white/10 bg-zinc-900/60">
            {loading && <span className="absolute left-4 top-4 z-10 flex items-center gap-2 text-sm text-zinc-300"><Loader2 className="h-4 w-4 animate-spin"/>読み込み中</span>}
            <div className="absolute right-3 top-3 z-10 flex gap-1 rounded-lg bg-zinc-950/90 p-1 text-xs" aria-label="グラフ表示操作">
              <button type="button" className={smallButton} aria-label="拡大" onClick={() => setView((v) => ({ ...v, scale: Math.min(3.2, v.scale * 1.25) }))}>＋</button>
              <button type="button" className={smallButton} aria-label="縮小" onClick={() => setView((v) => ({ ...v, scale: Math.max(.55, v.scale / 1.25) }))}>－</button>
              <button type="button" className={smallButton} onClick={() => { setView({ x: 0, y: 0, scale: 1 }); setNodeOffsets({}) }}>配置リセット</button>
              {focus && <button type="button" className={smallButton} onClick={() => { setFocus(""); setSearch(""); setView({ x: 0, y: 0, scale: 1 }) }}>全体表示</button>}
            </div>
            <svg className="pt-kg-canvas block h-[420px] w-full touch-none cursor-grab" viewBox="0 0 1000 480" role="img" aria-label="研究グラフ：論文と登録項目の関係。ドラッグで移動、ホイールでズーム" onWheel={zoomGraph}
              onPointerDown={(event) => beginGraphGesture(event, "pan")} onPointerMove={moveGraphGesture} onPointerUp={endGraphGesture} onPointerCancel={endGraphGesture}>
              <defs>
                <marker id="pt98-link-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#71717a"/></marker>
                <pattern id="pt98-graph-dots" width="25" height="25" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#334155" opacity="0.52"/></pattern>
              </defs>
              <rect width="1000" height="480" fill="#0e1726"/>
              <rect width="1000" height="480" fill="url(#pt98-graph-dots)"/>
              <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
              {visible.links.map((link) => {
                const from = coords.get(link.from_id); const to = coords.get(link.to_id)
                if (!from || !to) return null
                return <g key={link.id}>
                  <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={link.origin === "manual" ? "#a5b4fc" : "#52525b"}
                    strokeWidth={link.origin === "manual" ? 2 : 1} strokeDasharray={link.origin === "manual" ? "" : "4 5"} opacity="0.7" markerEnd={link.origin === "manual" ? "url(#pt98-link-arrow)" : undefined}/>
                  {link.origin === "manual" && <g role="button" tabIndex={0} aria-label={`${relationName(link.relation)}の関係を編集`} onPointerDown={(e) => e.stopPropagation()} onClick={() => chooseLink(link)} onKeyDown={(e) => { if (e.key === "Enter") chooseLink(link) }} className="cursor-pointer">
                    <rect x={(from.x + to.x) / 2 - 26} y={(from.y + to.y) / 2 - 12} width="52" height="21" rx="6" fill="#27272a" stroke="#6366f1"/>
                    <text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 + 2} textAnchor="middle" fontSize="10" fill="#c7d2fe">{relationName(link.relation)}</text>
                  </g>}
                </g>
              })}
              {visible.nodes.map((node) => {
                const at = coords.get(node.id); if (!at) return null
                const chosen = selectedId === node.id
                return <g key={node.id} role="button" tabIndex={0} aria-label={`${node.kind === "paper" ? "論文" : "項目"} ${node.title} を選択`} onPointerDown={(e) => graphNodePointerDown(e, node.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); chooseNode(node) } }} className="cursor-pointer">
                  <title>{node.title}</title>
                  <circle cx={at.x} cy={at.y} r={node.kind === "paper" ? 28 : 20} fill="#18181b" stroke={nodeColor(node)} strokeWidth={chosen ? 4 : 2}/>
                  <text x={at.x} y={at.y + 4} textAnchor="middle" fill={nodeColor(node)} fontSize={node.kind === "paper" ? 14 : 11}>
                    {node.kind === "paper" ? "PDF" : node.kind === "measurement" ? "値" : node.kind === "figure" ? "Fig" : node.kind === "term" ? "語" : "Memo"}
                  </text>
                  <text x={at.x} y={at.y + (node.kind === "paper" ? 46 : 38)} textAnchor="middle" fill="#e4e4e7" fontSize="12">{idLabel(node)}</text>
                </g>
              })}
              </g>
            </svg>
            {!loading && visible.nodes.length === 0 && <p className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">該当項目がありません。検索を変更するかLibraryに論文を登録してください。</p>}
          </div>
          <div className="flex flex-wrap justify-between gap-3 text-xs text-zinc-400">
            <span>操作：背景ドラッグで移動・ホイールで拡大縮小・ノードドラッグで配置調整</span>
            {!graph?.manual_links && <span>関係線は手動で「論文間の関係」を登録すると表示されます。</span>}
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-zinc-400">
            <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-indigo-400"/>論文</span>
            {kinds.map((k) => <span key={k.id} className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: k.color }}/>{k.label}</span>)}
            <span>破線＝出典、実線＝手動登録の関係</span>
          </div>
          <div className="rounded-xl border border-white/10 bg-zinc-900/40 p-3 text-xs text-zinc-400">
            {selected?.kind === "paper" ? <>
              <div className="mb-2 flex items-center gap-2 font-medium text-zinc-100"><BookOpen className="h-4 w-4"/> {selected.title}</div>
              {selected.doi && <p className="mb-1 break-all">DOI: {selected.doi}</p>}
              <p>{selected.page_count}ページ。既存研究メモ：{selected.notes || "未登録"}</p>
              {selected.quality_gate === "fail" && <p className="mt-2 text-amber-300">日本語PDFの品質検査は不合格です。引用時は原文を確認してください。</p>}
              <button className="mt-3 inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-2 text-white hover:bg-indigo-500" onClick={() => onOpenDocument(selected.document_id)}>この論文を開く <ArrowLeft className="h-3.5 w-3.5 rotate-180"/></button>
            </> : selected?.kind ? <>
              <div className="mb-2 font-medium text-zinc-100">{selected.title}</div>
              <p className="whitespace-pre-wrap">{selected.body}</p>
              <p className="mt-2">根拠：{graph?.papers.find((p) => p.document_id === selected.document_id)?.title ?? selected.document_id.slice(0, 12)}{selected.page_number ? ` / p.${selected.page_number}` : ""}{selected.figure_label ? ` / ${selected.figure_label}` : ""}</p>
              {selected.kind === "measurement" && <p>値：{selected.value_text} {selected.unit}</p>}
              {selected.source_quote && <p className="mt-2 rounded-md bg-zinc-950 p-2">入力された原文：{selected.source_quote}</p>}
              <p className="mt-2 text-[11px] text-amber-200/80">手動登録値です。原文との一致をアプリが確認したものではありません。</p>
              <button className={smallButton + " mt-2"} disabled={saving} onClick={() => void request(`/api/knowledge-graph/facts/${selected.id}`, "DELETE") }><Trash2 className="mr-1 inline h-3 w-3"/>項目をアーカイブ</button>
            </> : selectedManualLink ? <>
              <p className="font-medium text-zinc-100">{relationName(selectedManualLink.relation)}：{nodeById.get(selectedManualLink.from_id)?.title} → {nodeById.get(selectedManualLink.to_id)?.title}</p>
              <p className="mt-2 whitespace-pre-wrap">{selectedManualLink.note || "根拠メモなし"}</p>
              <button className={smallButton + " mt-2"} disabled={saving} onClick={() => void request(`/api/knowledge-graph/links/${selectedManualLink.id}`, "DELETE")}><Trash2 className="mr-1 inline h-3 w-3"/>関係をアーカイブ</button>
            </> : <p>論文・項目・関係線をクリックすると、詳細が表示されます。</p>}
          </div>
        </main>
        <aside className="min-h-0 w-full shrink-0 overflow-y-auto border-t border-white/10 bg-zinc-950 p-4 lg:w-[380px] lg:border-l lg:border-t-0">
          <div className="mb-3 flex rounded-lg border border-white/10 bg-zinc-900 p-1">
            <button type="button" className={`flex-1 rounded-md px-2 py-2 text-xs ${editMode === "fact" ? "bg-indigo-600 text-white" : "text-zinc-400"}`} onClick={() => { setEditMode("fact"); setNotice("名称を入力し、フォーム下部の「登録」を押してください。"); titleInputRef.current?.focus() }}><Plus className="mr-1 inline h-4 w-4"/>項目の作成・編集</button>
            <button type="button" className={`flex-1 rounded-md px-2 py-2 text-xs ${editMode === "link" ? "bg-indigo-600 text-white" : "text-zinc-400"}`} onClick={() => { setEditMode("link"); if (selected && !editingLinkId) setLinkForm((current) => ({ ...current, from_id: selected.id, to_id: "" })); setNotice("起点と終点を選び、下部の「関係を登録」を押してください。ノードをクリックして終点も選択できます。") }}><Link2 className="mr-1 inline h-4 w-4"/>論文間の関係</button>
          </div>
          {error && <p className="mb-3 whitespace-pre-wrap rounded-lg border border-red-700/50 bg-red-950/30 p-3 text-xs text-red-200" role="alert">{error}</p>}
          {notice && <p className="mb-3 rounded-lg border border-emerald-700/40 bg-emerald-950/30 p-3 text-xs text-emerald-200" role="status">{notice}</p>}
          {editMode === "fact" ? <form noValidate onSubmit={(e) => void saveFact(e)} className="space-y-3">
            <h3 className="text-sm font-medium text-zinc-100">{editingFactId ? "登録項目を編集" : "根拠付きの項目を追加"}</h3>
            <label className="block text-xs text-zinc-400">出典論文（必須）
              <select required className={bgInput + " mt-1"} value={factForm.document_id} onChange={(e) => setFactForm({ ...factForm, document_id: e.target.value })}>
                {graph?.papers.map((p) => <option key={p.document_id} value={p.document_id}>{p.title.slice(0, 85)}</option>)}
              </select></label>
            <label className="block text-xs text-zinc-400">種類
              <select className={bgInput + " mt-1"} value={factForm.kind} onChange={(e) => setFactForm({ ...factForm, kind: e.target.value as FactKind })}>
                {kinds.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
              </select></label>
            <label className="block text-xs text-zinc-400">名称（必須）
              <input ref={titleInputRef} required maxLength={160} className={bgInput + " mt-1"} value={factForm.title} onChange={(e) => setFactForm({ ...factForm, title: e.target.value })} placeholder="例：臨界電流 Ic"/></label>
            <label className="block text-xs text-zinc-400">記述・研究メモ
              <textarea rows={3} maxLength={3000} className={bgInput + " mt-1"} value={factForm.body} onChange={(e) => setFactForm({ ...factForm, body: e.target.value })} placeholder="自分の解釈、条件、他の論文との比較等"/></label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs text-zinc-400">根拠ページ
                <input type="number" min={1} max={graph?.papers.find((p) => p.document_id === factForm.document_id)?.page_count || undefined} className={bgInput + " mt-1"} value={factForm.page_number} onChange={(e) => setFactForm({ ...factForm, page_number: e.target.value })} placeholder="例：3"/></label>
              <label className="block text-xs text-zinc-400">図表番号
                <input maxLength={100} className={bgInput + " mt-1"} value={factForm.figure_label} onChange={(e) => setFactForm({ ...factForm, figure_label: e.target.value })} placeholder="Fig. 2"/></label>
            </div>
            {factForm.kind === "measurement" && <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs text-zinc-400">測定値（原文の表記）<input className={bgInput + " mt-1"} maxLength={120} value={factForm.value_text} onChange={(e) => setFactForm({ ...factForm, value_text: e.target.value })} placeholder="4.2"/></label>
              <label className="block text-xs text-zinc-400">単位<input className={bgInput + " mt-1"} maxLength={80} value={factForm.unit} onChange={(e) => setFactForm({ ...factForm, unit: e.target.value })} placeholder="T"/></label>
            </div>}
            <label className="block text-xs text-zinc-400">原文抜粋（任意、手動入力・未照合）
              <textarea rows={2} maxLength={1000} className={bgInput + " mt-1"} value={factForm.source_quote} onChange={(e) => setFactForm({ ...factForm, source_quote: e.target.value })}/></label>
            <p className="text-[11px] text-zinc-400">※ 上の「項目の作成・編集」はタブです。実際の保存は下の「登録」ボタンで行います。</p>
            <div className="flex flex-wrap gap-2"><button type="submit" disabled={saving || !graph?.papers.length} className="inline-flex flex-1 items-center justify-center rounded-lg bg-indigo-600 px-3 py-2 text-xs text-white hover:bg-indigo-500 disabled:opacity-50"><Save className="mr-1 h-4 w-4"/>{saving ? "保存中" : editingFactId ? "変更を保存" : "登録"}</button>
              {editingFactId && <button type="button" className={smallButton} onClick={() => { setEditingFactId(null); setFactForm({ ...emptyFact, document_id: factForm.document_id }) }}>新規入力</button>}</div>
          </form> : <form className="space-y-3" onSubmit={(e) => void saveLink(e)}>
            <h3 className="text-sm font-medium text-zinc-100">{editingLinkId ? "関係を編集" : "2つの項目を結ぶ"}</h3>
            <label className="block text-xs text-zinc-400">起点
              <select required className={bgInput + " mt-1"} value={linkForm.from_id} onChange={(e) => setLinkForm({ ...linkForm, from_id: e.target.value })}>{allNodes.map((n) => <option key={n.id} value={n.id}>{n.title.slice(0, 72)}</option>)}</select></label>
            <label className="block text-xs text-zinc-400">終点
              <select required className={bgInput + " mt-1"} value={linkForm.to_id} onChange={(e) => setLinkForm({ ...linkForm, to_id: e.target.value })}><option value="">選択してください</option>{allNodes.filter((n) => n.id !== linkForm.from_id).map((n) => <option key={n.id} value={n.id}>{n.title.slice(0, 72)}</option>)}</select></label>
            <label className="block text-xs text-zinc-400">関係
              <select className={bgInput + " mt-1"} value={linkForm.relation} onChange={(e) => setLinkForm({ ...linkForm, relation: e.target.value })}>{relations.map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select></label>
            <label className="block text-xs text-zinc-400">根拠・比較の説明
              <textarea rows={3} maxLength={2000} className={bgInput + " mt-1"} value={linkForm.note} onChange={(e) => setLinkForm({ ...linkForm, note: e.target.value })} placeholder="なぜ関連するか、どの記述を引用するか"/></label>
            <label className="block text-xs text-zinc-400">根拠となる論文（任意）
              <select className={bgInput + " mt-1"} value={linkForm.evidence_document_id} onChange={(e) => setLinkForm({ ...linkForm, evidence_document_id: e.target.value, evidence_page_number: "" })}>
                <option value="">根拠論文未指定</option>{graph?.papers.map((p) => <option value={p.document_id} key={p.document_id}>{p.title.slice(0, 80)}</option>)}
              </select></label>
            <label className="block text-xs text-zinc-400">根拠ページ（任意）
              <input type="number" min={1} disabled={!linkForm.evidence_document_id} className={bgInput + " mt-1 disabled:opacity-50"} value={linkForm.evidence_page_number} onChange={(e) => setLinkForm({ ...linkForm, evidence_page_number: e.target.value })}/></label>
            {!linkForm.to_id && <p className="text-[11px] text-amber-200">終点を選ぶと「関係を登録」が有効になります。関連を推測して自動登録することはありません。</p>}
            <div className="flex gap-2"><button type="submit" disabled={saving || allNodes.length < 2 || !linkForm.to_id} className="flex-1 rounded-lg bg-indigo-600 px-3 py-2 text-xs text-white disabled:opacity-50"><Link2 className="mr-1 inline h-4 w-4"/>{editingLinkId ? "変更を保存" : "関係を登録"}</button>
              {editingLinkId && <button type="button" className={smallButton} onClick={() => { setEditingLinkId(null); setLinkForm({ ...emptyLink, from_id: linkForm.from_id }) }}>新規入力</button>}</div>
          </form>}
          <div className="mt-5 border-t border-white/10 pt-3">
            <button type="button" className={smallButton} onClick={() => { if (archivesOpen) setArchivesOpen(false); else void loadArchives() }}>
              <RotateCcw className="mr-1 inline h-4 w-4"/>アーカイブを復元
            </button>
            {archivesOpen && <div className="mt-2 max-h-48 space-y-2 overflow-auto text-xs text-zinc-300">
              {archives.facts.length === 0 && archives.links.length === 0 && <p className="text-zinc-500">アーカイブはありません。</p>}
              {archives.facts.map((fact) => <div key={fact.id} className="flex items-center justify-between gap-2 rounded-md border border-white/10 p-2"><span className="min-w-0 truncate">{fact.title}</span><button type="button" className={smallButton} disabled={saving} onClick={() => void request(`/api/knowledge-graph/facts/${fact.id}/restore`, "POST")}>復元</button></div>)}
              {archives.links.map((link) => <div key={link.id} className="flex items-center justify-between gap-2 rounded-md border border-white/10 p-2"><span>関係：{relationName(link.relation)}</span><button type="button" className={smallButton} disabled={saving} onClick={() => void request(`/api/knowledge-graph/links/${link.id}/restore`, "POST")}>復元</button></div>)}
            </div>}
          </div>
          <p className="mt-4 border-t border-white/10 pt-3 text-[11px] leading-5 text-zinc-500">グラフはローカルSQLiteに保存。登録・修正した項目は、研究上の事実として自動保証されません。アーカイブは復元でき、バックアップJSONにも履歴を保存します。バックアップJSONを取り込む機能は今後の工程です。</p>
        </aside>
      </div>
    </section>
  </div>
}
