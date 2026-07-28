import { apiUrl } from './client'
import { asAppError, normalizeError } from './errors'
import { parseEventEnvelope } from './v2-contracts'
import type { V2EventEnvelope } from '../types/v2'

const terminalEvents = new Set(['run.completed', 'run.failed', 'run.cancelled'])

export class RunSSEParser {
  private buffer = ''

  constructor(private readonly runId: string) {}

  push(chunk: string): V2EventEnvelope[] {
    this.buffer += chunk.replace(/\r\n/g, '\n')
    const blocks = this.buffer.split('\n\n')
    this.buffer = blocks.pop() ?? ''
    const events: V2EventEnvelope[] = []

    for (const block of blocks) {
      let wireEvent = ''
      let wireId = ''
      const dataLines: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) wireEvent = line.slice(6).trim()
        else if (line.startsWith('id:')) wireId = line.slice(3).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (!dataLines.length) continue
      try {
        const envelope = parseEventEnvelope(JSON.parse(dataLines.join('\n')))
        if (!envelope || envelope.run_id !== this.runId
          || envelope.event_id !== wireId || envelope.event_type !== wireEvent) continue
        events.push(envelope)
      } catch {
        // Malformed event data is ignored; REST recovery remains the source of truth.
      }
    }
    return events
  }
}

export interface SubscribeRunEventsOptions {
  signal: AbortSignal
  afterSequence?: number
  onEvent: (event: V2EventEnvelope) => void
}

export async function subscribeRunEvents(
  runId: string,
  { signal, afterSequence = 0, onEvent }: SubscribeRunEventsOptions,
): Promise<'terminal' | 'disconnected'> {
  const params = afterSequence > 0 ? `?after_sequence=${afterSequence}` : ''
  try {
    const response = await fetch(apiUrl(`/api/v2/runs/${encodeURIComponent(runId)}/events${params}`), {
      headers: { Accept: 'text/event-stream' },
      signal,
    })
    if (!response.ok) throw await normalizeError(response)
    if (!response.body) return 'disconnected'

    const parser = new RunSSEParser(runId)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    while (!signal.aborted) {
      const { done, value } = await reader.read()
      if (done) return 'disconnected'
      for (const event of parser.push(decoder.decode(value, { stream: true }))) {
        onEvent(event)
        if (terminalEvents.has(event.event_type)) {
          await reader.cancel()
          return 'terminal'
        }
      }
    }
    await reader.cancel()
    return 'disconnected'
  } catch (error) {
    if (signal.aborted) return 'disconnected'
    throw asAppError(error)
  }
}
