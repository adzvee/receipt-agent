import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { SimpleMarkdown } from './SimpleMarkdown'

it('renders bold text and bullet lists', () => {
  const { container } = render(
    <SimpleMarkdown text={'You spent **$125.50**.\n\n* Groceries: $105.50\n* Dining: $20.00'} />,
  )

  expect(screen.getByText('$125.50').tagName).toBe('STRONG')
  expect([...container.querySelectorAll('li')].map((li) => li.textContent)).toEqual([
    'Groceries: $105.50',
    'Dining: $20.00',
  ])
})

it('never turns model output into HTML', () => {
  const { container } = render(<SimpleMarkdown text={'<img src=x onerror="alert(1)"> hi'} />)

  expect(container.querySelector('img')).toBeNull()
  expect(container.textContent).toBe('<img src=x onerror="alert(1)"> hi')
})
