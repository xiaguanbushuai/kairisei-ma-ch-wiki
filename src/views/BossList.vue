<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ATTR_COLOR, RARITY_COLOR, cardThumb, getBossIndex, getMeta } from '../api.js'

const route = useRoute()
const router = useRouter()

const bosses = ref([])
const meta = ref(null)
const loading = ref(true)

const filters = reactive({
  keyword: '',
  tab: route.query.past === '1' ? 'past' : 'current',
  difficulty: '',
  group: route.query.group || '',
})

const DIFFICULTY_ORDER = ['初级', '中级', '上级', '特级', '超级', '超弩级', '地狱级', '断绝级', '超弩级(ｺﾝﾃｨﾆｭｰ不可)']

onMounted(async () => {
  const [metaData, list] = await Promise.all([getMeta(), getBossIndex()])
  meta.value = metaData
  bosses.value = list
  loading.value = false
})

const difficulties = computed(() => {
  const present = new Set(bosses.value.filter((b) => (filters.tab === 'past') === b.past).map((b) => b.difficulty))
  const known = DIFFICULTY_ORDER.filter((name) => present.has(name))
  const extra = [...present].filter((name) => !DIFFICULTY_ORDER.includes(name) && name)
  return [...known, ...extra.sort()]
})

const groups = computed(() => {
  const counts = new Map()
  for (const boss of bosses.value) {
    if ((filters.tab === 'past') !== boss.past) continue
    const name = boss.groupName || '未分组'
    counts.set(name, (counts.get(name) || 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh'))
})

const filtered = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase()
  return bosses.value.filter((boss) => {
    if ((filters.tab === 'past') !== boss.past) return false
    if (filters.difficulty && boss.difficulty !== filters.difficulty) return false
    if (filters.group && boss.groupName !== filters.group) return false
    if (keyword) {
      const haystack = `${boss.name} ${boss.groupName} ${boss.groupSub} ${boss.difficulty}`.toLowerCase()
      if (!haystack.includes(keyword)) return false
    }
    return true
  })
})

watch(filters, () => {
  router.replace({
    query: {
      ...(filters.tab === 'past' ? { past: '1' } : {}),
      ...(filters.group ? { group: filters.group } : {}),
    },
  })
}, { deep: true })

const ATTR_LABELS = { 0: '无', 1: '火', 2: '冰', 3: '风', 4: '光', 5: '暗' }
const ATTR_BY_INDEX = { 1: 'FIRE', 2: 'ICE', 3: 'WIND', 4: 'LIGHT', 5: 'DARK' }
</script>

<template>
  <div v-if="loading" class="loading">正在加载 Boss 数据 …</div>

  <div v-else>
    <section class="panel">
      <div class="panel-title">
        <h1 style="margin: 0">Boss 图鉴</h1>
        <span class="small muted">共 <strong>{{ filtered.length.toLocaleString() }}</strong> 条记录</span>
      </div>

      <div class="row">
        <div class="chip-group">
          <button class="chip" :class="{ on: filters.tab === 'current' }" @click="filters.tab = 'current'">
            活动 / 素材
          </button>
          <button class="chip" :class="{ on: filters.tab === 'past' }" @click="filters.tab = 'past'">
            往期 Boss
          </button>
        </div>
        <div class="field" style="flex: 1 1 220px">
          <input v-model="filters.keyword" type="text" placeholder="搜索 Boss 名 / 分组 / 难度" />
        </div>
        <div class="field">
          <label>难度</label>
          <select v-model="filters.difficulty">
            <option value="">全部</option>
            <option v-for="name in difficulties" :key="name" :value="name">{{ name }}</option>
          </select>
        </div>
        <div class="field">
          <label>分组</label>
          <select v-model="filters.group">
            <option value="">全部</option>
            <option v-for="[name, count] in groups" :key="name" :value="name">{{ name }}（{{ count }}）</option>
          </select>
        </div>
        <button class="btn" @click="Object.assign(filters, { keyword: '', difficulty: '', group: '' })">重置</button>
      </div>
    </section>

    <section class="panel" style="margin-top: 16px">
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>Boss</th>
              <th>分组</th>
              <th>难度</th>
              <th class="num">BP</th>
              <th class="num">波次</th>
              <th>模式</th>
              <th>奖励卡</th>
              <th>行动轴</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="boss in filtered.slice(0, 400)" :key="boss.id">
              <td>
                <router-link :to="`/boss/${boss.id}`"><strong>{{ boss.name || `#${boss.id}` }}</strong></router-link>
                <div class="tiny faint">ID {{ boss.id }}</div>
              </td>
              <td class="small">{{ boss.groupName }}</td>
              <td>
                <span class="badge badge-plain">{{ boss.difficulty || '—' }}</span>
              </td>
              <td class="num">{{ boss.bpUse }}</td>
              <td class="num">{{ boss.waveCount }}</td>
              <td class="tiny">
                <span v-if="boss.onlyMyDeck === 1" class="badge badge-plain">仅自身卡组</span>
                <span v-else class="badge badge-plain">常规</span>
                <span v-if="boss.continue === 1" class="badge badge-plain">可续关</span>
              </td>
              <td>
                <div class="row" style="gap: 4px; flex-wrap: nowrap">
                  <router-link
                    v-for="reward in boss.rewardCards.slice(0, 4)"
                    :key="reward.id"
                    :to="`/card/${reward.id}`"
                    :title="reward.name"
                  >
                    <img
                      v-if="reward.pictId"
                      :src="cardThumb(reward.pictId)"
                      alt=""
                      style="width: 30px; border-radius: 4px; display: block"
                    />
                  </router-link>
                  <span v-if="!boss.rewardCards.length" class="faint tiny">—</span>
                </div>
              </td>
              <td class="tiny">
                <span v-if="boss.hasOrder" class="badge badge-plain">有</span>
                <span v-else class="faint">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="filtered.length > 400" class="tiny faint" style="margin-top: 10px">
        仅显示前 400 条，请用筛选条件缩小范围。
      </div>
      <div v-if="!filtered.length" class="muted small">没有符合条件的 Boss。</div>
    </section>
  </div>
</template>
