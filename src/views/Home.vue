<script setup>
import { onMounted, ref } from 'vue'
import {
  RARITY_LABEL_ORDER,
  attrColor,
  attrLabel,
  getBossIndex,
  getCards,
  getMeta,
  groupFamilies,
  pickRepresentative,
  rarityLabelColor,
  rarityLabelOf,
} from '../api.js'

const meta = ref(null)
const rarityStats = ref([])
const attrStats = ref([])
const topBossGroups = ref([])
const familyCount = ref(0)
const playableFamilyCount = ref(0)

onMounted(async () => {
  const [metaData, cards, bosses] = await Promise.all([getMeta(), getCards(), getBossIndex()])
  meta.value = metaData

  // 同一张卡按进化阶段/稀有度占多条记录，统计时先按「同カードID」收拢成一张
  // （代表卡取族内稀有度最高的那张），避免 UR 与 MR 被重复计数。
  const { cardFamilies, cardFamiliesPlayable } = metaData.counts
  familyCount.value = cardFamilies
  playableFamilyCount.value = cardFamiliesPlayable

  const labelOrder = metaData.enums.rarityLabelOrder || RARITY_LABEL_ORDER
  const rarityCount = new Map()
  const attrCount = new Map()
  for (const members of groupFamilies(cards).values()) {
    const active = members.filter((card) => !card.stack)
    if (!active.length) continue
    const representative = pickRepresentative(active, labelOrder)
    // 每张卡只按它的最高形态归入一档（MR / MR+ / MR++ / MMR 各自独立）
    const label = rarityLabelOf(representative, metaData.enums)
    rarityCount.set(label, (rarityCount.get(label) || 0) + 1)
    if (representative.attr) attrCount.set(representative.attr, (attrCount.get(representative.attr) || 0) + 1)
  }
  rarityStats.value = [...rarityCount.entries()]
    .sort((a, b) => (labelOrder[b[0]] ?? -1) - (labelOrder[a[0]] ?? -1))
    .map(([label, count]) => ({
      key: label,
      count,
      label,
      color: rarityLabelColor(label),
    }))
  attrStats.value = [...attrCount.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({
      key,
      count,
      label: attrLabel(key, metaData.enums.attr) || key,
      color: attrColor(key),
    }))

  const groupCount = new Map()
  for (const boss of bosses) {
    if (boss.past) continue
    const name = boss.groupName || '未分组'
    groupCount.set(name, (groupCount.get(name) || 0) + 1)
  }
  topBossGroups.value = [...groupCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12)

  window.__kairiCards = cards.length
})

const entries = [
  {
    to: '/cards',
    icon: '🃏',
    title: '卡牌图鉴',
    desc: '按职业、属性、稀有度、COST 与技能效果筛选，查看数值、升级曲线与进化材料。',
  },
  {
    to: '/skills',
    icon: '✨',
    title: '技能索引',
    desc: '反向查询：从技能效果出发，找出拥有该技能的全部卡牌。',
  },
  {
    to: '/bosses',
    icon: '🐲',
    title: 'Boss 图鉴',
    desc: '副本各路波次的部位数值、属性耐性、行动轴与掉落奖励。',
  },
  {
    to: '/items',
    icon: '🎁',
    title: '道具资料',
    desc: '道具与材料的用途、来源与说明。',
  },
]
</script>

<template>
  <div>
    <section class="panel">
      <h1>乖离性百万亚瑟王 · 国服资料站</h1>
      <p class="muted" style="margin-top: -6px">
        停服纪念向的数据查询工具。数据直接提取自国服客户端主表，包含
        <template v-if="meta">
          <strong>{{ playableFamilyCount.toLocaleString() }}</strong> 张卡牌
          <span class="faint tiny">（客户端原始记录 {{ meta.counts.cards.toLocaleString() }} 条，同一张卡的各进化阶段已合并）</span>、
        </template>
        <strong v-if="meta">{{ meta.counts.skills.toLocaleString() }}</strong> 条技能、
        <strong v-if="meta">{{ meta.counts.bosses.toLocaleString() }}</strong> 个 Boss 记录与
        <strong v-if="meta">{{ meta.counts.items.toLocaleString() }}</strong> 项道具。
      </p>

      <div class="grid-2" style="margin-top: 16px">
        <router-link v-for="entry in entries" :key="entry.to" :to="entry.to" class="panel" style="text-decoration: none; display: block">
          <div class="row" style="align-items: flex-start; flex-wrap: nowrap">
            <span style="font-size: 22px">{{ entry.icon }}</span>
            <div>
              <h3 style="margin-bottom: 4px; color: var(--text)">{{ entry.title }}</h3>
              <div class="small muted">{{ entry.desc }}</div>
            </div>
          </div>
        </router-link>
      </div>
    </section>

    <div class="grid-2">
      <section class="panel">
        <div class="panel-title"><h3>卡牌稀有度分布</h3><span class="tiny faint">不含素材卡，每张卡按其最高形态只计一次</span></div>
        <div v-for="item in rarityStats" :key="item.key" style="margin-bottom: 10px">
          <div class="row" style="justify-content: space-between">
            <span class="small">
              <span class="badge" :style="{ background: item.color, color: '#12141c' }">{{ item.label }}</span>
            </span>
            <strong class="small">{{ item.count.toLocaleString() }}</strong>
          </div>
          <div class="bar">
            <span :style="{ width: `${(item.count / (rarityStats[0]?.count || 1)) * 100}%`, background: item.color }"></span>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title"><h3>属性分布</h3><span class="tiny faint">按同卡代表卡的主技能属性归类</span></div>
        <div v-for="item in attrStats" :key="item.key" style="margin-bottom: 10px">
          <div class="row" style="justify-content: space-between">
            <span class="small">
              <span class="badge" :style="{ background: item.color, color: '#12141c' }">{{ item.label }}</span>
            </span>
            <strong class="small">{{ item.count.toLocaleString() }}</strong>
          </div>
          <div class="bar">
            <span :style="{ width: `${(item.count / (attrStats[0]?.count || 1)) * 100}%`, background: item.color }"></span>
          </div>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-title">
        <h3>Boss 分组（当前开放）</h3>
        <router-link to="/bosses" class="small">查看全部 →</router-link>
      </div>
      <div class="chip-group">
        <router-link
          v-for="[name, count] in topBossGroups"
          :key="name"
          class="chip"
          :to="{ path: '/bosses', query: { group: name } }"
        >
          {{ name }} <span class="faint">{{ count }}</span>
        </router-link>
      </div>
    </section>
  </div>
</template>
