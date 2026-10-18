import type { LucideProps } from 'lucide-react'
import { createElement } from 'react'
import { categoryColor, categoryIcon } from '../categories'
import { categoryLabel } from '../format'

/** A category's icon in its color. Extra props (size, x, y) go to the SVG. */
export function CategoryIcon({ category, ...props }: { category: string | null } & LucideProps) {
  return createElement(categoryIcon(category), {
    'aria-hidden': true,
    color: categoryColor(category),
    ...props,
  })
}

/** Icon and name, e.g. in the receipts list. */
export function CategoryTag({ category }: { category: string | null }) {
  return (
    <span className="category-tag">
      <CategoryIcon category={category} size={16} />
      {categoryLabel(category)}
    </span>
  )
}
