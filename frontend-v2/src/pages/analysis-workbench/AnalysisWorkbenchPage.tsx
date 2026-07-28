import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  LoaderCircle,
  PanelRightOpen,
  Send,
  Square,
  X,
} from 'lucide-react'
import { type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { subscribeRunEvents } from '../../api/v2-events'
import { asAppError } from '../../api/errors'
import { ErrorState } from '../../components/feedback/ErrorState'
import { LoadingState } from '../../components/feedback/LoadingState'
import { MarkdownContent } from '../../components/feedback/MarkdownContent'
import { Button } from '../../components/ui/Button'
import { useDataset } from '../../features/datasets/queries'
import { ArtifactView } from '../../features/analysis/ArtifactView'
import {
  useAnalysisRun,
  useAnalysisRunArtifacts,
  useAnalysisRunSteps,
  useCancelAnalysisRun,
  useConversationDetail,
  useCreateAnalysisRun,
  useCreateConversation,
} from '../../features/analysis/queries'
import { applyRunEvent, createRunEventState } from '../../features/analysis/event-state'
import { formatDate, formatNumber } from '../../utils/format'
import type { AnalysisRun, ConversationMessage, RunStatus, RunStep } from '../../types/v2'

const statusCopy: Record<RunStatus, string> = {
  queued: '正在排队',
  running: '正在分析',
  completed: '分析完成',
  failed: '分析失败',
  cancelled: '已取消',
}

const statusIcon = {
  queued: Clock3,
  running: LoaderCircle,
  completed: CheckCircle2,
  failed: CircleAlert,
  cancelled: Square,
}

const isActive = (status?: RunStatus) => status === 'queued' || status === 'running'

const newSubmissionKey = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `submission-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const summaryText = (value: Record<string, unknown> | null) => {
  if (!value) return null
  if (typeof value.summary === 'string') return value.summary
  if (typeof value.message === 'string') return value.message
  return null
}

function RunStatusBadge({ status }: { status: RunStatus }) {
  const Icon = statusIcon[status]
  return <span className={`run-status run-status-${status}`} role="status">
    <Icon className={status === 'running' ? 'spin' : ''} size={15} />
    {statusCopy[status]}
  </span>
}

function ConversationHistory({
  messages,
  activeRun,
}: {
  messages: ConversationMessage[]
  activeRun?: AnalysisRun
}) {
  const hiddenIds = new Set(
    [activeRun?.input_message_id, activeRun?.output_message_id].filter(Boolean),
  )
  const history = messages.filter((message) => !hiddenIds.has(message.id))
  if (!history.length) return null
  return <section className="analysis-history" aria-labelledby="history-heading">
    <div className="workbench-section-heading">
      <div><span className="eyebrow">当前会话</span><h2 id="history-heading">会话记录</h2></div>
      <span>{history.length} 条消息</span>
    </div>
    <div className="history-ledger">
      {history.map((message) => <article className={`history-message history-${message.role}`} key={message.id}>
        <div><strong>{message.role === 'user' ? '你的问题' : '分析结论'}</strong><time>{formatDate(message.created_at)}</time></div>
        {message.role === 'assistant'
          ? <MarkdownContent content={message.content} />
          : <p>{message.content}</p>}
      </article>)}
    </div>
  </section>
}

function ExecutionDrawer({
  open,
  steps,
  onClose,
}: {
  open: boolean
  steps: RunStep[]
  onClose: () => void
}) {
  useEffect(() => {
    if (!open) return
    const handleKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose])
  if (!open) return null
  return <div className="drawer-backdrop" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose()
  }}>
    <aside className="execution-drawer" role="dialog" aria-modal="true" aria-labelledby="execution-title">
      <header>
        <div><span className="eyebrow">运行过程</span><h2 id="execution-title">执行详情</h2></div>
        <button className="icon-button" type="button" aria-label="关闭执行详情" onClick={onClose}><X /></button>
      </header>
      {!steps.length && <p className="drawer-empty">服务端还没有记录分析步骤。</p>}
      <ol className="step-list">
        {steps.map((step) => <li key={step.id}>
          <span className={`step-marker step-${step.status}`} aria-hidden="true" />
          <div>
            <div className="step-title"><strong>{step.display_name}</strong><span>{step.status === 'completed' ? '已完成' : step.status === 'running' ? '进行中' : step.status}</span></div>
            {summaryText(step.output_summary) && <p>{summaryText(step.output_summary)}</p>}
            {summaryText(step.error) && <p className="step-error">{summaryText(step.error)}</p>}
            <small>{step.started_at ? formatDate(step.started_at) : '尚未开始'}{step.finished_at ? ` — ${formatDate(step.finished_at)}` : ''}</small>
          </div>
        </li>)}
      </ol>
    </aside>
  </div>
}

export function AnalysisWorkbenchPage() {
  const { fileId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationId = searchParams.get('conversationId') || ''
  const runId = searchParams.get('runId') || ''
  const dataset = useDataset(fileId)
  const conversation = useConversationDetail(conversationId)
  const run = useAnalysisRun(runId)
  const steps = useAnalysisRunSteps(runId)
  const artifacts = useAnalysisRunArtifacts(runId)
  const createConversation = useCreateConversation()
  const createRun = useCreateAnalysisRun()
  const cancelRun = useCancelAnalysisRun()
  const [question, setQuestion] = useState('')
  const [activeQuestion, setActiveQuestion] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [submittingError, setSubmittingError] = useState<unknown>(null)
  const [streamNotice, setStreamNotice] = useState<{ runId: string; message: string } | null>(null)
  const [pendingSubmission, setPendingSubmission] = useState<{ question: string; key: string } | null>(null)
  const [eventState, setEventState] = useState(() => createRunEventState(runId))
  const streamRunRef = useRef('')
  const refetchRun = run.refetch
  const refetchSteps = steps.refetch
  const refetchArtifacts = artifacts.refetch
  const refetchConversation = conversation.refetch
  const streamRunStatus = run.data?.status
  const streamRunSequence = run.data?.last_event_sequence ?? 0

  useEffect(() => {
    if (!runId || !isActive(streamRunStatus)) return
    const controller = new AbortController()
    streamRunRef.current = runId
    const recover = async () => {
      setStreamNotice({ runId, message: '实时连接已中断，正在恢复状态' })
      const results = await Promise.allSettled([
        refetchRun(),
        refetchSteps(),
        refetchArtifacts(),
      ])
      if (streamRunRef.current !== runId) return
      if (results.every((result) => result.status === 'fulfilled')) {
        setStreamNotice({ runId, message: '已通过服务器记录恢复当前结果' })
      } else {
        setStreamNotice({ runId, message: '状态恢复未完成，请手动重试' })
      }
    }
    void subscribeRunEvents(runId, {
      signal: controller.signal,
      afterSequence: streamRunSequence,
      onEvent: (event) => {
        if (streamRunRef.current !== event.run_id) return
        setEventState((current) => applyRunEvent(
          current.runId === event.run_id ? current : createRunEventState(event.run_id),
          event,
        ))
        if (event.event_type === 'artifact.created') void refetchArtifacts()
        if (event.event_type === 'step.started' || event.event_type === 'step.completed') void refetchSteps()
        if (event.event_type === 'run.status') void refetchRun()
        if (event.event_type === 'run.completed' || event.event_type === 'run.failed'
          || event.event_type === 'run.cancelled') {
          void Promise.all([
            refetchRun(),
            refetchSteps(),
            refetchArtifacts(),
            refetchConversation(),
          ])
        }
      },
    }).then((result) => {
      if (result === 'disconnected' && !controller.signal.aborted) void recover()
    }).catch(() => {
      if (!controller.signal.aborted) void recover()
    })
    return () => controller.abort()
  }, [
    runId,
    streamRunStatus,
    streamRunSequence,
    refetchRun,
    refetchSteps,
    refetchArtifacts,
    refetchConversation,
  ])

  const serverStatus = run.data?.status
  const currentStatus = eventState.runId === runId
    && eventState.lastSequence > (run.data?.last_event_sequence ?? 0)
    ? eventState.status
    : serverStatus
  const active = isActive(currentStatus)
  const conversationMismatch = Boolean(
    conversationId && conversation.data && conversation.data.file_id !== fileId,
  )
  const runMismatch = Boolean(
    runId && run.data && (
      run.data.conversation_id !== conversationId
      || run.data.dataset_version_id !== fileId
    ),
  )
  const currentQuestion = useMemo(() => {
    if (activeQuestion) return activeQuestion
    return conversation.data?.messages.find((message) => message.id === run.data?.input_message_id)?.content || ''
  }, [activeQuestion, conversation.data?.messages, run.data?.input_message_id])
  const textArtifacts = artifacts.data?.filter((item) => item.artifact_type === 'text') ?? []
  const metricArtifacts = artifacts.data?.filter((item) => item.artifact_type === 'metric') ?? []
  const contentArtifacts = artifacts.data?.filter((item) => item.artifact_type !== 'text' && item.artifact_type !== 'metric') ?? []
  const fallbackAnswer = !textArtifacts.length
    ? conversation.data?.messages.find((message) => message.id === run.data?.output_message_id)
    : undefined
  const busy = active || createConversation.isPending || createRun.isPending

  const submitQuestion = async (event?: FormEvent) => {
    event?.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || busy || conversationMismatch) return
    setSubmittingError(null)
    setActiveQuestion(trimmed)
    const submission = pendingSubmission?.question === trimmed
      ? pendingSubmission
      : { question: trimmed, key: newSubmissionKey() }
    setPendingSubmission(submission)
    try {
      let resolvedConversationId = conversationId
      if (!resolvedConversationId) {
        const created = await createConversation.mutateAsync({
          file_id: fileId,
          title: trimmed.slice(0, 50),
        })
        resolvedConversationId = created.id
        setSearchParams({ conversationId: created.id }, { replace: true })
      }
      const createdRun = await createRun.mutateAsync({
        conversationId: resolvedConversationId,
        input: {
          message: trimmed,
          dataset_version_id: fileId,
          context: { include_message_ids: [], include_artifact_ids: [] },
        },
        idempotencyKey: submission.key,
      })
      setQuestion('')
      setPendingSubmission(null)
      setSearchParams({
        conversationId: resolvedConversationId,
        runId: createdRun.run.id,
      }, { replace: true })
    } catch (error) {
      setSubmittingError(error)
    }
  }

  const handleInputKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submitQuestion()
    }
  }

  const requestCancel = async () => {
    if (!runId || cancelRun.isPending) return
    setSubmittingError(null)
    try {
      await cancelRun.mutateAsync(runId)
      await Promise.all([run.refetch(), steps.refetch(), artifacts.refetch()])
    } catch (error) {
      setSubmittingError(error)
      if (asAppError(error).code === 'RUN_NOT_CANCELLABLE') {
        await run.refetch()
      }
    }
  }

  if (dataset.isPending) return <div className="page"><LoadingState label="正在加载数据集" /></div>
  if (dataset.isError) return <div className="page"><ErrorState error={dataset.error} onRetry={() => void dataset.refetch()} /></div>
  if (conversationId && conversation.isPending) return <div className="page"><LoadingState label="正在恢复分析记录" /></div>
  if (conversationId && conversation.isError) return <div className="page"><ErrorState error={conversation.error} onRetry={() => void conversation.refetch()} /></div>
  if (conversationMismatch) return <div className="page"><div className="state-panel error-state" role="alert"><CircleAlert /><strong>这条分析记录不属于当前数据集</strong><p>请返回数据集概览，选择正确的分析记录。</p><Link className="button button-secondary" to={`/datasets/${fileId}`}>返回数据集概览</Link></div></div>
  if (runId && run.isPending) return <div className="page"><LoadingState label="正在恢复分析状态" /></div>
  if (runId && run.isError) return <div className="page"><ErrorState error={run.error} onRetry={() => void run.refetch()} /></div>
  if (runMismatch) return <div className="page"><div className="state-panel error-state" role="alert"><CircleAlert /><strong>当前分析任务与数据集或会话不匹配</strong><p>请从正确的数据集记录重新进入。</p><Link className="button button-secondary" to={`/datasets/${fileId}`}>返回数据集概览</Link></div></div>

  return <div className="page workbench-page">
    <header className="workbench-header">
      <div className="workbench-context">
        <Link className="back-link" to={`/datasets/${fileId}`}><ArrowLeft size={15} />返回数据集概览</Link>
        <span className="eyebrow">分析工作台</span>
        <h1 title={dataset.data.filename}>{dataset.data.filename}</h1>
        <p>{formatNumber(dataset.data.row_count)} 行 · {formatNumber(dataset.data.col_count)} 列</p>
      </div>
      <div className="workbench-actions">
        {currentStatus && <RunStatusBadge status={currentStatus} />}
        {runId && <Button variant="secondary" onClick={() => setDrawerOpen(true)}><PanelRightOpen size={16} />查看执行详情</Button>}
        {active && <Button variant="secondary" disabled={cancelRun.isPending} onClick={() => void requestCancel()}>
          <Square size={14} />{cancelRun.isPending ? '正在取消' : '取消分析'}
        </Button>}
      </div>
    </header>

    <main className="analysis-canvas">
      {!runId && conversation.data?.messages && <ConversationHistory messages={conversation.data.messages} activeRun={run.data} />}

      {!runId && <section className="analysis-welcome">
        <div><span>01</span><ChevronRight /></div>
        <h2>从一个明确的问题开始</h2>
        <p>例如：哪些字段最值得关注？数据中是否存在明显分组差异？</p>
      </section>}

      {runId && <section className="active-analysis" aria-labelledby="current-analysis-heading">
        <div className="question-card">
          <span className="eyebrow">本轮问题</span>
          <h2 id="current-analysis-heading">{currentQuestion || '正在读取本轮问题'}</h2>
        </div>

        {active && <div className="running-panel" aria-live="polite">
          <LoaderCircle className="spin" size={21} />
          <div><strong>{currentStatus ? statusCopy[currentStatus] : '正在准备'}</strong><p>结果会在分析步骤完成后逐项出现。</p></div>
        </div>}

        {streamNotice?.runId === runId && <div className="recovery-note" role="status">
          <span>{streamNotice.message}</span>
          {streamNotice.message.includes('未完成') && <Button variant="secondary" onClick={() => void Promise.all([run.refetch(), steps.refetch(), artifacts.refetch()])}>重试恢复</Button>}
        </div>}

        {metricArtifacts.length > 0 && <section aria-labelledby="metrics-heading">
          <div className="workbench-section-heading"><div><span className="eyebrow">关键指标</span><h2 id="metrics-heading">数据概览</h2></div></div>
          <div className="result-metrics">{metricArtifacts.map((artifact) => <ArtifactView artifact={artifact} key={artifact.id} />)}</div>
        </section>}

        {(textArtifacts.length > 0 || fallbackAnswer) && currentStatus !== 'cancelled' && currentStatus !== 'failed' && <section aria-labelledby="answer-heading">
          <div className="workbench-section-heading"><div><span className="eyebrow">分析结论</span><h2 id="answer-heading">核心发现</h2></div></div>
          <div className="answer-panel">
            {textArtifacts.map((artifact) => <ArtifactView artifact={artifact} key={artifact.id} />)}
            {!textArtifacts.length && fallbackAnswer && <MarkdownContent content={fallbackAnswer.content} />}
          </div>
        </section>}

        {contentArtifacts.length > 0 && <section className="evidence-stack" aria-labelledby="evidence-heading">
          <div className="workbench-section-heading"><div><span className="eyebrow">分析依据</span><h2 id="evidence-heading">表格与图表</h2></div></div>
          {contentArtifacts.map((artifact) => <ArtifactView artifact={artifact} key={artifact.id} />)}
        </section>}

        {currentStatus === 'failed' && <div className="run-outcome run-outcome-failed" role="alert">
          <CircleAlert /><div><strong>分析失败</strong><p>{summaryText(run.data?.error ?? null) || '本轮分析未能完成，可以修改问题后重新尝试。'}</p></div>
        </div>}
        {currentStatus === 'cancelled' && <div className="run-outcome">
          <Square /><div><strong>已取消</strong><p>本轮分析已停止，已经生成的结果会继续保留。</p></div>
        </div>}
      </section>}
      {runId && conversation.data?.messages && <ConversationHistory messages={conversation.data.messages} activeRun={run.data} />}
    </main>

    {Boolean(submittingError) && <div className="workbench-error" role="alert">
      <CircleAlert size={18} /><div><strong>操作没有完成</strong><p>{asAppError(submittingError).message}</p></div>
    </div>}

    <form className="analysis-composer" onSubmit={(event) => void submitQuestion(event)}>
      <label htmlFor="analysis-question">继续分析这个数据集</label>
      <div>
        <textarea
          id="analysis-question"
          aria-label="输入分析问题"
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value)
            if (pendingSubmission?.question !== event.target.value.trim()) setPendingSubmission(null)
          }}
          onKeyDown={handleInputKey}
          placeholder="输入你想了解的数据问题…"
          rows={3}
          disabled={busy}
        />
        <Button type="submit" disabled={!question.trim() || busy}><Send size={16} />开始分析</Button>
      </div>
      <p>Enter 发送，Shift+Enter 换行 · 结果由数据计算和分析流程生成。</p>
    </form>

    <ExecutionDrawer open={drawerOpen} steps={steps.data ?? []} onClose={() => setDrawerOpen(false)} />
  </div>
}
