<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

interface WeatherState {
  city: string
  adcode: string
  emoji: string
  temperature: number
  description: string
  condition: string
  severe: boolean
}

type CityOption = {
  name: string
  adcode: string
}

const CITIES: CityOption[] = [
  { name: '北京', adcode: '110000' },
  { name: '上海', adcode: '310000' },
  { name: '广州', adcode: '440100' },
  { name: '成都', adcode: '510100' },
]

const DEFAULT_WEATHER: WeatherState = {
  city: '北京',
  adcode: '110000',
  emoji: '🌧️',
  temperature: 12,
  description: '小雨',
  condition: 'rain',
  severe: true,
}

const FALLBACKS: Record<string, WeatherState> = {
  '110000': DEFAULT_WEATHER,
  '310000': {
    city: '上海',
    adcode: '310000',
    emoji: '☁️',
    temperature: 18,
    description: '多云',
    condition: 'cloudy',
    severe: false,
  },
  '440100': {
    city: '广州',
    adcode: '440100',
    emoji: '☀️',
    temperature: 26,
    description: '晴',
    condition: 'sunny',
    severe: false,
  },
  '510100': {
    city: '成都',
    adcode: '510100',
    emoji: '🌥️',
    temperature: 16,
    description: '阴',
    condition: 'cloudy',
    severe: false,
  },
}

const emit = defineEmits<{
  change: [weather: WeatherState]
  loading: [value: boolean]
}>()

const AMAP_KEY = String(import.meta.env.VITE_AMAP_KEY || '').trim()
const rootRef = ref<HTMLElement | null>(null)
const open = ref(false)
const locating = ref(false)
const selectedAdcode = ref(DEFAULT_WEATHER.adcode)
const current = ref<WeatherState>({ ...DEFAULT_WEATHER })
let requestSeq = 0

function publish(next: WeatherState) {
  current.value = next
  selectedAdcode.value = next.adcode
  emit('change', { ...next })
}

function applyFallback(adcode = DEFAULT_WEATHER.adcode) {
  publish({ ...(FALLBACKS[adcode] || DEFAULT_WEATHER) })
}

function weatherMeta(description: string) {
  const text = description || ''
  if (/雨|雷/.test(text)) {
    return { emoji: '🌧️', condition: 'rain', severe: true }
  }
  if (/雪|冰|冻/.test(text)) {
    return { emoji: '❄️', condition: 'snow', severe: true }
  }
  if (/雾|霾|沙|尘/.test(text)) {
    return { emoji: '🌫️', condition: 'haze', severe: true }
  }
  if (/阴/.test(text)) {
    return { emoji: '☁️', condition: 'cloudy', severe: false }
  }
  if (/云/.test(text)) {
    return { emoji: '🌤️', condition: 'cloudy', severe: false }
  }
  if (/风/.test(text)) {
    return { emoji: '💨', condition: 'windy', severe: false }
  }
  return { emoji: '☀️', condition: 'sunny', severe: false }
}

async function fetchJson(url: string, timeout = 8000) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } finally {
    window.clearTimeout(timer)
  }
}

async function loadWeather(adcode: string, fallbackName: string) {
  const seq = ++requestSeq
  const city = CITIES.find((item) => item.adcode === adcode)?.name || fallbackName
  if (!AMAP_KEY) {
    applyFallback(adcode)
    return
  }

  emit('loading', true)
  try {
    const url = `https://restapi.amap.com/v3/weather/weatherInfo?key=${encodeURIComponent(AMAP_KEY)}&city=${encodeURIComponent(adcode)}&extensions=base`
    const data = await fetchJson(url)
    if (seq !== requestSeq) return
    const live = data?.lives?.[0]
    if (!live) throw new Error('empty weather')
    const description = String(live.weather || fallbackName)
    const meta = weatherMeta(description)
    publish({
      city,
      adcode,
      emoji: meta.emoji,
      temperature: Number(live.temperature || DEFAULT_WEATHER.temperature),
      description,
      condition: meta.condition,
      severe: meta.severe,
    })
  } catch {
    if (seq === requestSeq) applyFallback(adcode)
  } finally {
    if (seq === requestSeq) emit('loading', false)
  }
}

function selectCity(city: CityOption) {
  open.value = false
  locating.value = false
  selectedAdcode.value = city.adcode
  loadWeather(city.adcode, city.name)
}

async function locate() {
  if (!AMAP_KEY || !navigator.geolocation) return
  const seq = ++requestSeq
  locating.value = true
  emit('loading', true)
  navigator.geolocation.getCurrentPosition(
    async (position) => {
      if (seq !== requestSeq) return
      try {
        const { latitude, longitude } = position.coords
        const url = `https://restapi.amap.com/v3/geocode/regeo?key=${encodeURIComponent(AMAP_KEY)}&location=${longitude},${latitude}&extensions=base`
        const data = await fetchJson(url)
        if (seq !== requestSeq) return
        const component = data?.regeocode?.addressComponent || {}
        const adcode = String(component.adcode || '').trim()
        const rawCity = Array.isArray(component.city) ? component.city[0] : component.city
        const city = String(rawCity || component.province || component.district || '').trim()
        if (!adcode) throw new Error('empty adcode')
        selectedAdcode.value = adcode
        await loadWeather(adcode, city)
      } catch {
        if (seq === requestSeq) applyFallback()
      } finally {
        locating.value = false
        if (seq === requestSeq) emit('loading', false)
      }
    },
    () => {
      if (seq === requestSeq) {
        locating.value = false
        emit('loading', false)
      }
    },
    { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 },
  )
}

function onDocumentClick(event: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  locate()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div ref="rootRef" class="weather-widget">
    <button
      type="button"
      class="weather-trigger"
      :class="{ 'is-open': open }"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click.stop="open = !open"
    >
      <span class="weather-emoji" aria-hidden="true">{{ current.emoji }}</span>
      <span class="weather-line">
        <strong>{{ current.city }}</strong>
        <span>{{ current.temperature }}℃ {{ current.description }}</span>
      </span>
      <span v-if="locating" class="weather-locating">定位中</span>
      <svg class="weather-chevron" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m7 10 5 5 5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <Transition name="weather-menu">
      <div v-if="open" class="weather-menu" role="listbox">
        <div class="weather-menu-head">
          <span>选择城市</span>
          <span v-if="locating" class="weather-menu-status">定位中…</span>
        </div>

        <button
          v-for="city in CITIES"
          :key="city.adcode"
          type="button"
          class="weather-city"
          :class="{ active: selectedAdcode === city.adcode }"
          role="option"
          :aria-selected="selectedAdcode === city.adcode"
          @click.stop="selectCity(city)"
        >
          <span>{{ city.name }}</span>
          <span class="weather-city-code">{{ city.adcode.slice(0, 2) }}</span>
        </button>

        <button type="button" class="weather-locate" @click.stop="locate">
          <span aria-hidden="true">◎</span>
          定位当前城市
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.weather-widget {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.weather-trigger {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid #dce8e2;
  border-radius: 999px;
  background: #ffffff;
  color: #4b6b5d;
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(31, 61, 50, 0.04);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background-color 0.18s ease;
}

.weather-trigger:hover,
.weather-trigger.is-open {
  border-color: #b9d4c7;
  background: #f8fcfa;
  box-shadow: 0 5px 14px rgba(31, 61, 50, 0.07);
}

.weather-emoji {
  font-size: 16px;
  line-height: 1;
}

.weather-line {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  white-space: nowrap;
}

.weather-line strong {
  color: #284d3f;
  font-size: 12px;
  font-weight: 700;
}

.weather-line span {
  color: #6e8a7d;
  font-size: 11.5px;
}

.weather-locating {
  color: #91b7a7;
  font-size: 9.5px;
  white-space: nowrap;
}

.weather-chevron {
  width: 13px;
  height: 13px;
  color: #8aa196;
  transition: transform 0.18s ease;
}

.weather-trigger.is-open .weather-chevron {
  transform: rotate(180deg);
}

.weather-menu {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 80;
  width: 194px;
  padding: 6px;
  border: 1px solid #e3eee8;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 14px 30px rgba(31, 61, 50, 0.14);
}

.weather-menu-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px 7px;
  color: #9aaba2;
  font-size: 10px;
}

.weather-menu-status {
  color: #74a18c;
  font-size: 9.5px;
}

.weather-city {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 9px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #4b6359;
  font-family: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.weather-city:hover {
  background: #f4faf7;
}

.weather-city.active {
  background: #eaf5ef;
  color: #1f7a5f;
  font-weight: 600;
}

.weather-city-code {
  color: #a8b7af;
  font-size: 9.5px;
  font-weight: 400;
}

.weather-locate {
  display: flex;
  align-items: center;
  gap: 5px;
  width: 100%;
  margin-top: 4px;
  padding: 8px 9px;
  border: 0;
  border-top: 1px dashed #e8f0eb;
  border-radius: 0 0 9px 9px;
  background: transparent;
  color: #68917f;
  font-family: inherit;
  font-size: 11px;
  cursor: pointer;
}

.weather-locate:hover {
  background: #f4faf7;
  color: #1f7a5f;
}

.weather-menu-enter-active,
.weather-menu-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.weather-menu-enter-from,
.weather-menu-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
