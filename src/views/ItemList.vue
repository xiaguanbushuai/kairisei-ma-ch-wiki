<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { formatNumber, getItems } from '../api.js'

const items = ref([])
const loading = ref(true)

const filters = reactive({
  keyword: '',
  type: '',
})

const TYPE_LABELS = {
  BP_HEAL: '体力恢复',
  GACHA: '扭蛋',
  GACHA_TICKET: '扭蛋券',
  EVENT_POINT: '活动点数',
  LOVE_UP: '忠诚度提升',
  MATERIAL: '素材',
  CONSUME: '消耗品',
  STONE: '召唤石',
}

onMounted(async () => {
  const map = await getItems()
  items.value = Object.values(map).sort((a, b) => a.id - b.id)
  loading.value = false
})

const types = computed(() => {
  const counts = new Map()
  for (const item of items.value) counts.set(item.type, (counts.get(item.type) || 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
})

const filtered = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase()
  return items.value.filter((item) => {
    if (filters.type && item.type !== filters.type) return false
    if (keyword) {
      const haystack = `${item.name} ${item.desc} ${item.id}`.toLowerCase()
      if (!haystack.includes(keyword)) return false
    }
    return true
  })
})
</script>

<template>
  <div v-if="loading" class="loading">正在加载道具数据 …</div>

  <div v-else>
    <section class="panel">
      <div class="panel-title">
        <h1 style="margin: 0">道具资料</h1>
        <span class="small muted">共 <strong>{{ filtered.length.toLocaleString() }}</strong> / {{ items.length.toLocaleString() }} 项</span>
      </div>

      <div class="row" style="align-items: flex-end">
        <div class="field" style="flex: 1 1 260px">
          <label>名称 / ID / 说明</label>
          <input v-model="filters.keyword" type="text" placeholder="如：体力 / 大硬币 / 4010" />
        </div>
        <div class="field">
          <label>类型</label>
          <select v-model="filters.type">
            <option value="">全部</option>
            <option v-for="[name, count] in types" :key="name" :value="name">
              {{ TYPE_LABELS[name] || name }}（{{ count }}）
            </option>
          </select>
        </div>
        <button class="btn" @click="Object.assign(filters, { keyword: '', type: '' })">重置</button>
      </div>
    </section>

    <section class="panel" style="margin-top: 16px">
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th class="num">ID</th>
              <th>名称</th>
              <th>类型</th>
              <th class="num">持有上限</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filtered" :key="item.id">
              <td class="num">{{ item.id }}</td>
              <td><strong>{{ item.name || '—' }}</strong></td>
              <td class="small muted">{{ TYPE_LABELS[item.type] || item.type }}</td>
              <td class="num">{{ formatNumber(item.maxOwned) }}</td>
              <td class="small muted">{{ item.desc }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!filtered.length" class="muted small">没有符合条件的道具。</div>
    </section>
  </div>
</template>
