import { useEffect, useState, useRef } from "react"
import { Link, useParams } from "react-router-dom"
import {
  CheckCircle2,
  XCircle,
  Pause,
  Play,
  Clock,
  Award,
  ChevronLeft,
  ChevronRight,
  Send,
  Sparkles,
  AlertTriangle
} from "lucide-react"
import { api, LEVEL } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Crumbs } from "@/pages/Learn"
import { cn } from "@/lib/utils"

export default function Quiz() {
  const { topic, level } = useParams() as { topic: string; level: string }
  const [mod, setMod] = useState<any>(null)
  const [quiz, setQuiz] = useState<any>(null)
  const [picked, setPicked] = useState<Record<number | string, number>>({})
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)

  // Timer and pause state
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null)
  const [isPaused, setIsPaused] = useState(false)
  const [pauseBusy, setPauseBusy] = useState(false)
  const [currentIdx, setCurrentIdx] = useState(0)

  // Congrats modal state (for 100% score)
  const [showCongrats, setShowCongrats] = useState(false)

  const timerRef = useRef<any>(null)

  useEffect(() => {
    setQuiz(null)
    setResult(null)
    setPicked({})
    setErr("")
    setCurrentIdx(0)
    setIsPaused(false)
    setShowCongrats(false)
    if (timerRef.current) clearInterval(timerRef.current)

    Promise.all([
      api(`/modules/${encodeURIComponent(topic)}`),
      api("/quiz/start", { topic_id: topic, difficulty: level })
    ]).then(
      ([m, q]) => {
        setMod(m)
        setQuiz(q)
        if (q.seconds_left != null) {
          setSecondsLeft(q.seconds_left)
        }
        if (q.is_paused) {
          setIsPaused(true)
        }
      },
      (e) => setErr(e.message)
    )

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [topic, level])

  // Countdown timer effect
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)

    if (secondsLeft != null && !isPaused && !result) {
      timerRef.current = setInterval(() => {
        setSecondsLeft((prev) => {
          if (prev == null || prev <= 1) {
            clearInterval(timerRef.current)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isPaused, secondsLeft != null, result])

  // Auto submit when time runs out
  useEffect(() => {
    if (secondsLeft === 0 && quiz && !result && !busy) {
      handleTimeOutSubmit()
    }
  }, [secondsLeft, quiz, result, busy])

  async function handleTimeOutSubmit() {
    if (!quiz) return
    setBusy(true)
    try {
      const res = await api("/quiz/submit", {
        topic_id: topic,
        difficulty: level,
        session_id: quiz.session_id,
        timed_out: true,
        answers: quiz.questions.map((q: any) => ({
          question_id: q.id,
          chosen_index: picked[q.id] ?? null
        }))
      })
      setResult(res)
      if (res.score === res.total && res.total > 0) {
        setShowCongrats(true)
      }
      window.scrollTo(0, 0)
    } catch (e: any) {
      setErr(e.message)
    }
    setBusy(false)
  }

  async function togglePause() {
    if (!quiz || pauseBusy || busy || result) return
    setPauseBusy(true)
    try {
      if (isPaused) {
        // Resume
        const res = await api("/quiz/resume", { session_id: quiz.session_id })
        setIsPaused(false)
        if (res.seconds_left != null) {
          setSecondsLeft(res.seconds_left)
        }
      } else {
        // Pause
        const res = await api("/quiz/pause", { session_id: quiz.session_id })
        setIsPaused(true)
        if (res.seconds_left != null) {
          setSecondsLeft(res.seconds_left)
        }
      }
    } catch (e: any) {
      setErr(e.message)
    }
    setPauseBusy(false)
  }

  async function submit() {
    if (!quiz) return
    const blank = quiz.questions.filter((q: any) => picked[q.id] == null).length
    if (
      blank &&
      !confirm(
        `${blank} question(s) not answered. Unanswered questions count as wrong. Submit anyway?`
      )
    )
      return
    setBusy(true)
    try {
      const res = await api("/quiz/submit", {
        topic_id: topic,
        difficulty: level,
        session_id: quiz.session_id,
        answers: quiz.questions.map((q: any) => ({
          question_id: q.id,
          chosen_index: picked[q.id] ?? null
        }))
      })
      setResult(res)
      if (res.score === res.total && res.total > 0) {
        setShowCongrats(true)
      }
      window.scrollTo(0, 0)
    } catch (e: any) {
      setErr(e.message)
    }
    setBusy(false)
  }

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}:${s < 10 ? "0" : ""}${s}`
  }

  if (err && !quiz) {
    return (
      <div className="space-y-4">
        <p className="rounded-md bg-destructive/10 p-4 text-sm text-destructive">
          {err}
        </p>
        <Button variant="outline" asChild>
          <Link to="/subjects">Back to subjects</Link>
        </Button>
      </div>
    )
  }

  if (!quiz || !mod) return <p className="text-muted-foreground">Loading...</p>

  const crumbs = (
    <Crumbs
      items={[
        ["Subjects", "/subjects"],
        [mod.subject, `/subject/${encodeURIComponent(mod.subject)}`],
        [mod.name, `/module/${topic}`],
        [LEVEL[level]]
      ]}
    />
  )
  const L = "ABCD"

  if (result) {
    const p = Math.round((100 * result.score) / result.total)
    return (
      <div className="space-y-6 relative">
        {crumbs}

        {/* Congrats Modal Popup for 100% Score */}
        {showCongrats && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-300">
            <div className="relative w-full max-w-lg rounded-2xl border-2 border-primary/50 bg-card p-8 shadow-2xl text-center space-y-5 animate-in zoom-in-95 duration-200">
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-primary/20 text-primary">
                <Award className="h-12 w-12 text-yellow-500 animate-bounce" />
              </div>
              <div className="space-y-2">
                <div className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                  <Sparkles className="h-3.5 w-3.5" /> PERFECT SCORE!
                </div>
                <h2 className="text-3xl font-extrabold tracking-tight">
                  Congratulations! 🎉
                </h2>
                <p className="text-muted-foreground text-sm">
                  You got every single question right ({result.score} / {result.total})! Outstanding mastery of {mod.name}.
                </p>
              </div>
              <div className="rounded-xl bg-accent/50 p-4 font-medium flex justify-around text-sm">
                <div>
                  <span className="block text-muted-foreground text-xs">Accuracy</span>
                  <span className="text-xl font-bold text-success">100%</span>
                </div>
                <div>
                  <span className="block text-muted-foreground text-xs">Questions</span>
                  <span className="text-xl font-bold">{result.total} / {result.total}</span>
                </div>
                <div>
                  <span className="block text-muted-foreground text-xs">Level</span>
                  <span className="text-xl font-bold text-primary">{LEVEL[level]}</span>
                </div>
              </div>
              <Button
                size="lg"
                className="w-full text-base font-semibold"
                onClick={() => setShowCongrats(false)}
              >
                View Detailed Answers
              </Button>
            </div>
          </div>
        )}

        <Card
          className={cn(
            "border-2",
            result.difficulty === "practice"
              ? ""
              : result.passed
              ? "border-success/40"
              : "border-destructive/40"
          )}
        >
          <CardHeader className="items-center text-center">
            <CardTitle className="text-4xl">
              {result.score} / {result.total}
            </CardTitle>
            <p className="text-muted-foreground">
              {p}%{" "}
              {result.difficulty === "practice"
                ? "· practice answers update your mastery"
                : result.passed
                ? "· Passed! 🎉"
                : `· Not passed (need ${result.pass_mark})`}
            </p>
            <Progress value={p} className="mt-2 max-w-xs" />
          </CardHeader>
          <CardContent className="flex flex-wrap justify-center gap-2">
            {result.passed && result.next_level && (
              <Button asChild>
                <Link to={`/quiz/${topic}/${result.next_level}`}>
                  Go to {LEVEL[result.next_level]} level
                </Link>
              </Button>
            )}
            <Button variant="outline" asChild>
              <Link to={`/quiz/${topic}/${level}`} reloadDocument>
                {level === "practice" ? "Practice again" : "Retake"}
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link to={`/subject/${encodeURIComponent(mod.subject)}`}>
                Back to modules
              </Link>
            </Button>
            <Button variant="ghost" asChild>
              <Link to="/progress">My progress</Link>
            </Button>
          </CardContent>
        </Card>

        {result.results.map((x: any, i: number) => (
          <Card
            key={x.question_id}
            className={cn(
              "border-l-4",
              x.correct ? "border-l-success" : "border-l-destructive"
            )}
          >
            <CardContent className="space-y-2 pt-6">
              <p className="flex gap-2 font-medium">
                {x.correct ? (
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
                ) : (
                  <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                )}
                {i + 1}. {x.question}
              </p>
              <p className="text-sm">
                Your answer:{" "}
                {x.skipped || x.chosen_index == null ? (
                  <span className="text-destructive font-semibold">not answered</span>
                ) : (
                  <span
                    className={
                      x.correct
                        ? "text-success font-semibold"
                        : "text-destructive font-semibold"
                    }
                  >
                    {L[x.chosen_index]}. {x.options[x.chosen_index]}
                  </span>
                )}
              </p>
              {!x.correct && (
                <p className="text-sm">
                  Correct answer:{" "}
                  <span className="text-success font-semibold">
                    {x.correct_answer}
                  </span>
                </p>
              )}
              <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground leading-relaxed">
                {x.explanation}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  const doneCount = Object.keys(picked).length
  const totalQuestions = quiz.questions.length
  const currentQ = quiz.questions[currentIdx] || quiz.questions[0]

  return (
    <div className="space-y-6 relative">
      {crumbs}

      {/* Sticky Test Header Bar with Timer, Progress & Pause Control */}
      <div className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-background/95 backdrop-blur-md p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight">{mod.name}</h1>
              <Badge variant="secondary">{LEVEL[level]}</Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Question {currentIdx + 1} of {totalQuestions} · {doneCount} answered
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Timer Display */}
          {secondsLeft != null && (
            <div
              className={cn(
                "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-semibold transition-colors",
                secondsLeft <= 120
                  ? "border-destructive text-destructive bg-destructive/10 animate-pulse"
                  : "border-primary/30 bg-primary/5 text-foreground"
              )}
            >
              <Clock className="h-4 w-4" />
              <span>{formatTime(secondsLeft)}</span>
              <span className="text-xs font-normal text-muted-foreground hidden sm:inline">
                (2m / q)
              </span>
            </div>
          )}

          {/* Pause / Resume Button */}
          {level !== "practice" && (
            <Button
              variant={isPaused ? "default" : "outline"}
              size="sm"
              onClick={togglePause}
              disabled={pauseBusy || busy}
              className="gap-1.5 font-medium"
            >
              {isPaused ? (
                <>
                  <Play className="h-4 w-4 fill-current" /> Resume
                </>
              ) : (
                <>
                  <Pause className="h-4 w-4" /> Pause
                </>
              )}
            </Button>
          )}

          {/* Direct Submit Button */}
          <Button
            size="sm"
            onClick={submit}
            disabled={busy || isPaused}
            className="gap-1.5 bg-primary text-primary-foreground font-semibold shadow-sm"
          >
            <Send className="h-3.5 w-3.5" /> Submit Test
          </Button>
        </div>
      </div>

      {/* Question Number Navigator Bar */}
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border bg-card/60 p-2.5">
        <span className="text-xs font-semibold text-muted-foreground mr-1">Questions:</span>
        {quiz.questions.map((q: any, i: number) => {
          const isAnswered = picked[q.id] != null
          const isCurrent = i === currentIdx
          return (
            <button
              key={q.id}
              type="button"
              disabled={isPaused}
              onClick={() => setCurrentIdx(i)}
              className={cn(
                "h-8 w-8 rounded-md text-xs font-semibold transition-all flex items-center justify-center",
                isCurrent
                  ? "ring-2 ring-primary ring-offset-1 bg-primary text-primary-foreground font-bold"
                  : isAnswered
                  ? "bg-secondary/80 text-foreground border border-primary/30"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              )}
            >
              {i + 1}
            </button>
          )
        })}
      </div>

      {/* Paused Screen Overlay */}
      {isPaused && (
        <Card className="border-2 border-dashed border-primary/40 bg-accent/20 p-10 text-center animate-in fade-in duration-200">
          <CardContent className="space-y-4 pt-4">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Pause className="h-8 w-8" />
            </div>
            <h2 className="text-2xl font-bold">Quiz is Paused</h2>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              The countdown timer has been halted. Take a breath and click Resume when you are ready to continue your test.
            </p>
            <Button size="lg" onClick={togglePause} disabled={pauseBusy} className="gap-2">
              <Play className="h-4 w-4 fill-current" /> Resume Quiz
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Active Question View */}
      {!isPaused && currentQ && (
        <Card className="transition-all shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <CardTitle className="text-lg font-semibold leading-relaxed">
              <span className="text-primary mr-2">Q{currentIdx + 1}.</span>
              {currentQ.question}
            </CardTitle>
            {currentQ.source && (
              <Badge variant="outline" className="text-xs text-muted-foreground shrink-0 hidden sm:inline-flex">
                {currentQ.source}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="space-y-3 pt-2">
            {currentQ.options.map((o: string, j: number) => {
              const isSelected = picked[currentQ.id] === j
              return (
                <button
                  key={j}
                  type="button"
                  onClick={() => setPicked({ ...picked, [currentQ.id]: j })}
                  className={cn(
                    "w-full flex items-center gap-3.5 rounded-xl border p-4 text-left text-sm font-medium transition-all hover:bg-accent/60",
                    isSelected
                      ? "border-primary bg-primary/10 ring-1 ring-primary text-foreground shadow-sm"
                      : "bg-card border-border/70"
                  )}
                >
                  <span
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors",
                      isSelected
                        ? "bg-primary text-primary-foreground"
                        : "border border-muted-foreground/30 bg-muted/60 text-muted-foreground"
                    )}
                  >
                    {L[j]}
                  </span>
                  <span className="flex-1 leading-relaxed">{o}</span>
                </button>
              )
            })}
          </CardContent>
        </Card>
      )}

      {/* Smooth Navigation Controls: Prev, Next, Submit */}
      {!isPaused && (
        <div className="flex items-center justify-between gap-4 pt-2">
          <Button
            variant="outline"
            disabled={currentIdx === 0}
            onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
            className="gap-1.5"
          >
            <ChevronLeft className="h-4 w-4" /> Previous
          </Button>

          <div className="text-xs text-muted-foreground font-medium">
            {doneCount} of {totalQuestions} answered
          </div>

          {currentIdx < totalQuestions - 1 ? (
            <Button
              onClick={() => setCurrentIdx((i) => Math.min(totalQuestions - 1, i + 1))}
              className="gap-1.5"
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              onClick={submit}
              disabled={busy}
              className="gap-1.5 bg-primary text-primary-foreground font-semibold"
            >
              <Send className="h-4 w-4" /> Finish & Submit
            </Button>
          )}
        </div>
      )}

      {err && (
        <div className="flex items-center gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{err}</span>
        </div>
      )}
    </div>
  )
}
