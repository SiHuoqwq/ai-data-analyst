import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(
  join(process.cwd(), 'src/styles/globals.css'),
  'utf8',
)

describe('analysis workbench narrow layout safeguards', () => {
  it('fixes overflow at the responsible containers', () => {
    expect(css).not.toMatch(/body\s*\{[^}]*overflow-x:\s*hidden/)
    expect(css).not.toMatch(/html\s*\{[^}]*overflow-x:\s*hidden/)
    expect(css).toContain('.workbench-page { --canvas-width: 940px; min-width: 0;')
    expect(css).toContain('.question-card { min-width: 0;')
    expect(css).toContain('.artifact-table,.artifact-chart { min-width: 0; max-width: 100%;')
    expect(css).toContain('.chart-image-button img { display: block; width: 100%;')
    expect(css).toContain('overflow-wrap: anywhere; word-break: break-word;')
  })

  it('allows the long dataset title to wrap on narrow screens', () => {
    expect(css).toMatch(
      /@media \(max-width: 800px\)[\s\S]*?\.workbench-context h1 \{[^}]*white-space: normal;[^}]*overflow-wrap: anywhere;/,
    )
  })
})
