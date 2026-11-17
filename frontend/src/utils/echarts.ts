import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  DatasetComponent,
  MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  DatasetComponent,
  MarkLineComponent,
  CanvasRenderer,
])

export { echarts }
export type { EChartsOption }

/** 统一图表主题色，保证各页面视觉一致 */
export const CHART_COLORS = ['#0f7b6c', '#f0a232', '#2f6fb0', '#8f6ed5', '#cf4237', '#5aa469', '#9aa7a2']

export const baseTextStyle = {
  fontFamily: "'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif",
  color: '#47554f',
}
