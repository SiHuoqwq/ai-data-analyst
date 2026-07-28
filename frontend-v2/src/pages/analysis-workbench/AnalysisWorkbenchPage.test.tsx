import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AnalysisWorkbenchPage } from './AnalysisWorkbenchPage'

const createConversation = vi.fn()
const createRun = vi.fn()
const cancelRun = vi.fn()
const subscribe = vi.fn()

let conversationData: Record<string, unknown> | undefined
let runData: Record<string, unknown> | undefined
let stepsData: Record<string, unknown>[] = []
let artifactsData: Record<string, unknown>[] = []

vi.mock('../../features/datasets/queries', () => ({
  useDataset: () => ({
    isPending: false,
    isError: false,
    data: {
      id: 'file-1',
      filename: '销售数据.csv',
      file_type: 'csv',
      row_count: 12,
      col_count: 3,
      columns: [],
      profile_report: '',
    },
  }),
}))

vi.mock('../../features/analysis/queries', () => ({
  analysisKeys: {
    conversation: (id: string) => ['analysis', 'conversation', id],
    run: (id: string) => ['analysis', 'run', id],
    steps: (id: string) => ['analysis', 'run', id, 'steps'],
    artifacts: (id: string) => ['analysis', 'run', id, 'artifacts'],
  },
  useConversationDetail: () => ({
    isPending: false,
    isError: false,
    data: conversationData,
    refetch: vi.fn(),
  }),
  useAnalysisRun: () => ({
    isPending: false,
    isError: false,
    data: runData,
    refetch: vi.fn().mockResolvedValue({ data: runData }),
  }),
  useAnalysisRunSteps: () => ({
    isPending: false,
    isError: false,
    data: stepsData,
    refetch: vi.fn().mockResolvedValue({ data: stepsData }),
  }),
  useAnalysisRunArtifacts: () => ({
    isPending: false,
    isError: false,
    data: artifactsData,
    refetch: vi.fn().mockResolvedValue({ data: artifactsData }),
  }),
  useCreateConversation: () => ({
    isPending: false,
    isError: false,
    mutateAsync: createConversation,
  }),
  useCreateAnalysisRun: () => ({
    isPending: false,
    isError: false,
    mutateAsync: createRun,
  }),
  useCancelAnalysisRun: () => ({
    isPending: false,
    isError: false,
    mutateAsync: cancelRun,
  }),
}))

vi.mock('../../api/v2-events', () => ({
  subscribeRunEvents: (...args: unknown[]) => subscribe(...args),
}))

vi.mock('../../features/analysis/event-state', () => ({
  createRunEventState: (runId: string) => ({
    runId,
    status: 'queued',
    lastSequence: 0,
    seenEventIds: [],
    stepEvents: [],
    artifactIds: [],
    terminal: false,
  }),
  applyRunEvent: (state: unknown) => state,
}))

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="当前地址">{location.pathname}{location.search}</output>
}

function renderPage(path = '/datasets/file-1/analysis') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/datasets/:fileId/analysis" element={<><AnalysisWorkbenchPage /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

const runningRun = {
  id: 'run-1',
  conversation_id: 'conversation-1',
  dataset_version_id: 'file-1',
  input_message_id: 'message-1',
  output_message_id: null,
  status: 'running',
  current_phase: 'analysis',
  progress: { completed_steps: 0, total_steps: 2 },
  failure: null,
  error: null,
  last_event_sequence: 2,
  allowed_actions: { cancel: true },
}

describe('AnalysisWorkbenchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    conversationData = undefined
    runData = undefined
    stepsData = []
    artifactsData = []
    subscribe.mockResolvedValue('terminal')
    createConversation.mockResolvedValue({
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
    })
    createRun.mockResolvedValue({
      message: { id: 'message-1', role: 'user', content_text: '分析销售数据', status: 'committed' },
      run: {
        id: 'run-1',
        conversation_id: 'conversation-1',
        dataset_version_id: 'file-1',
        input_message_id: 'message-1',
        output_message_id: null,
        status: 'queued',
      },
      events_url: '/api/v2/runs/run-1/events',
    })
  })

  it('creates a conversation only on the first real submission, then creates a run', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(createConversation).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('输入分析问题'), '分析销售数据')
    await user.click(screen.getByRole('button', { name: '开始分析' }))

    await waitFor(() => expect(createConversation).toHaveBeenCalledWith({
      file_id: 'file-1',
      title: '分析销售数据',
    }))
    expect(createRun).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: 'conversation-1',
      input: expect.objectContaining({
        message: '分析销售数据',
        dataset_version_id: 'file-1',
      }),
      idempotencyKey: expect.any(String),
    }))
    expect(screen.getByLabelText('当前地址')).toHaveTextContent(
      '/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1',
    )
  })

  it('uses an existing conversation and never creates another one', async () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [],
    }
    const user = userEvent.setup()
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1')

    await user.type(screen.getByLabelText('输入分析问题'), '查看地区分布')
    await user.keyboard('{Enter}')

    await waitFor(() => expect(createRun).toHaveBeenCalled())
    expect(createConversation).not.toHaveBeenCalled()
  })

  it('rejects a conversation that belongs to another dataset', () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'another-file',
      title: '其他数据',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [],
    }
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1')

    expect(screen.getByRole('alert')).toHaveTextContent('这条分析记录不属于当前数据集')
  })

  it('restores running state from URL and disables duplicate submission', () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [{ id: 'message-1', role: 'user', content: '分析销售数据', created_at: '2026-07-28T10:00:01Z' }],
    }
    runData = runningRun
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1')

    expect(screen.getAllByText('正在分析')).not.toHaveLength(0)
    expect(screen.getByRole('button', { name: '开始分析' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '取消分析' })).toBeEnabled()
    expect(subscribe).toHaveBeenCalledWith('run-1', expect.objectContaining({
      afterSequence: 2,
    }))
  })

  it('shows failed and cancelled runs without inventing an assistant answer', () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [{ id: 'message-1', role: 'user', content: '失败问题', created_at: '2026-07-28T10:00:01Z' }],
    }
    runData = { ...runningRun, status: 'failed', error: { message: '分析流程未能完成' } }
    const { rerender } = renderPage('/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1')
    expect(screen.getByRole('alert')).toHaveTextContent('分析失败')
    expect(screen.queryByText('助手回答')).not.toBeInTheDocument()

    runData = { ...runningRun, status: 'cancelled' }
    rerender(
      <MemoryRouter initialEntries={['/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1']}>
        <Routes><Route path="/datasets/:fileId/analysis" element={<AnalysisWorkbenchPage />} /></Routes>
      </MemoryRouter>,
    )
    expect(screen.getAllByText('已取消')).not.toHaveLength(0)
  })

  it('shows real steps in a closed-by-default details drawer', async () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [],
    }
    runData = { ...runningRun, status: 'completed' }
    stepsData = [{
      id: 'step-1',
      sequence: 1,
      phase: 'analysis',
      operation: 'profile',
      display_name: '读取数据',
      status: 'completed',
      output_summary: { summary: '已读取 12 行数据' },
      error: null,
      artifact_ids: [],
      started_at: '2026-07-28T10:00:01Z',
      finished_at: '2026-07-28T10:00:02Z',
    }]
    const user = userEvent.setup()
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1')

    expect(screen.queryByText('已读取 12 行数据')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '查看执行详情' }))
    expect(screen.getByText('读取数据')).toBeInTheDocument()
    expect(screen.getByText('已读取 12 行数据')).toBeInTheDocument()
  })

  it('renders all artifact types and a safe unknown fallback', () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [],
    }
    runData = { ...runningRun, status: 'completed' }
    artifactsData = [
      artifact('text', { format: 'markdown', content: '## 核心结论\n销售稳定' }),
      artifact('metric', { label: '记录数', value: 12, display_value: '12', unit: '行' }),
      artifact('table', {
        columns: [{ key: 'region', label: '地区', data_type: 'string' }],
        rows: [{ region: '华东' }],
      }),
      artifact('chart', {
        renderer: 'static-image',
        chart_type: 'bar',
        title: '地区分布',
        image_url: '/api/v2/artifacts/chart-1/download',
        alt_text: '地区分布柱状图',
      }),
      artifact('future-result', {}),
    ]
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1')

    expect(screen.getByRole('heading', { name: '核心结论' })).toBeInTheDocument()
    expect(screen.getByText('记录数')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: '地区' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '地区分布柱状图' })).toBeInTheDocument()
    expect(screen.getByText('暂不支持展示此分析结果。')).toBeInTheDocument()
  })

  it('keeps an empty question disabled and supports Shift+Enter', async () => {
    const user = userEvent.setup()
    renderPage()
    const submit = screen.getByRole('button', { name: '开始分析' })
    const input = screen.getByLabelText('输入分析问题')

    expect(submit).toBeDisabled()
    await user.type(input, '第一行{Shift>}{Enter}{/Shift}第二行')
    expect(input).toHaveValue('第一行\n第二行')
    expect(createRun).not.toHaveBeenCalled()
  })

  it('requests cancellation once and keeps the current question visible', async () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [{ id: 'message-1', role: 'user', content: '分析销售数据', created_at: '2026-07-28T10:00:01Z' }],
    }
    runData = runningRun
    cancelRun.mockResolvedValue({ ...runningRun, status: 'cancelled' })
    const user = userEvent.setup()
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1')

    await user.click(screen.getByRole('button', { name: '取消分析' }))

    await waitFor(() => expect(cancelRun).toHaveBeenCalledTimes(1))
    expect(cancelRun).toHaveBeenCalledWith('run-1')
    expect(screen.getByRole('heading', { name: '分析销售数据' })).toBeInTheDocument()
  })

  it('recovers persisted evidence through REST after an SSE disconnect', async () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [{ id: 'message-1', role: 'user', content: '分析销售数据', created_at: '2026-07-28T10:00:01Z' }],
    }
    runData = runningRun
    subscribe.mockResolvedValue('disconnected')
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1')

    expect(await screen.findByText('已通过服务器记录恢复当前结果')).toBeInTheDocument()
  })

  it('keeps multi-round history ordered while isolating the current result', () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [
        { id: 'user-1', role: 'user', content: '第一轮问题', created_at: '2026-07-28T10:00:01Z' },
        { id: 'assistant-1', role: 'assistant', content: '第一轮结论', created_at: '2026-07-28T10:00:02Z' },
        { id: 'message-1', role: 'user', content: '第二轮问题', created_at: '2026-07-28T10:00:03Z' },
        { id: 'assistant-2', role: 'assistant', content: '第二轮结论', created_at: '2026-07-28T10:00:04Z' },
      ],
    }
    runData = { ...runningRun, status: 'completed', output_message_id: 'assistant-2' }
    artifactsData = [artifact('text', { format: 'markdown', content: '第二轮结论' })]
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1&runId=run-1')

    const firstQuestion = screen.getByText('第一轮问题')
    const firstAnswer = screen.getByText('第一轮结论')
    expect(firstQuestion.compareDocumentPosition(firstAnswer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('heading', { name: '第二轮问题' })).toBeInTheDocument()
    expect(screen.getAllByText('第二轮结论')).toHaveLength(1)
  })

  it('reuses the same idempotency key when retrying one failed network submission', async () => {
    conversationData = {
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [],
    }
    createRun
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce({
        message: { id: 'message-1', role: 'user', content_text: '分析销售数据', status: 'committed' },
        run: { id: 'run-1', conversation_id: 'conversation-1', dataset_version_id: 'file-1', input_message_id: 'message-1', output_message_id: null, status: 'queued' },
        events_url: '/api/v2/runs/run-1/events',
      })
    const user = userEvent.setup()
    renderPage('/datasets/file-1/analysis?conversationId=conversation-1')
    await user.type(screen.getByLabelText('输入分析问题'), '分析销售数据')

    await user.click(screen.getByRole('button', { name: '开始分析' }))
    await screen.findByText('操作没有完成')
    await user.click(screen.getByRole('button', { name: '开始分析' }))

    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(2))
    expect(createRun.mock.calls[0][0].idempotencyKey).toBe(createRun.mock.calls[1][0].idempotencyKey)
  })
})

function artifact(artifactType: string, payload: Record<string, unknown>) {
  return {
    id: `${artifactType}-1`,
    dataset_version_id: 'file-1',
    run_id: 'run-1',
    run_step_id: 'step-1',
    artifact_type: artifactType,
    status: 'ready',
    title: '分析结果',
    content_format: 'json',
    payload,
    size_bytes: 10,
    row_count: null,
    download_available: false,
    created_at: '2026-07-28T10:00:00Z',
  }
}
