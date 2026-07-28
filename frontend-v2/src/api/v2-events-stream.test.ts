import { describe, expect, it, vi } from 'vitest'
import { subscribeRunEvents } from './v2-events'
import type { V2EventEnvelope, V2EventType } from '../types/v2'

const envelope = (sequence: number, eventType: V2EventType): V2EventEnvelope => ({
  event_id: `event-${sequence}`,
  event_type: eventType,
  run_id: 'run-1',
  sequence,
  timestamp: '2026-07-28T10:00:00Z',
  schema_version: '1.0',
  payload: eventType === 'run.status' ? { status: 'running' } : {},
})

const wire = (event: V2EventEnvelope) =>
  `id: ${event.event_id}\nevent: ${event.event_type}\ndata: ${JSON.stringify(event)}\n\n`

const streamResponse = (...chunks: string[]) => new Response(new ReadableStream({
  start(controller) {
    const encoder = new TextEncoder()
    chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
    controller.close()
  },
}), { status: 200, headers: { 'Content-Type': 'text/event-stream' } })

describe('subscribeRunEvents', () => {
  it('delivers standard events and closes on completed before later data', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(
      wire(envelope(1, 'run.started')),
      wire(envelope(2, 'heartbeat')),
      wire(envelope(3, 'run.completed')),
      wire(envelope(4, 'step.completed')),
    ))
    const received: V2EventEnvelope[] = []

    const result = await subscribeRunEvents('run-1', {
      signal: new AbortController().signal,
      afterSequence: 0,
      onEvent: (event) => received.push(event),
    })

    expect(result).toBe('terminal')
    expect(received.map((event) => event.event_type)).toEqual([
      'run.started',
      'heartbeat',
      'run.completed',
    ])
  })

  it.each(['run.failed', 'run.cancelled'] as const)('closes on %s', async (terminalType) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(wire(envelope(1, terminalType))))

    await expect(subscribeRunEvents('run-1', {
      signal: new AbortController().signal,
      onEvent: vi.fn(),
    })).resolves.toBe('terminal')
  })

  it('ignores illegal JSON and reports an ordinary closed stream as disconnected', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(
      'id: broken\nevent: run.status\ndata: {bad-json}\n\n',
    ))
    const onEvent = vi.fn()

    await expect(subscribeRunEvents('run-1', {
      signal: new AbortController().signal,
      onEvent,
    })).resolves.toBe('disconnected')
    expect(onEvent).not.toHaveBeenCalled()
  })
})
