<template>
  <section class="correction-panel" data-testid="term-correction-panel">
    <header class="panel-head">
      <div>
        <h3>同版词条批量更正</h3>
        <p class="panel-desc">
          只勾选同一转写版本的词条；提交后媒体索引按版本与原段立即更新命中，撤回则整批恢复。
        </p>
      </div>
      <button class="btn ghost" type="button" data-testid="refresh-batches" @click="reloadBatches">
        刷新批次
      </button>
    </header>

    <p v-if="selectionError" class="error-text" data-testid="selection-error">{{ selectionError }}</p>

    <form class="panel-form" @submit.prevent="submitBatch">
      <label class="panel-field">
        <span>已选 {{ selectedIds.length }} 条 · 版本 {{ selectedVersion || '未选' }}{{ versionTag }}</span>
        <input
          v-model="correctedText"
          data-testid="corrected-text"
          placeholder="纠正为（同批统一成同一个词）"
        />
      </label>
      <label class="panel-field">
        <span>备注</span>
        <input v-model="remark" data-testid="correction-remark" placeholder="可留空" />
      </label>
      <button
        class="btn primary"
        type="submit"
        data-testid="submit-batch"
        :disabled="busy || !!selectionError || !selectedIds.length"
      >
        {{ busy ? '提交中…' : '提交批量更正' }}
      </button>
    </form>

    <p v-if="message" class="panel-message" data-testid="correction-message">{{ message }}</p>
    <p v-if="errorMessage" class="error-text" data-testid="correction-error">{{ errorMessage }}</p>

    <table v-if="batches.length" class="data-table batch-table">
      <thead>
        <tr>
          <th>更正批次</th>
          <th>状态</th>
          <th>转写版本</th>
          <th>词条数</th>
          <th>纠正为</th>
          <th>提交时间</th>
          <th>撤回</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="batch in batches"
          :key="batch.更正批次"
          :data-testid="`batch-${batch.更正批次}`"
          :data-batch-status="batch.状态"
        >
          <td>{{ batch.更正批次 }}</td>
          <td>{{ batch.状态 }}</td>
          <td>{{ batch.转写版本 }}</td>
          <td>{{ batch.更正词数量 }}</td>
          <td>{{ batch.纠正文本 }}</td>
          <td>{{ batch.提交时间 }}</td>
          <td>
            <button
              v-if="batch.状态 === '已提交'"
              class="link"
              type="button"
              :data-testid="`withdraw-${batch.更正批次}`"
              :disabled="busy"
              @click="withdraw(batch)"
            >
              撤回整批
            </button>
            <span v-else class="muted">{{ batch.撤回时间 }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  listBatches,
  submitCorrection,
  withdrawCorrection,
} from '@/api/term-index'
import type { CorrectionBatch } from '@/api/term-index'
import type { EntryRow } from '@/data/types'

const props = defineProps<{
  rows: EntryRow[]
  selectedIds: number[]
  versionField: string
  versionIdField?: string
}>()
const emit = defineEmits<{ (event: 'changed'): void }>()

const batches = ref<CorrectionBatch[]>([])
const correctedText = ref('')
const remark = ref('')
const busy = ref(false)
const message = ref('')
const errorMessage = ref('')

const selectedRows = computed(() =>
  props.rows.filter((row) => props.selectedIds.includes(Number(row.id))),
)
const selectedVersions = computed(() =>
  Array.from(new Set(selectedRows.value.map((row) => String(row[props.versionField] ?? '')))),
)
const selectedVersionIds = computed(() => {
  const field = props.versionIdField
  if (!field) return [] as string[]
  return Array.from(new Set(selectedRows.value.map((row) => String(row[field] ?? ''))))
})
const selectedVersion = computed(() => selectedVersions.value[0] ?? '')
const versionTag = computed(() =>
  selectedVersionIds.value.length === 1 && selectedVersionIds.value[0]
    ? `（${selectedVersionIds.value[0]}）`
    : '',
)
const selectionError = computed(() => {
  if (selectedRows.value.length === 0) return ''
  if (selectedVersions.value.length > 1) return '已勾选的词条跨了多个转写版本，请只保留同一版本'
  if (props.versionIdField && selectedVersionIds.value.length > 1) {
    return '版本号相同但不是同一条版本记录（分属不同任务），请只保留同一版本记录的词条'
  }
  if (selectedRows.value.some((row) => !row[props.versionField])) {
    return '已勾选的词条缺少转写版本，不能批量更正'
  }
  return ''
})

async function reloadBatches() {
  try {
    batches.value = await listBatches()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '更正批次读取失败'
  }
}

async function submitBatch() {
  if (selectionError.value || !props.selectedIds.length) return
  busy.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const result = await submitCorrection(props.selectedIds, correctedText.value, remark.value)
    if (!result.ok) throw new Error(result.message)
    message.value = result.message
    correctedText.value = ''
    await reloadBatches()
    emit('changed')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量更正提交失败'
  } finally {
    busy.value = false
  }
}

async function withdraw(batch: CorrectionBatch) {
  busy.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const result = await withdrawCorrection(batch.更正批次)
    if (!result.ok) throw new Error(result.message)
    message.value = result.message
    await reloadBatches()
    emit('changed')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '撤回更正失败'
  } finally {
    busy.value = false
  }
}

watch(() => props.selectedIds, () => {
  message.value = ''
  errorMessage.value = ''
})

onMounted(reloadBatches)
</script>
