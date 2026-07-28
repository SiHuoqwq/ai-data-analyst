import { describe, expect, it } from 'vitest'
import { RunSSEParser } from '../../api/v2-events'
import { applyRunEvent, createRunEventState } from './event-state'
import type { V2EventEnvelope } from '../../types/v2'

const event = (
  sequence: number,
  eventType: V2EventEnvelope['event_type'],
  payload: Record<string, unknown> = {},
): V2EventEnvelope => ({
  event_id: `event-${sequence}`,
  event_type: eventType,
  run_id: 'run-1',
  sequence,
  timestamp: '2026-07-28T10:00:00Z',
  schema_version: '1.0',
  payload,
})

describe('RunSSEParser', () => {
  it('parses standard event, id and data fields across chunks', () => {
    const parser = new RunSSEParser('run-1')
    const first = parser.push('id: event-1\nevent: run.started\ndata: {"event_id":"event-1","event_type":"run.started",')
    const second = parser.push('"run_id":"run-1","sequence":1,"timestamp":"2026-07-28T10:00:00Z","schema_version":"1.0","payload":{"status":"queued"}}\n\n')

    expect(first).toEqual([])
    expect(second).toEqual([expect.objectContaining({
      event_id: 'event-1',
      event_type: 'run.started',
      sequence: 1,
    })])
  })

  it('ignores malformed JSON, mismatched event metadata and other runs', () => {
    const parser = new RunSSEParser('run-1')
    const output = parser.push([
      'id: bad',
      'event: run.status',
      'data: not-json',
      '',
      'id: event-2',
      'event: run.status',
      `data: ${JSON.stringify(event(2, 'step.started'))}`,
      '',
      'id: event-3',
      'event: run.status',
      `data: ${JSON.stringify({ ...event(3, 'run.status'), run_id: 'run-old' })}`,
      '',
      '',
    ].join('\n'))

    expect(output).toEqual([])
  })
})

describe('run event state', () => {
  it('accepts strictly newer events and ignores duplicates or older sequences', () => {
    let state = createRunEventState('run-1')
    state = applyRunEvent(state, event(1, 'run.started'))
    state = applyRunEvent(state, event(2, 'run.status', { status: 'running' }))
    state = applyRunEvent(state, event(2, 'run.status', { status: 'queued' }))
    state = applyRunEvent(state, { ...event(1, 'run.started'), event_id: 'another-id' })

    expect(state.lastSequence).toBe(2)
    expect(state.status).toBe('running')
    expect(state.seenEventIds).toEqual(['event-1', 'event-2'])
  })

  it('does not turn heartbeat into an analysis step', () => {
    const state = applyRunEvent(createRunEventState('run-1'), event(1, 'heartbeat'))

    expect(state.stepEvents).toEqual([])
    expect(state.lastSequence).toBe(1)
  })

  it.each([
    ['run.completed', 'completed'],
    ['run.failed', 'failed'],
    ['run.cancelled', 'cancelled'],
  ] as const)('marks %s as terminal', (eventType, status) => {
    const state = applyRunEvent(createRunEventState('run-1'), event(1, eventType))

    expect(state.status).toBe(status)
    expect(state.terminal).toBe(true)
  })

  it('collects only real step and artifact identifiers', () => {
    let state = createRunEventState('run-1')
    state = applyRunEvent(state, event(1, 'step.started', { step_id: 'step-1' }))
    state = applyRunEvent(state, event(2, 'artifact.created', { artifact_id: 'artifact-1' }))

    expect(state.stepEvents).toHaveLength(1)
    expect(state.artifactIds).toEqual(['artifact-1'])
  })
})
