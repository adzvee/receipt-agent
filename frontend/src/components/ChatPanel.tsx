import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { askQuestion, type ChatTurn, type ToolCall } from '../api'
import { describeToolCall } from '../format'
import { SimpleMarkdown } from './SimpleMarkdown'

const SUGGESTIONS = [
  'How much did I spend on food last month?',
  'What were my biggest purchases this year?',
  'Which receipts need review?',
]

interface Message extends ChatTurn {
  toolCalls?: ToolCall[]
}

export function ChatPanel() {
  const queryClient = useQueryClient()
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')

  const ask = useMutation({
    mutationFn: ({ question, history }: { question: string; history: ChatTurn[] }) =>
      askQuestion(question, history),
    onSuccess: (response) => {
      setMessages((current) => [
        ...current,
        { role: 'assistant', content: response.answer, toolCalls: response.tool_calls },
      ])
      queryClient.invalidateQueries({ queryKey: ['me'] }) // demo request count
    },
  })

  function send(question: string) {
    const text = question.trim()
    if (!text || ask.isPending) return
    // Earlier turns go along so follow-ups ("and in October?") have context.
    const history = messages.map(({ role, content }) => ({ role, content }))
    setMessages((current) => [...current, { role: 'user', content: text }])
    setDraft('')
    ask.mutate({ question: text, history })
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    send(draft)
  }

  return (
    <section className="card chat" aria-label="Ask about your spending">
      <h2>Ask about your spending</h2>

      <div className="chat-log" aria-live="polite">
        {messages.length === 0 && (
          <div className="suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => send(suggestion)}>
                {suggestion}
              </button>
            ))}
          </div>
        )}
        {messages.map((message, i) => (
          <div key={i} className={`message message-${message.role}`}>
            {message.role === 'assistant' ? (
              <SimpleMarkdown text={message.content} />
            ) : (
              <p>{message.content}</p>
            )}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <details className="tool-calls">
                <summary>How I found this</summary>
                <ul>
                  {message.toolCalls.map((call, j) => (
                    <li key={j}>{describeToolCall(call)}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
        {ask.isPending && <p className="muted">Looking through your receipts…</p>}
        {ask.isError && <p className="error-text">{ask.error.message}</p>}
      </div>

      <form onSubmit={onSubmit} className="chat-form">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="e.g. How much did I spend on coffee?"
          aria-label="Question"
          maxLength={1000}
        />
        <button type="submit" disabled={!draft.trim() || ask.isPending}>
          Ask
        </button>
      </form>
    </section>
  )
}
