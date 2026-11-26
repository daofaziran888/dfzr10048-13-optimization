<template>
  <section class="lookup-panel" data-testid="hit-lookup-panel">
    <header class="panel-head">
      <div>
        <h3>命中检索与取材</h3>
        <p class="panel-desc">
          查询按转写版本返回命中；切到旧版本只显示旧版本自己的词与原位置。
          打开过的试听位置会一直保留，取材时给出实际采用的录音或不能取材的理由。
        </p>
      </div>
    </header>

    <form class="panel-form" @submit.prevent="runSearch">
      <label class="panel-field">
        <span>检索词</span>
        <input v-model="word" data-testid="lookup-word" placeholder="如 蓝鲸 / 座头鲸" />
      </label>
      <label class="panel-field">
        <span>转写版本</span>
        <select v-model="version" data-testid="lookup-version">
          <option v-for="item in versions" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn primary" type="submit" data-testid="lookup-submit">检索命中</button>
    </form>

    <p v-if="errorMessage" class="error-text" data-testid="lookup-error">{{ errorMessage }}</p>

    <div v-if="searched" data-testid="lookup-result">
      <p class="panel-message" data-testid="lookup-summary">
        「{{ lastWord }}」在 {{ lastVersion }} 命中 {{ hits.length }} 条（按原段归并，段内重报只算一次）
      </p>
      <table v-if="hits.length" class="data-table">
        <thead>
          <tr>
            <th>媒体源</th>
            <th>媒体标题</th>
            <th>命中分段数</th>
            <th>命中毫秒位置</th>
            <th>出处引文</th>
            <th>取材</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="hit in hits" :key="hit.索引编号" :data-testid="`hit-${hit.关联媒体源}`">
            <td>{{ hit.关联媒体源 }}</td>
            <td>{{ hit.媒体标题 }}</td>
            <td>{{ hit.命中分段数 }}</td>
            <td>{{ hit.命中毫秒位置 }}</td>
            <td>
              <ul class="origin-list">
                <li v-for="origin in hit.命中出处" :key="origin.分段编号">
                  {{ origin.分段编号 }} · {{ origin.起始毫秒 }}–{{ origin.结束毫秒 }}ms
                  · 重报 {{ origin.重报次数 }} 次<br />
                  <span class="quote">「{{ origin.引文 }}」</span>
                </li>
              </ul>
            </td>
            <td>
              <button
                v-for="origin in hit.命中出处"
                :key="`open-${origin.分段编号}`"
                class="link"
                type="button"
                :data-testid="`open-${hit.关联媒体源}-${origin.分段编号}`"
                @click="openAt(hit, origin)"
              >
                打开试听位置
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state" data-testid="lookup-empty">
        该版本下没有「{{ lastWord }}」的命中
      </p>
    </div>

    <section v-if="opened" class="opened-card" data-testid="opened-position">
      <h4>已打开的试听位置</h4>
      <p class="muted">
        {{ opened.media }} · {{ opened.segment }} · {{ opened.position }}ms
        · 检索词「{{ opened.word }}」· 版本 {{ opened.version }} · {{ opened.openedAt }}
      </p>
      <p class="hint">尚未保存引文。发布更正或回撤后，点下方按钮让页面给出取材结论。</p>
      <button class="btn" type="button" data-testid="resolve-citation" :disabled="resolving" @click="resolve">
        {{ resolving ? '核对中…' : '从已打开位置取材' }}
      </button>

      <div v-if="decision" class="decision" data-testid="citation-decision" :data-decision="decision.decision">
        <p class="decision-label" :class="decision.ok ? 'ok' : 'bad'">{{ decision.decisionLabel }}</p>
        <p class="decision-reason" data-testid="citation-reason">{{ decision.reason }}</p>
        <dl v-if="decision.adopted" class="adopted">
          <dt>实际采用的录音</dt>
          <dd data-testid="adopted-media">
            {{ decision.adopted.关联媒体源 }} · {{ decision.adopted.媒体标题 }}
          </dd>
          <dt>原段与区间</dt>
          <dd>{{ decision.adopted.分段编号 }} · {{ decision.adopted.起始毫秒 }}–{{ decision.adopted.结束毫秒 }}ms</dd>
          <dt>版本可追溯</dt>
          <dd>{{ decision.adopted.版本编号 }} / {{ decision.adopted.转写版本 }}（{{ decision.adopted.版本状态 }}）</dd>
          <dt>引文</dt>
          <dd class="quote" data-testid="adopted-quote">「{{ decision.adopted.引文 }}」</dd>
        </dl>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  resolveCitation,
  searchHits,
} from '@/api/term-index'
import type { CitationDecision, HitOrigin, IndexHit } from '@/api/term-index'
import type { EntryRow } from '@/data/types'
import { clearPosition, openPosition, openedPosition } from '@/domain/citation-session'

const props = defineProps<{ rows: EntryRow[]; versionField: string }>()

const versions = computed(() => {
  const found = new Set<string>(props.rows.map((row) => String(row[props.versionField] ?? '')))
  found.delete('')
  return Array.from(found).sort()
})

const word = ref('蓝鲸')
const version = ref('v2')
const hits = ref<IndexHit[]>([])
const searched = ref(false)
const lastWord = ref('')
const lastVersion = ref('')
const errorMessage = ref('')
const decision = ref<CitationDecision | null>(null)
const resolving = ref(false)

const opened = computed(() => openedPosition.current)

async function runSearch() {
  errorMessage.value = ''
  decision.value = null
  try {
    hits.value = await searchHits(word.value.trim(), version.value)
    lastWord.value = word.value.trim()
    lastVersion.value = version.value
    searched.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '命中检索失败'
  }
}

function openAt(hit: IndexHit, origin: HitOrigin) {
  openPosition({
    word: hit.索引词,
    version: hit.索引版本,
    media: hit.关联媒体源,
    segment: origin.分段编号,
    position: origin.起始毫秒,
    context: hit.媒体标题,
  })
  decision.value = null
}

async function resolve() {
  if (!opened.value) return
  resolving.value = true
  errorMessage.value = ''
  try {
    decision.value = await resolveCitation(opened.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '取材结论读取失败'
  } finally {
    resolving.value = false
  }
}

function closeOpened() {
  clearPosition()
  decision.value = null
}

onMounted(() => {
  if (versions.value.length && !versions.value.includes(version.value)) {
    version.value = versions.value[versions.value.length - 1]
    word.value = '蓝鲸'
  }
})
</script>
