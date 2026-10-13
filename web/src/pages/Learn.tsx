import { Link, useNavigate, useParams } from "react-router-dom"
import { AlertTriangle, BookOpen, Check, CheckCircle2, ChevronRight, ExternalLink, Lock, Minus, Sparkles, Target, TrendingDown, TrendingUp } from "lucide-react"
import { api, useApi, pct, LEVEL, STATUS } from "@/lib/api"
import { useUser } from "@/lib/user"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

/* ------------------------------------------------------------------ */
/* Shared building blocks (Dashboard imports these too)                */
/* ------------------------------------------------------------------ */

export type Tone = "weak" | "developing" | "strong" | "neutral" | "muted"
export const toneOf = (s?: string): Tone => (s === "weak" || s === "developing" || s === "strong" ? s : "muted")
const statusLabel = (s: string) => STATUS[s] || s.replace(/_/g, " ")

export function StatusPill({ status }: { status: string }) {
  return <span className="pill" data-tone={toneOf(status)}>{statusLabel(status)}</span>
}

export function MasteryBar({ value, tone = "neutral", label, large }: { value: number; tone?: Tone; label: string; large?: boolean }) {
  const w = Math.round(Math.max(0, Math.min(1, value || 0)) * 100)
  return (
    <div data-tone={tone} className={`mastery${large ? " mastery-lg" : ""}`} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={w}>
      <div className="mastery-fill" style={{ width: `${w}%` }} />
    </div>
  )
}

const TREND: Record<string, { label: string; Icon: any; tone: Tone }> = {
  improving: { label: "Improving", Icon: TrendingUp, tone: "strong" },
  declining: { label: "Declining", Icon: TrendingDown, tone: "weak" },
  stable: { label: "Steady", Icon: Minus, tone: "muted" },
}
export function Trend({ trend }: { trend?: string }) {
  const t = trend ? TREND[trend] : undefined
  if (!t) return null
  return <span data-tone={t.tone} className="inline-flex items-center gap-1 font-medium text-[hsl(var(--tone-ink))]"><t.Icon className="h-3.5 w-3.5" aria-hidden />{t.label}</span>
}

export function Loading({ error, loading }: { error: string; loading: boolean }) {
  if (error) return <p role="alert" className="rounded-md bg-destructive/10 p-4 text-sm text-destructive">{error}</p>
  return loading ? <p role="status" className="animate-pulse text-muted-foreground">Loading...</p> : null
}

export const Crumbs = ({ items }: { items: [string, string?][] }) => (
  <nav aria-label="Breadcrumb" className="mb-4 flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
    {items.map(([t, to], i) => (<span key={i} className="flex items-center gap-1">{i > 0 && <ChevronRight className="h-3 w-3" aria-hidden />}{to ? <Link className="hover:text-foreground" to={to}>{t}</Link> : <span aria-current="page" className="text-foreground">{t}</span>}</span>))}
  </nav>
)

export function LevelButtons({ topic, levels }: { topic: string; levels: any[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {levels.map((l) => l.unlocked ? (
        <Button key={l.difficulty} size="sm" variant={l.passed ? "secondary" : "default"} asChild>
          <Link to={`/quiz/${topic}/${l.difficulty}`}>
            {l.passed && <CheckCircle2 className="h-4 w-4 text-success" />}{LEVEL[l.difficulty]}{l.tries > 0 && <span className="opacity-70">{l.best_score}/{l.best_total}</span>}
          </Link>
        </Button>
      ) : (
        <Button key={l.difficulty} size="sm" variant="outline" disabled title="Pass the previous level to unlock this one"><Lock className="h-3.5 w-3.5" />{LEVEL[l.difficulty]}</Button>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Learning stages: quiz difficulty (easy/medium/hard) <-> study level */
/* ------------------------------------------------------------------ */

const ORDER = ["easy", "medium", "hard"]
const STAGES: Record<string, { name: string; tagline: string; goal: string }> = {
  easy: { name: "Beginner", tagline: "Core ideas and vocabulary", goal: "Explain the key terms and basic ideas in your own words." },
  medium: { name: "Intermediate", tagline: "Using the ideas on typical problems", goal: "Apply the ideas to standard problems and avoid the common mistakes." },
  hard: { name: "Advanced", tagline: "Combining ideas and tricky cases", goal: "Combine several ideas, handle edge cases and solve multi-step problems." },
}
/** Resource levels may be named beginner/intermediate/advanced or easy/medium/hard. */
const stageOf = (l?: string) => {
  const s = (l || "").toLowerCase()
  return s === "easy" || s === "beginner" ? "easy" : s === "medium" || s === "intermediate" ? "medium" : s === "hard" || s === "advanced" ? "hard" : ""
}
const minutesOf = (seconds: number) => Math.max(1, Math.round(seconds / 60))

/** Recommended order: prerequisites first; otherwise keep the original order. */
function pathOrder(mods: any[]): any[] {
  const ids = new Set(mods.map((m) => m.topic_id)), done = new Set<string>(), out: any[] = []
  const left = [...mods]
  while (left.length) {
    const i = left.findIndex((m) => m.prerequisites.every((p: any) => !ids.has(p.topic_id) || done.has(p.topic_id)))
    const [m] = left.splice(i < 0 ? 0 : i, 1)   // i < 0 only if prerequisites form a cycle
    out.push(m); done.add(m.topic_id)
  }
  return out
}

/* ------------------------------------------------------------------ */
/* Subjects                                                            */
/* ------------------------------------------------------------------ */

function SubjectCard({ s, go }: { s: any; go: (subject: string) => void }) {
  const total = s.levels_total, done = s.levels_passed
  const complete = total > 0 && done === total
  const started = s.selected || done > 0
  return (
    <Card className="card-raised flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle>{s.subject}</CardTitle>
          {complete ? <span className="pill" data-tone="strong">Completed</span> : started ? <span className="pill" data-tone="neutral">In progress</span> : null}
        </div>
        <CardDescription>{s.modules} {s.modules === 1 ? "module" : "modules"}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto space-y-4">
        <div>
          <div className="mb-1.5 flex justify-between text-xs text-muted-foreground"><span>Levels passed</span><span className="tabular-nums">{done} of {total}</span></div>
          <MasteryBar value={total ? done / total : 0} tone={complete ? "strong" : "neutral"} label={`${s.subject}: levels passed`} />
        </div>
        <Button className="w-full" variant={complete ? "secondary" : "default"} onClick={() => go(s.subject)}>{complete ? "Review" : started ? "Continue" : "Start"}</Button>
      </CardContent>
    </Card>
  )
}

export function Subjects() {
  const user = useUser(), nav = useNavigate()
  const { data, error, loading } = useApi("/subjects")
  const go = async (s: string) => { await api("/me/subjects", { subject: s }); nav(`/subject/${encodeURIComponent(s)}`) }
  const list: any[] = data?.subjects ?? []
  const started = (s: any) => s.selected || s.levels_passed > 0
  const groups: [string, any[]][] = [
    ["Continue learning", list.filter(started)],
    [list.some(started) ? "Start something new" : "Choose a subject", list.filter((s) => !started(s))],
  ]
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Hello, {user.name}. What do you want to learn?</h1>
        <p className="mt-1 text-muted-foreground">Every module has three stages. Study the material, then pass the quiz (60% or more) to unlock the next stage.</p>
      </div>
      <ol className="grid gap-3 sm:grid-cols-3" aria-label="How each module works">
        {ORDER.map((d, i) => (
          <li key={d} className="flex gap-3 rounded-xl border bg-card p-4">
            <span className="tone-tile tone-tile-sm font-semibold" data-tone="neutral">{i + 1}</span>
            <div><div className="font-semibold">{STAGES[d].name}</div><div className="text-sm text-muted-foreground">{STAGES[d].tagline}</div></div>
          </li>
        ))}
      </ol>
      <Loading error={error} loading={loading} />
      {groups.map(([title, items]) => items.length > 0 && (
        <section key={title} className="space-y-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{items.map((s) => <SubjectCard key={s.subject} s={s} go={go} />)}</div>
        </section>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Modules in a subject: the learning path                             */
/* ------------------------------------------------------------------ */

function PathNode({ n, done, current }: { n: number; done: boolean; current: boolean }) {
  const base = "absolute left-0 top-5 flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold"
  if (done) return <span aria-hidden data-tone="strong" className={`${base} bg-[hsl(var(--tone))] text-white`}><Check className="h-4 w-4" /></span>
  if (current) return <span aria-hidden className={`${base} bg-primary text-primary-foreground ring-4 ring-[hsl(var(--accent))]`}>{n}</span>
  return <span aria-hidden className={`${base} border bg-card text-muted-foreground`}>{n}</span>
}

function Prereqs({ m, byId }: { m: any; byId: Record<string, any> }) {
  if (!m.prerequisites.length) return null
  const unfinished = m.prerequisites.filter((p: any) => byId[p.topic_id] && !(byId[p.topic_id].completed || byId[p.topic_id].levels_total === 0))
  const links = (list: any[]) => list.map((p, i) => (<span key={p.topic_id}><Link className="font-medium underline-offset-2 hover:underline" to={`/module/${p.topic_id}`}>{p.name}</Link>{i < list.length - 1 ? ", " : ""}</span>))
  if (unfinished.length) return <p className="feedback" data-tone="developing"><AlertTriangle className="h-4 w-4" aria-hidden /><span>Learn first: {links(unfinished)}. You can still start, but these topics build the foundation.</span></p>
  return <p className="text-sm text-muted-foreground">Builds on: {links(m.prerequisites)}</p>
}

export function Modules() {
  const subject = decodeURIComponent(useParams().subject || "")
  const { data, error, loading } = useApi(`/modules?subject=${encodeURIComponent(subject)}`)
  const raw: any[] = data?.modules ?? []
  const byId: Record<string, any> = Object.fromEntries(raw.map((m) => [m.topic_id, m]))
  const mods = pathOrder(raw)
  const finished = (m: any) => m.completed || m.levels_total === 0
  const ready = (m: any) => m.prerequisites.every((p: any) => !byId[p.topic_id] || finished(byId[p.topic_id]))
  const next = mods.find((m) => !m.completed && m.levels_total > 0 && ready(m))
  const passed = raw.reduce((n, m) => n + m.levels_passed, 0), total = raw.reduce((n, m) => n + m.levels_total, 0)
  const completed = raw.filter((m) => m.completed).length
  const allDone = raw.length > 0 && completed === raw.filter((m) => m.levels_total > 0).length && total > 0

  return (
    <div>
      <Crumbs items={[["Subjects", "/subjects"], [subject]]} />
      <h1 className="mb-6 text-3xl font-bold tracking-tight">{subject}</h1>
      <Loading error={error} loading={loading} />
      {raw.length > 0 && (
        <section className="hero card-raised mb-8 grid gap-5 p-5 sm:p-6 md:grid-cols-2 md:items-center">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Subject progress</p>
            <p className="text-2xl font-bold tabular-nums">{passed} of {total} levels passed</p>
            <MasteryBar large value={total ? passed / total : 0} tone={allDone ? "strong" : "neutral"} label={`${subject} progress`} />
            <p className="text-sm text-muted-foreground">{completed} of {raw.length} modules completed</p>
          </div>
          {allDone ? (
            <div className="feedback feedback-pop" data-tone="strong" role="status"><CheckCircle2 className="h-4 w-4" aria-hidden /><span>Every module in {subject} is complete. Revisit any module to keep your mastery up.</span></div>
          ) : next ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Up next</p>
              <p className="text-lg font-semibold">{next.name}</p>
              <Button asChild><Link to={`/module/${next.topic_id}`}>{next.levels_passed > 0 ? "Continue module" : "Start module"}</Link></Button>
            </div>
          ) : null}
        </section>
      )}
      <ol className="max-w-4xl">
        {mods.map((m, i) => {
          const isNext = next?.topic_id === m.topic_id
          const leadsTo = raw.filter((o) => o.prerequisites.some((p: any) => p.topic_id === m.topic_id))
          return (
            <li key={m.topic_id} className="relative pb-5 pl-12 last:pb-0 before:absolute before:bottom-0 before:left-4 before:top-[3.25rem] before:w-px before:bg-border last:before:hidden">
              <PathNode n={i + 1} done={!!m.completed} current={isNext} />
              <Card className={`card-raised ${isNext ? "border-primary" : ""}`}>
                <CardHeader className="space-y-2">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <CardTitle><Link className="hover:text-primary" to={`/module/${m.topic_id}`}>{m.name}</Link></CardTitle>
                    <div className="flex items-center gap-2">
                      {isNext && <span className="pill" data-tone="neutral">Up next</span>}
                      {m.completed ? <span className="pill" data-tone="strong">Completed</span> : <StatusPill status={m.status} />}
                    </div>
                  </div>
                  <Prereqs m={m} byId={byId} />
                  {leadsTo.length > 0 && <CardDescription>Leads to: {leadsTo.map((o) => o.name).join(", ")}</CardDescription>}
                </CardHeader>
                <CardContent className="space-y-4">
                  {m.mastery != null && m.status !== "insufficient_data" && (
                    <div><div className="mb-1.5 flex justify-between text-xs text-muted-foreground"><span>Mastery</span><span className="tabular-nums">{pct(m.mastery)}</span></div>
                      <MasteryBar value={m.mastery} tone={toneOf(m.status)} label={`${m.name} mastery`} /></div>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <LevelButtons topic={m.topic_id} levels={m.levels} />
                    <Button size="sm" variant="outline" asChild><Link to={`/module/${m.topic_id}`}><BookOpen className="h-4 w-4" aria-hidden />Study</Link></Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* One module: study path, stage by stage                              */
/* ------------------------------------------------------------------ */

type StageState = "passed" | "current" | "locked" | "open"

function Stage({ topic, d, n, lv, res, goal, state, prevName }: { topic: string; d: string; n: number; lv?: any; res: any[]; goal: string; state: StageState; prevName: string }) {
  const S = STAGES[d], quizName = LEVEL[d] || S.name
  const minutes = res.reduce((t, r) => t + (r.minutes || 0), 0)
  const tone: Tone = state === "passed" ? "strong" : state === "locked" ? "muted" : "neutral"
  return (
    <Card id={`stage-${d}`} className="card-raised scroll-mt-32">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="tone-tile font-semibold" data-tone={tone} aria-hidden>{state === "passed" ? <Check className="h-5 w-5" /> : state === "locked" ? <Lock className="h-4 w-4" /> : n}</span>
            <div><CardTitle className="text-lg">{S.name}</CardTitle><CardDescription>{S.tagline}</CardDescription></div>
          </div>
          {state === "passed" && <span className="pill" data-tone="strong">Passed</span>}
          {state === "current" && <span className="pill" data-tone="neutral">Current stage</span>}
          {state === "locked" && <span className="pill" data-tone="muted">Locked</span>}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <p className="flex gap-2 text-sm"><Target className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden /><span><b>Goal:</b> {goal}</span></p>

        <section>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold"><BookOpen className="h-4 w-4" aria-hidden />Study first</h3>
            {res.length > 0 && <span className="text-xs text-muted-foreground">{res.length} {res.length === 1 ? "item" : "items"}, about {minutes} min, in this order</span>}
          </div>
          {res.length ? (
            <ol className="divide-y rounded-lg border">
              {res.map((r, i) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 px-3 py-3 hover:bg-muted">
                    <div className="flex min-w-0 gap-3">
                      <span className="w-4 shrink-0 text-sm font-semibold tabular-nums text-muted-foreground">{i + 1}</span>
                      <div className="min-w-0">
                        <div className="font-medium">{r.title}{r.link_type === "search" && <span className="ml-2 text-xs font-normal text-muted-foreground">(search results)</span>}</div>
                        <div className="text-xs text-muted-foreground">{r.provider}, {r.minutes} min</div>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2"><Badge variant="outline">{r.type}</Badge><ExternalLink className="h-4 w-4" aria-hidden /></div>
                  </a>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted-foreground">No study material for this stage yet. The quiz is still available.</p>}
        </section>

        {lv ? (
          <section className="flex flex-col gap-3 rounded-lg bg-muted p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1 text-sm">
              <h3 className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4" aria-hidden />{state === "passed" ? "Quiz passed" : "Then take the quiz"}</h3>
              <p className="text-muted-foreground">{lv.questions} questions, {minutesOf(lv.time_limit_seconds)} min, pass with {lv.pass_mark} correct.</p>
              {lv.tries > 0 && (lv.passed
                ? <p className="font-medium text-[hsl(var(--success))]">Best score {lv.best_score}/{lv.best_total}. Passed.</p>
                : <p className="text-muted-foreground">Best score {lv.best_score}/{lv.best_total}. Aim for {lv.pass_mark} of {lv.questions}.</p>)}
              {!lv.unlocked && <p className="text-muted-foreground">Pass the {prevName} quiz to unlock this one.</p>}
            </div>
            {lv.unlocked ? (
              <Button variant={lv.passed ? "secondary" : "default"} asChild>
                <Link to={`/quiz/${topic}/${d}`}>{lv.passed ? "Retake quiz" : lv.tries > 0 ? "Try again" : `Take the ${quizName} quiz`}</Link>
              </Button>
            ) : <Button variant="outline" disabled><Lock className="h-4 w-4" aria-hidden />Locked</Button>}
          </section>
        ) : <p className="text-sm text-muted-foreground">There is no quiz for this stage yet.</p>}
      </CardContent>
    </Card>
  )
}

export function Module() {
  const topic = useParams().topic!
  const { data: m, error, loading } = useApi(`/modules/${encodeURIComponent(topic)}`)
  if (!m) return <Loading error={error} loading={loading} />

  const levels: any[] = m.levels, resources: any[] = m.resources
  const byStage: Record<string, any[]> = { easy: [], medium: [], hard: [] }
  const extra: any[] = []
  resources.forEach((r) => { const s = stageOf(r.level); (s ? byStage[s] : extra).push(r) })

  const objs = m.objectives                                   // optional: string[] or { easy, medium, hard }
  const goals: string[] = Array.isArray(objs) ? objs : []
  const goalFor = (d: string) => (objs && !Array.isArray(objs) && objs[d]) || STAGES[d].goal

  const stages = ORDER.map((d) => ({ d, lv: levels.find((l) => l.difficulty === d), res: byStage[d] })).filter((s) => s.lv || s.res.length)
  const current = levels.find((l) => l.unlocked && !l.passed)
  const stateOf = (d: string, lv?: any): StageState => (lv?.passed ? "passed" : lv && !lv.unlocked ? "locked" : current?.difficulty === d ? "current" : "open")
  const prevName = (d: string) => { const i = levels.findIndex((l) => l.difficulty === d); return i > 0 ? STAGES[levels[i - 1].difficulty]?.name || "previous" : "previous" }
  const hasMastery = m.mastery != null && m.status !== "insufficient_data"
  const cs = current ? STAGES[current.difficulty] : null
  const studyFirst = !!current && current.tries === 0 && byStage[current.difficulty].length > 0

  return (
    <div className="space-y-8">
      <div>
        <Crumbs items={[["Subjects", "/subjects"], [m.subject, `/subject/${encodeURIComponent(m.subject)}`], [m.name]]} />
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold tracking-tight">{m.name}</h1>
          {m.completed ? <span className="pill" data-tone="strong">Completed</span> : <StatusPill status={m.status} />}
        </div>
        {m.description && <p className="mt-2 max-w-prose text-muted-foreground">{m.description}</p>}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <aside className="space-y-4 lg:order-2 lg:sticky lg:top-32 lg:self-start">
          <Card className="card-raised">
            <CardHeader><CardTitle className="text-base">Your next step</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {m.completed ? (
                <>
                  <div className="feedback feedback-pop" data-tone="strong" role="status"><CheckCircle2 className="h-4 w-4" aria-hidden /><span>Module complete. You passed every level.</span></div>
                  <Button className="w-full" variant="outline" asChild><Link to={`/subject/${encodeURIComponent(m.subject)}`}>Back to {m.subject}</Link></Button>
                </>
              ) : current && cs ? (
                <>
                  <p className="text-sm text-muted-foreground">{cs.name} stage: {studyFirst ? "read the study material, then take the quiz." : "take the quiz when you feel ready."}</p>
                  {studyFirst ? (
                    <>
                      <Button className="w-full" onClick={() => document.getElementById(`stage-${current.difficulty}`)?.scrollIntoView({ block: "start" })}>Start with the {cs.name} material</Button>
                      <Button className="w-full" variant="outline" asChild><Link to={`/quiz/${topic}/${current.difficulty}`}>Go straight to the quiz</Link></Button>
                    </>
                  ) : (
                    <Button className="w-full" asChild><Link to={`/quiz/${topic}/${current.difficulty}`}>{current.tries > 0 ? "Try the quiz again" : `Take the ${LEVEL[current.difficulty] || cs.name} quiz`}</Link></Button>
                  )}
                </>
              ) : <p className="text-sm text-muted-foreground">This module has no quizzes yet. Use the study material below.</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Progress</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {levels.length > 0 && (
                <ul className="space-y-2">
                  {levels.map((l) => (
                    <li key={l.difficulty} className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2">
                        {l.passed ? <CheckCircle2 className="h-4 w-4 text-[hsl(var(--success))]" aria-hidden /> : l.unlocked ? <span aria-hidden className="h-4 w-4 rounded-full border-2 border-primary" /> : <Lock className="h-4 w-4 text-muted-foreground" aria-hidden />}
                        {STAGES[l.difficulty]?.name || LEVEL[l.difficulty]}
                      </span>
                      <span className="tabular-nums text-muted-foreground">{l.tries > 0 ? `${l.best_score}/${l.best_total}` : l.unlocked ? "Not tried" : "Locked"}</span>
                    </li>
                  ))}
                </ul>
              )}
              {hasMastery ? (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-sm"><span className="text-muted-foreground">Mastery</span><span className="font-semibold tabular-nums">{pct(m.mastery)}</span></div>
                  <MasteryBar value={m.mastery} tone={toneOf(m.status)} label={`${m.name} mastery`} />
                  <div className="text-xs"><Trend trend={m.trend} /></div>
                </div>
              ) : <p className="text-xs text-muted-foreground">Mastery appears after you answer a few questions.</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Before you start</CardTitle></CardHeader>
            <CardContent className="text-sm">
              {m.prerequisites.length ? (
                <>
                  <p className="mb-2 text-muted-foreground">These topics will help. You can start without them.</p>
                  <ul className="space-y-1">{m.prerequisites.map((p: any) => <li key={p.topic_id}><Link className="font-medium text-primary hover:underline" to={`/module/${p.topic_id}`}>{p.name}</Link></li>)}</ul>
                </>
              ) : <p className="text-muted-foreground">No prerequisites. You can start right away.</p>}
            </CardContent>
          </Card>

          <Button className="w-full" variant="outline" asChild><Link to={`/quiz/${topic}/practice`}><Sparkles className="h-4 w-4" aria-hidden />Adaptive practice</Link></Button>
        </aside>

        <div className="space-y-6 lg:order-1">
          {goals.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-lg">What you will learn</CardTitle></CardHeader>
              <CardContent><ul className="space-y-2 text-sm">{goals.map((g, i) => <li key={i} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />{g}</li>)}</ul></CardContent>
            </Card>
          )}
          <div>
            <h2 className="text-xl font-semibold">Study path</h2>
            <p className="text-sm text-muted-foreground">Work through the stages in order. Study each stage, then pass its quiz to unlock the next.</p>
          </div>
          <ol className="space-y-4">
            {stages.map(({ d, lv, res }, i) => (
              <li key={d}><Stage topic={topic} d={d} n={i + 1} lv={lv} res={res} goal={goalFor(d)} state={stateOf(d, lv)} prevName={prevName(d)} /></li>
            ))}
          </ol>
          {resources.length === 0 && <p className="text-sm text-muted-foreground">No study material for this module yet.</p>}
          {extra.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-lg">More material</CardTitle><CardDescription>Useful at any stage.</CardDescription></CardHeader>
              <CardContent className="divide-y">
                {extra.map((r) => (
                  <a key={r.url} href={r.url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 py-3 hover:text-primary">
                    <div><div className="font-medium">{r.title}{r.link_type === "search" && <span className="ml-2 text-xs text-muted-foreground">(search results)</span>}</div>
                      <div className="text-xs text-muted-foreground">{r.provider}, {r.minutes} min</div></div>
                    <div className="flex shrink-0 items-center gap-2"><Badge variant="outline">{r.type}</Badge><ExternalLink className="h-4 w-4" aria-hidden /></div>
                  </a>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
