/** 检索人员的取材会话：已打开的试听位置要跨模块页面切换保留。 */
import { reactive } from 'vue'

import type { OpenedPosition as CitationTarget } from '@/api/term-index'

export type OpenedPosition = CitationTarget & {
  /** 打开位置时正在检索的媒体源清单，用于展示。 */
  context: string
  openedAt: string
}

export const openedPosition = reactive<{ current: OpenedPosition | null }>({
  current: null,
})

export function openPosition(
  payload: Omit<OpenedPosition, 'openedAt'>,
): OpenedPosition {
  const next: OpenedPosition = {
    ...payload,
    openedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
  }
  openedPosition.current = next
  return next
}

export function clearPosition() {
  openedPosition.current = null
}
