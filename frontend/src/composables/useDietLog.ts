import { computed, ref } from 'vue'
import type { DishInfo } from '@/api/types'

const STORAGE_KEY = 'fsai_diet_log_v1'

export interface DietLogEntry {
  id: string
  slug: string
  dish_name: string
  category: string
  weight_g: number
  calories: number
  protein_g: number
  fat_g: number
  carbs_g: number
  created_at: string
  day: string
}

function todayKey(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function readEntries(): DietLogEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as DietLogEntry[]
    if (!Array.isArray(parsed)) return []
    return parsed.filter((entry) => entry?.day === todayKey())
  } catch {
    return []
  }
}

const entries = ref<DietLogEntry[]>(readEntries())

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.value))
  } catch {
    /* 隐私模式下 localStorage 不可用时，保留内存态 */
  }
}

function makeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function useDietLog() {
  const totals = computed(() =>
    entries.value.reduce(
      (acc, entry) => {
        acc.calories += entry.calories
        acc.protein_g += entry.protein_g
        acc.fat_g += entry.fat_g
        acc.carbs_g += entry.carbs_g
        return acc
      },
      { calories: 0, protein_g: 0, fat_g: 0, carbs_g: 0 },
    ),
  )

  function addDish(dish: DishInfo, weightG?: number): DietLogEntry {
    const weight = Math.max(1, Number(weightG || dish.typical_portion_g || 100))
    const factor = weight / 100
    const entry: DietLogEntry = {
      id: makeId(),
      slug: dish.slug,
      dish_name: dish.dish_name,
      category: dish.category,
      weight_g: Math.round(weight),
      calories: Math.round(dish.calories_per_100g * factor * 10) / 10,
      protein_g: Math.round(dish.protein_per_100g * factor * 10) / 10,
      fat_g: Math.round(dish.fat_per_100g * factor * 10) / 10,
      carbs_g: Math.round(dish.carbs_per_100g * factor * 10) / 10,
      created_at: new Date().toISOString(),
      day: todayKey(),
    }
    entries.value = [...entries.value, entry]
    persist()
    return entry
  }

  function addMeal(input: {
    name: string
    calories: number
    protein_g: number
    fat_g: number
    carbs_g: number
    weight_g?: number
    category?: string
  }): DietLogEntry {
    const entry: DietLogEntry = {
      id: makeId(),
      slug: `record-${Date.now()}`,
      dish_name: input.name,
      category: input.category || '家常菜',
      weight_g: Math.max(0, Math.round(Number(input.weight_g || 0))),
      calories: Math.round(Number(input.calories) * 10) / 10,
      protein_g: Math.round(Number(input.protein_g) * 10) / 10,
      fat_g: Math.round(Number(input.fat_g) * 10) / 10,
      carbs_g: Math.round(Number(input.carbs_g) * 10) / 10,
      created_at: new Date().toISOString(),
      day: todayKey(),
    }
    entries.value = [...entries.value, entry]
    persist()
    return entry
  }

  function removeEntry(id: string) {
    entries.value = entries.value.filter((entry) => entry.id !== id)
    persist()
  }

  function clearToday() {
    entries.value = []
    persist()
  }

  return { entries, totals, addDish, addMeal, removeEntry, clearToday }
}