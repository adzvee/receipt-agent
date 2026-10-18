import {
  Briefcase,
  Car,
  CircleHelp,
  Clapperboard,
  GraduationCap,
  HeartPulse,
  Plane,
  Repeat,
  ShoppingBag,
  ShoppingCart,
  Tag,
  Utensils,
  Zap,
  type LucideIcon,
} from 'lucide-react'

// One color and icon per category, used everywhere a category appears (chart, receipts
// list), so e.g. Dining always looks the same. Colors are CSS variables (--cat-*) in
// index.css with light and dark values, each at least 3:1 against the card background.
// A category's name is always shown too, so color is never the only cue.
const ICONS: Record<string, LucideIcon> = {
  groceries: ShoppingCart,
  dining: Utensils,
  transportation: Car,
  travel: Plane,
  shopping: ShoppingBag,
  utilities: Zap,
  health: HeartPulse,
  entertainment: Clapperboard,
  subscriptions: Repeat,
  education: GraduationCap,
  office: Briefcase,
  other: Tag,
}

/** The CSS color for a category; uncategorized receipts get a neutral gray. */
export function categoryColor(category: string | null): string {
  return category && category in ICONS ? `var(--cat-${category})` : 'var(--cat-uncategorized)'
}

export function categoryIcon(category: string | null): LucideIcon {
  return (category && ICONS[category]) || CircleHelp
}
