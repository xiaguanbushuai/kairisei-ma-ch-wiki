<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ATTR_COLOR,
  RARITY_LABEL_ORDER,
  attrColor,
  attrLabel,
  cardThumb,
  getCards,
  getMeta,
  getSkills,
  groupFamilies,
  parseRarityParam,
  pickRepresentative,
  rarityLabelColor,
  rarityLabelOf,
} from '../api.js'

const route = useRoute()
const router = useRouter()

const cards = ref([])
const skills = ref({})
const meta = ref(null)
const loading = ref(true)

const filters = reactive({
  keyword: route.query.q || '',
  rarities: [],
  sources: [],
  growths: [],
  attrs: [],
  jobs: [],
  kinds: [],
  costMin: '',
  costMax: '',
  skillKeyword: '',
  onlyNormalCards: true,
  // 同一张卡的多个进化阶段/稀有度版本合并为一条
  mergeFamilies: route.query.merge !== '0',
})

const sortBy = ref('costAsc')
const page = ref(1)
const pageSize = 48

const RARITY_LABEL_RANK = { ...RARITY_LABEL_ORDER }
const JOB_LABELS = { MERCENARY: '佣兵', MILLIONAIRE: '富豪', THIEF: '盗贼', SINGER: '歌姬', NULL: '通用' }
const ATTR_LABELS = { FIRE: '火', ICE: '冰', WIND: '风', LIGHT: '光', DARK: '暗', NULL: '无' }

/** 游戏卡面的技能分类（物/魔/支/防/治/弱），与技能表的 kind 枚举一一对应。 */
const KIND_LABELS = { ATTACK: '物', SORCERY: '魔', SUPPORT: '支', DEFENSE: '防', RECOVERY: '治', JAMMING: '弱' }
const KIND_FULL = { ATTACK: '物理攻击', SORCERY: '魔法攻击', SUPPORT: '支援', DEFENSE: '防御', RECOVERY: '回复', JAMMING: '妨害' }
const KIND_ORDER = ['ATTACK', 'SORCERY', 'SUPPORT', 'DEFENSE', 'RECOVERY', 'JAMMING']
const KIND_COLOR = {
  ATTACK: '#e3524a',
  SORCERY: '#8f6bff',
  SUPPORT: '#4cc06a',
  DEFENSE: '#3f8fe0',
  RECOVERY: '#e6b63c',
  JAMMING: '#8a8fa3',
}

/** 检索文本按卡牌 ID 预建，避免每次筛选重复拼接。 */
const searchMap = ref(new Map())
/** 同卡族：familyId → 成员卡数组 */
const familyMap = ref(new Map())

onMounted(async () => {
  const [metaData, cardList, skillMap] = await Promise.all([getMeta(), getCards(), getSkills()])
  meta.value = metaData
  cards.value = cardList
  skills.value = skillMap

  Object.assign(RARITY_LABEL_RANK, metaData.enums.rarityLabelOrder || RARITY_LABEL_ORDER)
  searchMap.value = new Map(
    cardList.map((card) => {
      const skill = skillMap[card.skillId]
      return [
        card.id,
        {
          name: `${card.title} ${card.mainName}`.toLowerCase(),
          skillText: `${card.skillName} ${skill?.sub || ''} ${skill?.desc || ''} ${skill?.kind || ''}`.toLowerCase(),
        },
      ]
    }),
  )
  familyMap.value = groupFamilies(cardList)

  // 应用来自首页/外链的初始筛选（rarity 传标签，兼容旧的枚举写法）
  if (route.query.rarity) filters.rarities = parseRarityParam(route.query.rarity)
  if (route.query.source) filters.sources = String(route.query.source).split(',').filter(Boolean)
  if (route.query.growth) filters.growths = String(route.query.growth).split(',').filter(Boolean)
  if (route.query.attr) filters.attrs = String(route.query.attr).split(',')
  if (route.query.job) filters.jobs = String(route.query.job).split(',')
  if (route.query.kind) filters.kinds = String(route.query.kind).split(',').filter(Boolean)
  if (route.query.stack === '1') filters.onlyNormalCards = false
  if (route.query.q) filters.keyword = String(route.query.q)
  if (route.query.costMin !== undefined) filters.costMin = String(route.query.costMin)
  if (route.query.costMax !== undefined) filters.costMax = String(route.query.costMax)

  loading.value = false
})

/**
 * 稀有度 chip 按 rarityLabel 分档（N/HN/R/SR/UR/EX/MR/MR+/MR++/MMR/传说）。
 * 客户端的 レアリティ 枚举颗粒度太粗，MR/MR+/MR++ 共用 MILLIONRARE、
 * MMR 与 EX 共用 EXRARE，所以不能拿枚举当筛选单位。
 */
const rarityOptions = computed(() => {
  const counts = new Map()
  for (const members of familyMap.value.values()) {
    const labels = new Set()
    for (const card of members) {
      if (filters.onlyNormalCards && card.stack) continue
      labels.add(rarityLabelOf(card, meta.value?.enums))
    }
    // 计数口径与默认视图一致：一个同卡族只算一张，所以是「涉及卡族数」
    for (const label of labels) counts.set(label, (counts.get(label) || 0) + 1)
  }
  return [...counts.keys()]
    .sort((a, b) => (RARITY_LABEL_RANK[a] ?? 99) - (RARITY_LABEL_RANK[b] ?? 99))
    .map((label) => ({ key: label, label, count: counts.get(label), color: rarityLabelColor(label) }))
})

/**
 * 生成一档 chip（计数口径与稀有度 chip 一致：同卡族只算一张，即「涉及卡族数」）。
 * 同一卡族内各进化阶段共享同一个 source，所以来源档在族内是唯一的。
 */
function buildOptions(order, field) {
  const counts = new Map()
  for (const members of familyMap.value.values()) {
    const labels = new Set()
    for (const card of members) {
      if (filters.onlyNormalCards && card.stack) continue
      if (card[field]) labels.add(card[field])
    }
    for (const label of labels) counts.set(label, (counts.get(label) || 0) + 1)
  }
  return [...counts.keys()]
    .sort((a, b) => {
      const ia = order.indexOf(a)
      const ib = order.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
    .map((label) => ({ key: label, label, count: counts.get(label) }))
}

/** 技能分类的原始档位（英文 key），供 kindOptions 套上中文名与配色。 */
const kindOptionsRaw = computed(() => buildOptions(KIND_ORDER, 'skillKind'))

/**
 * 入手途径 chip。顺序取自 ETL 的 sourceOrder。
 * 同一卡族内各形态共用一条入手途径（取族内最低稀有度形态的记录）。
 */
const sourceOptions = computed(() => buildOptions(meta.value?.enums.sourceOrder || [], 'source'))

/**
 * 成长方式 chip：本形态自身是怎么来的（直接获得 / 进化 / 乖离进化 / 因子觉醒 / 限界突破）。
 * 与入手途径是两个独立维度——扭蛋抽到的 MR 靠因子觉醒升到 MMR，
 * 它的入手途径仍是「扭蛋」，成长方式是「因子觉醒」。
 */
const growthOptions = computed(() => buildOptions(meta.value?.enums.growthOrder || [], 'growth'))

const attrOptions = computed(() => {
  const present = new Set(cards.value.map((card) => card.attr).filter(Boolean))
  return Object.keys(ATTR_COLOR)
    .filter((key) => present.has(key))
    .map((key) => ({ key, label: attrLabel(key, ATTR_LABELS) || key, color: attrColor(key) }))
})

const jobOptions = computed(() => {
  const present = new Set(cards.value.map((card) => card.job).filter(Boolean))
  return Object.keys(JOB_LABELS)
    .filter((key) => present.has(key))
    .map((key) => ({ key, label: JOB_LABELS[key] }))
})

/**
 * 技能分类 chip。口径与稀有度/入手途径一致：一个同卡族只算一张（按族内出现的分类去重）。
 * 同一卡族的进化形态可能换分类（如 UR 物攻 → MR 魔攻），该族会在两档各计一次。
 */
const kindOptions = computed(() =>
  kindOptionsRaw.value.map((item) => ({
    ...item,
    label: KIND_LABELS[item.key] || item.key,
    full: KIND_FULL[item.key] || item.key,
    color: KIND_COLOR[item.key] || '#8a8fa3',
  })),
)

function toggle(list, value) {
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
  else list.push(value)
}

/** 单张卡是否命中当前筛选条件 */
function matchCard(card) {
  const entry = searchMap.value.get(card.id)
  if (!entry) return false
  if (filters.onlyNormalCards && card.stack) return false
  if (filters.rarities.length && !filters.rarities.includes(rarityLabelOf(card, meta.value?.enums))) return false
  if (filters.sources.length && !filters.sources.includes(card.source)) return false
  if (filters.growths.length && !filters.growths.includes(card.growth)) return false
  // 双属性卡（如 ICE_LIGHT）应同时命中「冰」和「光」任一筛选
  if (filters.attrs.length && !filters.attrs.some((a) => (card.attr || '').split('_').includes(a))) return false
  if (filters.jobs.length && !filters.jobs.includes(card.job)) return false
  if (filters.kinds.length && !filters.kinds.includes(card.skillKind)) return false
  const costMin = filters.costMin === '' ? null : Number(filters.costMin)
  const costMax = filters.costMax === '' ? null : Number(filters.costMax)
  if (costMin !== null && card.cost < costMin) return false
  if (costMax !== null && card.cost > costMax) return false
  const keyword = filters.keyword.trim().toLowerCase()
  if (keyword && !entry.name.includes(keyword)) return false
  const skillKeyword = filters.skillKeyword.trim().toLowerCase()
  if (skillKeyword && !entry.skillText.includes(skillKeyword)) return false
  return true
}

/**
 * 同时算出两个口径：
 * - rawCount：命中的原始卡牌记录条数（同一张卡的每个进化阶段各算一条）
 * - families：按同カードID 收拢后，每个同卡族只留一条（代表卡取命中成员里稀有度最高的那张）
 */
const matched = computed(() => {
  const groups = []
  let rawCount = 0
  for (const members of familyMap.value.values()) {
    const hits = members.filter(matchCard)
    if (!hits.length) continue
    rawCount += hits.length
    groups.push({
      card: pickRepresentative(hits, RARITY_LABEL_RANK),
      stageCount: members.length,
      hitCount: hits.length,
    })
  }
  return { groups, rawCount, familyCount: groups.length }
})

/** 排序用 COST：0 视为未定，排到最大之后 */
const costKey = (card) => (card.cost > 0 ? card.cost : 9999)

const comparators = {
  rarity: (a, b) =>
    (RARITY_LABEL_RANK[rarityLabelOf(b, meta.value?.enums)] ?? -1) -
      (RARITY_LABEL_RANK[rarityLabelOf(a, meta.value?.enums)] ?? -1) ||
    b.cost - a.cost ||
    a.id - b.id,
  costDesc: (a, b) => b.cost - a.cost || a.id - b.id,
  // COST 升序：cost=0 是官方表里的"未定"值（特殊卡），当作未知排到最后
  costAsc: (a, b) => costKey(a) - costKey(b) || a.id - b.id,
  hp: (a, b) => b.hpMax - a.hpMax || a.id - b.id,
  atk: (a, b) => b.atkMax - a.atkMax || a.id - b.id,
  int: (a, b) => b.intMax - a.intMax || a.id - b.id,
  mnd: (a, b) => b.mndMax - a.mndMax || a.id - b.id,
  id: (a, b) => a.id - b.id,
}

/** 列表数据：合并模式下每族一条，否则保留原始条目（但带上族内阶段数） */
const filtered = computed(() => {
  const compare = comparators[sortBy.value] || comparators.rarity
  if (filters.mergeFamilies) {
    return [...matched.value.groups].sort((a, b) => compare(a.card, b.card))
  }
  const rows = []
  for (const group of matched.value.groups) {
    for (const member of familyMap.value.get(group.card.sameId || group.card.id) || []) {
      if (matchCard(member)) rows.push({ card: member, stageCount: group.stageCount, hitCount: 1 })
    }
  }
  return rows.sort((a, b) => compare(a.card, b.card))
})

const displayCount = computed(() => filtered.value.length)
const pageCount = computed(() => Math.max(1, Math.ceil(displayCount.value / pageSize)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))

watch(filters, () => {
  page.value = 1
  router.replace({
    query: {
      ...(filters.keyword ? { q: filters.keyword } : {}),
      ...(filters.rarities.length ? { rarity: filters.rarities.join(',') } : {}),
      ...(filters.sources.length ? { source: filters.sources.join(',') } : {}),
      ...(filters.growths.length ? { growth: filters.growths.join(',') } : {}),
      ...(filters.attrs.length ? { attr: filters.attrs.join(',') } : {}),
      ...(filters.jobs.length ? { job: filters.jobs.join(',') } : {}),
      ...(filters.kinds.length ? { kind: filters.kinds.join(',') } : {}),
      ...(filters.costMin !== '' ? { costMin: filters.costMin } : {}),
      ...(filters.costMax !== '' ? { costMax: filters.costMax } : {}),
      ...(filters.mergeFamilies ? {} : { merge: '0' }),
    },
  })
}, { deep: true })

function reset() {
  filters.keyword = ''
  filters.rarities = []
  filters.sources = []
  filters.growths = []
  filters.attrs = []
  filters.jobs = []
  filters.kinds = []
  filters.costMin = ''
  filters.costMax = ''
  filters.skillKeyword = ''
  filters.onlyNormalCards = true
  filters.mergeFamilies = true
  sortBy.value = 'costAsc'
}

function rarityLabel(card) {
  return rarityLabelOf(card, meta.value?.enums)
}

function goPage(value) {
  page.value = Math.min(Math.max(1, value), pageCount.value)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
</script>

<template>
  <div v-if="loading" class="loading">正在加载卡牌数据 …</div>

  <div v-else>
    <section class="panel">
      <div class="panel-title">
        <h1 style="margin: 0">卡牌图鉴</h1>
        <span class="small muted">
          <template v-if="filters.mergeFamilies">
            共 <strong>{{ displayCount.toLocaleString() }}</strong> 张卡
            <span class="faint">（未合并前 {{ matched.rawCount.toLocaleString() }} 条记录）</span>
          </template>
          <template v-else>
            共 <strong>{{ displayCount.toLocaleString() }}</strong> 条记录
            <span class="faint">（按同カードID 合并后 {{ matched.familyCount.toLocaleString() }} 张卡）</span>
          </template>
        </span>
      </div>

      <div class="row" style="align-items: flex-end">
        <div class="field" style="flex: 1 1 220px">
          <label>卡牌名</label>
          <input v-model="filters.keyword" type="text" placeholder="如：库丘林 / 悲恋少女" />
        </div>
        <div class="field" style="flex: 1 1 240px">
          <label>技能关键词 <span class="faint tiny">（搜索技能名与效果说明）</span></label>
          <input v-model="filters.skillKeyword" type="text" placeholder="如：风属性伤害 / 回复 / 敌全体" />
        </div>
        <div class="field">
          <label>COST</label>
          <div class="row" style="gap: 6px; flex-wrap: nowrap">
            <input v-model="filters.costMin" type="number" min="0" max="99" placeholder="最小" />
            <span class="faint">-</span>
            <input v-model="filters.costMax" type="number" min="0" max="99" placeholder="最大" />
          </div>
        </div>
        <div class="field">
          <label>排序</label>
          <select v-model="sortBy">
            <option value="rarity">稀有度 → 高</option>
            <option value="costDesc">COST → 高</option>
            <option value="costAsc">COST → 低</option>
            <option value="hp">HP → 高</option>
            <option value="atk">ATK → 高</option>
            <option value="int">INT → 高</option>
            <option value="mnd">MND → 高</option>
            <option value="id">图鉴 ID → 升序</option>
          </select>
        </div>
        <button class="btn" @click="reset">重置</button>
      </div>

      <div class="row" style="margin-top: 14px; align-items: flex-start">
        <div class="field">
          <label>稀有度 <span class="faint tiny">（按卡面徽标分档，数字为涉及的卡张数）</span></label>
          <div class="chip-group">
            <button
              v-for="item in rarityOptions"
              :key="item.key"
              class="chip"
              :class="{ on: filters.rarities.includes(item.key) }"
              @click="toggle(filters.rarities, item.key)"
            >
              {{ item.label }}<span class="chip-count">{{ item.count }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="row" style="margin-top: 12px; align-items: flex-start">
        <div class="field">
          <label>入手途径 <span class="faint tiny">（整张卡怎么来的，同卡族共用）</span></label>
          <div class="chip-group">
            <button
              v-for="item in sourceOptions"
              :key="item.key"
              class="chip"
              :class="{ on: filters.sources.includes(item.key) }"
              @click="toggle(filters.sources, item.key)"
            >
              {{ item.label }}<span class="chip-count">{{ item.count }}</span>
            </button>
          </div>
        </div>
        <div class="field">
          <label>成长方式 <span class="faint tiny">（这个形态怎么来的）</span></label>
          <div class="chip-group">
            <button
              v-for="item in growthOptions"
              :key="item.key"
              class="chip"
              :class="{ on: filters.growths.includes(item.key) }"
              @click="toggle(filters.growths, item.key)"
            >
              {{ item.label }}<span class="chip-count">{{ item.count }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="row" style="margin-top: 12px; align-items: flex-start">
        <div class="field">
          <label>技能分类 <span class="faint tiny">（按游戏卡面图标：物 / 魔 / 支 / 防 / 治 / 弱）</span></label>
          <div class="chip-group">
            <button
              v-for="item in kindOptions"
              :key="item.key"
              class="chip"
              :class="{ on: filters.kinds.includes(item.key) }"
              :title="`技能分类：${item.full}`"
              @click="toggle(filters.kinds, item.key)"
            >
              <span class="chip-dot" :style="{ background: item.color }"></span>{{ item.label }}<span class="chip-count">{{ item.count }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="row" style="margin-top: 12px; align-items: flex-start">
        <div class="field">
          <label>属性</label>
          <div class="chip-group">
            <button
              v-for="item in attrOptions"
              :key="item.key"
              class="chip"
              :class="{ on: filters.attrs.includes(item.key) }"
              @click="toggle(filters.attrs, item.key)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div class="field">
          <label>职业</label>
          <div class="chip-group">
            <button
              v-for="item in jobOptions"
              :key="item.key"
              class="chip"
              :class="{ on: filters.jobs.includes(item.key) }"
              @click="toggle(filters.jobs, item.key)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div class="field">
          <label>其他</label>
          <div class="chip-group">
            <button
              class="chip"
              :class="{ on: filters.onlyNormalCards }"
              @click="filters.onlyNormalCards = !filters.onlyNormalCards"
            >
              隐藏素材卡
            </button>
            <button
              class="chip"
              :class="{ on: filters.mergeFamilies }"
              title="同一张卡的各进化阶段（如 UR / MR）只算一张，代表卡取稀有度最高的那张"
              @click="filters.mergeFamilies = !filters.mergeFamilies"
            >
              合并同卡（按同カードID）
            </button>
          </div>
        </div>
      </div>
    </section>

    <div class="card-grid" style="margin-top: 16px">
      <router-link v-for="item in paged" :key="item.card.id" class="card-tile" :to="`/card/${item.card.id}`">
        <div class="card-tile-media">
          <img v-if="item.card.pictId" :src="cardThumb(item.card.pictId)" :alt="item.card.mainName" loading="lazy" />
          <div v-else class="no-image">无图</div>
          <div class="card-tile-marks">
            <span class="card-tile-cost">C{{ item.card.cost > 0 ? item.card.cost : '?' }}</span>
            <span
              v-if="item.card.skillKind"
              class="card-tile-kind"
              :style="{ background: KIND_COLOR[item.card.skillKind] || '#8a8fa3' }"
              :title="`技能分类：${KIND_FULL[item.card.skillKind] || item.card.skillKind}`"
            >{{ KIND_LABELS[item.card.skillKind] || '?' }}</span>
          </div>
          <span
            v-if="item.card.attr"
            class="card-tile-attr"
            :style="{ background: attrColor(item.card.attr) }"
          >{{ attrLabel(item.card.attr, ATTR_LABELS) || item.card.attr }}</span>
        </div>
        <div class="card-tile-body">
          <span class="card-tile-title">{{ item.card.title }}</span>
          <span class="card-tile-name">{{ item.card.mainName }}</span>
          <span class="row" style="gap: 4px">
            <span class="badge" :style="{ background: rarityLabelColor(rarityLabel(item.card)), color: '#12141c' }">
              {{ rarityLabel(item.card) }}
            </span>
            <span class="badge badge-plain">{{ JOB_LABELS[item.card.job] || '通用' }}</span>
            <span
              v-if="item.card.source && item.card.source !== '其他 / 未标注' && item.card.source !== '日服卡牌'"
              class="badge badge-plain"
              :title="`入手途径：${item.card.source}`"
            >{{ item.card.source }}</span>
            <span
              v-if="item.card.growth && item.card.growth !== '直接获得'"
              class="badge badge-plain"
              :title="`成长方式：${item.card.growth}`"
            >{{ item.card.growth }}</span>
            <span v-if="item.stageCount > 1" class="badge badge-plain" title="同一张卡的进化阶段数">
              {{ item.stageCount }} 阶段
            </span>
          </span>
          <span class="card-tile-skill" :title="item.card.skillName">{{ item.card.skillName || '—' }}</span>
        </div>
      </router-link>
    </div>

    <div v-if="!paged.length" class="panel" style="margin-top: 16px; text-align: center">
      <span class="muted">没有符合条件的卡牌，试试放宽筛选条件。</span>
    </div>

    <div v-if="pageCount > 1" class="pager">
      <button class="btn" :disabled="page === 1" @click="goPage(1)">«</button>
      <button class="btn" :disabled="page === 1" @click="goPage(page - 1)">上一页</button>
      <span class="small muted">第 {{ page }} / {{ pageCount }} 页</span>
      <button class="btn" :disabled="page === pageCount" @click="goPage(page + 1)">下一页</button>
      <button class="btn" :disabled="page === pageCount" @click="goPage(pageCount)">»</button>
    </div>
  </div>
</template>
