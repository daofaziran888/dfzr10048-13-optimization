import { request } from './client'

export type CorrectionItem = {
  术语条目id: number
  术语编号: string
  关联媒体源: string
  原段编号: string
  原术语文本: string
  新术语文本: string
  更正前原段: string
}

export type CorrectionBatch = {
  id: number
  更正批次: string
  状态: string
  版本编号: string
  转写版本: string
  更正词数量: string
  纠正文本: string
  操作者: string
  备注: string
  提交时间: string
  撤回时间: string
  明细?: CorrectionItem[]
}

export type HitOrigin = {
  分段编号: string
  起始毫秒: string
  结束毫秒: string
  引文: string
  重报次数: string
}

export type IndexHit = {
  索引编号: string
  关联媒体源: string
  媒体标题: string
  索引词: string
  命中分段数: string
  命中毫秒位置: string
  索引版本: string
  状态: string
  命中出处: HitOrigin[]
}

export type AdoptedRecording = {
  关联媒体源: string
  媒体标题: string
  分段编号: string
  起始毫秒: string
  结束毫秒: string
  版本编号: string
  转写版本: string
  版本状态: string
  引文: string
  可核验: boolean
}

export type CitationDecision = {
  ok: boolean
  decision: 'used_recording' | 'unavailable'
  decisionLabel: string
  word: string
  requestedVersion: string
  matched: boolean
  currentWord: string
  adopted: AdoptedRecording | null
  citation: {
    关联媒体源: string
    分段编号: string
    起始毫秒: string
    结束毫秒: string
    引文: string
    索引版本: string
    版本编号: string
  } | null
  reason: string
}

export type OpenedPosition = {
  word: string
  version: string
  media: string
  segment: string
  position: string
}

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  const payload = (await response.json()) as T & { message?: string; detail?: string }
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || fallback)
  }
  return payload
}

export async function listBatches(): Promise<CorrectionBatch[]> {
  const response = await request('/api/term-index/batches')
  const payload = await readJson<{ items: CorrectionBatch[] }>(response, '更正批次读取失败')
  return payload.items
}

export async function submitCorrection(
  termIds: number[],
  correctedText: string,
  remark = '',
): Promise<{ ok: boolean; message: string; entry: CorrectionBatch | null }> {
  const response = await request('/api/term-index/batches', {
    method: 'POST',
    body: JSON.stringify({ termIds, correctedText, remark }),
  })
  return await readJson(response, '批量更正提交失败')
}

export async function withdrawCorrection(
  batchId: string,
  remark = '',
): Promise<{ ok: boolean; message: string; entry: CorrectionBatch | null }> {
  const response = await request(`/api/term-index/batches/${encodeURIComponent(batchId)}/withdraw`, {
    method: 'POST',
    body: JSON.stringify({ remark }),
  })
  return await readJson(response, '撤回更正失败')
}

export async function searchHits(word: string, version: string): Promise<IndexHit[]> {
  const query = new URLSearchParams({ word, version }).toString()
  const response = await request(`/api/term-index/hits?${query}`)
  const payload = await readJson<{ items: IndexHit[] }>(response, '命中检索失败')
  return payload.items
}

export async function resolveCitation(
  opened: OpenedPosition,
): Promise<CitationDecision> {
  const query = new URLSearchParams({
    word: opened.word,
    version: opened.version,
    media: opened.media,
    segment: opened.segment,
    position: opened.position,
  }).toString()
  const response = await request(`/api/term-index/citation?${query}`)
  return await readJson(response, '取材结论读取失败')
}
