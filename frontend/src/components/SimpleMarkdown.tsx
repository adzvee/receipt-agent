import type { ReactNode } from 'react'

// The chat model replies with light Markdown (**bold** and bullet lists). This renders just
// that, as React elements: model output is never inserted as HTML, so it can't inject markup.

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  )
}

export function SimpleMarkdown({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let bullets: string[] = []

  const flushBullets = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={blocks.length}>
          {bullets.map((item, i) => (
            <li key={i}>{renderInline(item)}</li>
          ))}
        </ul>,
      )
      bullets = []
    }
  }

  for (const line of text.split('\n')) {
    const bullet = line.match(/^\s*[*-]\s+(.*)$/)
    if (bullet) {
      bullets.push(bullet[1])
    } else {
      flushBullets()
      if (line.trim()) blocks.push(<p key={blocks.length}>{renderInline(line)}</p>)
    }
  }
  flushBullets()
  return <>{blocks}</>
}
