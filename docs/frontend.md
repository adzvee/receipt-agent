# The frontend

React + TypeScript (Vite), with React Router for pages, TanStack Query for fetching and
caching API data, and Recharts for charts.

- **Dashboard:** monthly spending for the last year, a period filter (this month, last
  month, last 90 days, ...) that scopes the total and the category breakdown below it,
  receipts needing review, and the chat box. The dashboard's totals come from the same
  `spending_summary` function the agent uses, so the two always agree. A new account sees
  a single welcome state instead: an Upload receipt button and its forwarding address.
- **Receipts:** drag-and-drop upload (several files at once, or "Take photo" on phones),
  the user's email forwarding address, and the list with photo thumbnails, filterable to
  receipts that need review.
- **Receipt detail:** the original file next to the extracted fields and line items,
  flags with a Dismiss button, and a category picker.

Each category has one color and icon, used in both the category chart and the receipts
list; every color is checked for at least 3:1 contrast in light and dark mode, and the
category name is always shown too, so color is never the only cue. Charts label values
directly or in a subtitle (never clipped), show a tooltip on hover, and have a "Show as
table" view so no number is only available by hovering. The chat renders
the model's bold text and bullet lists as React elements, never as raw HTML.
