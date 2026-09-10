import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppError } from './errors'
import { createV2Conversation, getConversationDetail } from './v2-conversations'
import {
  cancelAnalysisRun,
  createAnalysisRun,
  getAnalysisRun,
  listAnalysisRunSteps,
} from './v2-runs'
import { getArtifact, listAnalysisRunArtifacts } from './v2-artifacts'
import { getDatasetRecommendations } from './v2-recommendations'

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

describe('V2 API client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('creates a conversation with the real V2 request shape', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        data: {
          id: 'conversation-1',
          file_id: 'file-1',
          title: '销售分析',
          mode: 'agent',
          created_at: '2026-07-28T10:00:00Z',
        },
        meta: { request_id: 'request-1', schema_version: '1.0' },
      }, 201),
    )

    const result = await createV2Conversation({ file_id: 'file-1', title: '销售分析' })

    expect(result.id).toBe('conversation-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/conversations',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ file_id: 'file-1', title: '销售分析' }),
      }),
    )
  })

  it('creates a run with one explicit Idempotency-Key', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        data: {
          message: { id: 'message-1', role: 'user', content_text: '分析数据', status: 'committed' },
          run: {
            id: 'run-1',
            conversation_id: 'conversation-1',
            status: 'queued',
            dataset_version_id: 'file-1',
            input_message_id: 'message-1',
            output_message_id: null,
          },
          events_url: '/api/v2/runs/run-1/events',
        },
        meta: { request_id: 'request-1', schema_version: '1.0' },
      }, 202),
    )

    const result = await createAnalysisRun(
      'conversation-1',
      {
        message: '分析数据',
        dataset_version_id: 'file-1',
        recommendation_id: 'group-comparison-abcd1234',
      },
      'submit-key-1',
    )

    expect(result.run.id).toBe('run-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/conversations/conversation-1/runs',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'Idempotency-Key': 'submit-key-1' }),
        body: JSON.stringify({
          message: '分析数据',
          dataset_version_id: 'file-1',
          recommendation_id: 'group-comparison-abcd1234',
        }),
      }),
    )
  })

  it('gets typed recommendations for the requested dataset', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      data: {
        dataset_version_id: 'file-1',
        source: 'template',
        generated_at: '2026-08-06T10:00:00Z',
        recommendations: [{
          id: 'recommendation-1',
          intent_type: 'group_comparison',
          label: '渠道成交表现',
          question: '比较各获客渠道的成交表现。',
          referenced_fields: ['获客渠道', '成交转化率'],
        }],
      },
      meta: metaFixture,
    }))

    await expect(getDatasetRecommendations('file / 1')).resolves.toMatchObject({
      dataset_version_id: 'file-1',
      source: 'template',
      recommendations: [{ id: 'recommendation-1', intent_type: 'group_comparison' }],
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/datasets/file%20%2F%201/recommendations',
      expect.any(Object),
    )
  })

  it('queries run, steps, artifacts and one artifact', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ data: runFixture, meta: metaFixture }))
      .mockResolvedValueOnce(jsonResponse({ data: [stepFixture], meta: metaFixture }))
      .mockResolvedValueOnce(jsonResponse({ data: [artifactFixture], meta: metaFixture }))
      .mockResolvedValueOnce(jsonResponse({ data: artifactFixture, meta: metaFixture }))

    await expect(getAnalysisRun('run-1')).resolves.toMatchObject({ id: 'run-1' })
    await expect(listAnalysisRunSteps('run-1')).resolves.toHaveLength(1)
    await expect(listAnalysisRunArtifacts('run-1')).resolves.toHaveLength(1)
    await expect(getArtifact('artifact-1')).resolves.toMatchObject({ artifact_type: 'text' })
    expect(fetchMock).toHaveBeenCalledTimes(4)
  })

  it('sends a cooperative cancellation request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ data: { ...runFixture, status: 'cancelled' }, meta: metaFixture }, 202),
    )

    await expect(cancelAnalysisRun('run-1')).resolves.toMatchObject({ status: 'cancelled' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/runs/run-1/cancel',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ reason: 'user_requested' }),
      }),
    )
  })

  it('reads the real V1 conversation detail shape', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      id: 'conversation-1',
      file_id: 'file-1',
      title: '销售分析',
      mode: 'agent',
      created_at: '2026-07-28T10:00:00Z',
      messages: [{
        id: 'message-1',
        role: 'user',
        content: '分析数据',
        tool_calls: null,
        chart_ids: [],
        created_at: '2026-07-28T10:00:01Z',
      }],
    }))

    await expect(getConversationDetail('conversation-1')).resolves.toMatchObject({
      file_id: 'file-1',
      messages: [{ role: 'user' }],
    })
  })

  it('normalizes the V2 error envelope without exposing implementation details', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        error: {
          code: 'IDEMPOTENCY_CONFLICT',
          message: '该请求与之前的提交不一致',
          details: {},
          retryable: false,
          request_id: 'request-1',
        },
      }, 409),
    )

    const error = await createAnalysisRun(
      'conversation-1',
      { message: '另一个问题', dataset_version_id: 'file-1' },
      'submit-key-1',
    ).catch((value: unknown) => value)

    expect(error).toBeInstanceOf(AppError)
    expect(error).toMatchObject({
      status: 409,
      code: 'IDEMPOTENCY_CONFLICT',
      message: '该请求与之前的提交不一致',
      retryable: false,
    })
  })

  it('rejects an invalid success payload', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ data: { id: 42 } }))

    const error = await getAnalysisRun('run-1').catch((value: unknown) => value)

    expect(error).toBeInstanceOf(AppError)
    expect(error).toMatchObject({ code: 'invalid_response', retryable: false })
  })
})

const metaFixture = { request_id: 'request-1', schema_version: '1.0' }

const runFixture = {
  id: 'run-1',
  conversation_id: 'conversation-1',
  dataset_version_id: 'file-1',
  trigger_message_id: 'message-1',
  answer_message_id: null,
  input_message_id: 'message-1',
  output_message_id: null,
  status: 'running',
  current_phase: 'analysis',
  progress: { completed_steps: 0, total_steps: 2 },
  failure: null,
  created_at: '2026-07-28T10:00:00Z',
  updated_at: '2026-07-28T10:00:01Z',
  started_at: '2026-07-28T10:00:01Z',
  completed_at: null,
  finished_at: null,
  cancelled_at: null,
  error: null,
  last_event_sequence: 2,
  allowed_actions: { cancel: true },
}

const stepFixture = {
  id: 'step-1',
  plan_step_id: null,
  sequence: 1,
  phase: 'analysis',
  operation: 'profile',
  display_name: '数据概览',
  status: 'completed',
  attempt: 1,
  max_attempts: 1,
  output_summary: { summary: '已完成' },
  error: null,
  artifact_ids: ['artifact-1'],
  started_at: '2026-07-28T10:00:01Z',
  finished_at: '2026-07-28T10:00:02Z',
}

const artifactFixture = {
  id: 'artifact-1',
  dataset_version_id: 'file-1',
  run_id: 'run-1',
  run_step_id: 'step-1',
  artifact_type: 'text',
  status: 'ready',
  title: '分析结论',
  content_format: 'markdown',
  payload: { format: 'markdown', content: '结果' },
  size_bytes: 6,
  row_count: null,
  download_available: false,
  created_at: '2026-07-28T10:00:02Z',
}
