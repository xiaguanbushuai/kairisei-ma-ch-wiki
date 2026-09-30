<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { attrColor, attrLabel, cardThumb, getCards, getSkills } from '../api.js'
import { getMatcher } from '../keywords.js'
import SkillText from '../components/SkillText.vue'

const route = useRoute()
const router = useRouter()

const skills = ref([])
const keywords = ref(null)
const loading = ref(true)
const expanded = ref(new Set())
const showKeywordPanel = ref(false)

const filters = reactive({
  keyword: '',
  attr: '',
  job: '',
  kind: '',
  target: '',
  phys: '',
})

const JOB_LABELS = { MERCENARY: '佣兵', MILLIONAIRE: '富豪', THIEF: '盗贼', SINGER: '歌姬', NULL: '通用' }
const ATTR_LABELS = { FIRE: '火', ICE: '冰', WIND: '风', LIGHT: '光', DARK: '暗' }
const KIND_LABELS = { ATTACK: '攻击', SORCERY: '魔法', RECOVERY: '回复', SUPPORT: '支援', DEFENSE: '防御', JAMMING: '妨害' }
const PHYS_LABELS = { PHYSICS: '物理', MAGIC: '魔法', ALL: '物理+魔法' }

onMounted(async () => {
  const [skillMap, cards, matcher] = await Promise.all([getSkills(), getCards(), getMatcher()])
  keywords.value = matcher

  const cardOwners = new Map()
  for (const card of cards) {
    if (!card.skillId) continue
    const key = String(card.skillId)
    if (!cardOwners.has(key)) cardOwners.set(key, [])
    cardOwners.get(key).push(card)
  }

  skills.value = Object.values(skillMap)
    .filter((skill) => skill.name)
    .map((skill) => ({ ...skill, cards: (cardOwners.get(String(skill.id)) || []).sort((a, b) => a.id - b.id) }))
    .sort((a, b) => b.cards.length - a.cards.length || a.id - b.id)

  applyQuery(route.query)
  loading.value = false
})

/** URL → 筛选状态（支持关键词链接直接跳转进来） */
function applyQuery(query) {
  filters.keyword = typeof query.q === 'string' ? query.q : ''
  filters.attr = typeof query.attr === 'string' ? query.attr : ''
  filters.job = typeof query.job === 'string' ? query.job : ''
  filters.kind = typeof query.kind === 'string' ? query.kind : ''
  filters.target = typeof query.target === 'string' ? query.target : ''
  filters.phys = typeof query.phys === 'string' ? query.phys : ''
}

/** 筛选状态 → URL（可分享/可回退） */
watch(filters, () => {
  if (loading.value) return
  const query = {}
  if (filters.keyword) query.q = filters.keyword
  if (filters.attr) query.attr = filters.attr
  if (filters.job) query.job = filters.job
  if (filters.kind) query.kind = filters.kind
  if (filters.target) query.target = filters.target
  if (filters.phys) query.phys = filters.phys
  router.replace({ query })
})

// 浏览器前进/后退时同步筛选
watch(
  () => route.query,
  (query) => {
    if (route.name === 'skills' && !loading.value) applyQuery(query)
  },
)

const attrOptions = computed(() => [...new Set(skills.value.flatMap((s) => (s.attr || '').split('_')).filter(Boolean))])
const jobOptions = computed(() => [...new Set(skills.value.map((s) => s.job).filter(Boolean))])
const kindOptions = computed(() => [...new Set(skills.value.map((s) => s.kind).filter(Boolean))])
const targetOptions = computed(() => [...new Set(skills.value.map((s) => s.target).filter(Boolean))])
const physOptions = computed(() => [...new Set(skills.value.map((s) => s.physMagic).filter(Boolean))])

const keywordGroups = computed(() => {
  if (!keywords.value) return []
  return keywords.value.groups
    .map((group) => ({
      ...group,
      items: keywords.value.terms.filter((term) => term.group === group.key),
    }))
    .filter((group) => group.items.length)
})

/** 关键词是否正被用作筛选（用于高亮 chip） */
function isTermActive(term) {
  const filter = term.filter || {}
  if (filter.type === 'target') return filters.target === filter.value
  if (filter.type === 'attr') return filters.attr === filter.value
  if (filter.type === 'phys') return filters.phys === filter.value
  return filters.keyword === term.label
}

function clickTerm(term) {
  const filter = term.filter || {}
  if (filter.type === 'target') filters.target = filters.target === filter.value ? '' : filter.value
  else if (filter.type === 'attr') filters.attr = filters.attr === filter.value ? '' : filter.value
  else if (filter.type === 'phys') filters.phys = filters.phys === filter.value ? '' : filter.value
  else filters.keyword = filters.keyword === term.label ? '' : term.label
}

function reset() {
  filters.keyword = ''
  filters.attr = ''
  filters.job = ''
  filters.kind = ''
  filters.target = ''
  filters.phys = ''
}

/**
 * 关键词若是命中了某个术语（如「回复」），则按该术语的全部别名做 OR 匹配，
 * 保证筛选结果与速查面板 chip 上的命中数口径一致
 * （否则「回复」只匹配 2 条，而 chip 显示的 105 是「回复+回復」的并集）。
 */
const keywordAliases = computed(() => {
  const keyword = filters.keyword.trim()
  if (!keyword || !keywords.value) return null
  const term = keywords.value.terms.find(
    (item) => item.label === keyword || (item.aliases || []).includes(keyword),
  )
  return term ? term.aliases : null
})

const filtered = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase()
  const aliases = keywordAliases.value
    ? keywordAliases.value.map((alias) => alias.toLowerCase())
    : null
  return skills.value.filter((skill) => {
    if (filters.attr && !(skill.attr || '').split('_').includes(filters.attr)) return false
    if (filters.job && skill.job !== filters.job) return false
    if (filters.kind && skill.kind !== filters.kind) return false
    if (filters.target && skill.target !== filters.target) return false
    if (filters.phys && skill.physMagic !== filters.phys) return false
    if (keyword) {
      const haystack = `${skill.name} ${skill.sub} ${skill.desc}`.toLowerCase()
      const hit = aliases
        ? aliases.some((alias) => haystack.includes(alias))
        : haystack.includes(keyword)
      if (!hit) return false
    }
    return true
  })
})

/** 命中技能名下的卡牌总数（技能可能被多张卡复用） */
const matchedCardCount = computed(() =>
  filtered.value.reduce((sum, skill) => sum + skill.cards.length, 0),
)

const visible = computed(() => filtered.value.slice(0, 300))

function toggle(id) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}
</script>

<template>
  <div v-if="loading" class="loading">正在加载技能数据 …</div>

  <div v-else>
    <section class="panel">
      <div class="panel-title">
        <h1 style="margin: 0">技能索引</h1>
        <span class="small muted">
          匹配 <strong>{{ filtered.length.toLocaleString() }}</strong> / {{ skills.length.toLocaleString() }} 条技能
          <template v-if="matchedCardCount">· 涉及 <strong>{{ matchedCardCount.toLocaleString() }}</strong> 张卡</template>
        </span>
      </div>

      <div class="row" style="align-items: flex-end">
        <div class="field" style="flex: 1 1 280px">
          <label>技能名或效果关键词</label>
          <input v-model="filters.keyword" type="text" placeholder="如：风属性伤害 / 回复 / 敌全体 / 提升" />
        </div>
        <div class="field">
          <label>属性</label>
          <select v-model="filters.attr">
            <option value="">全部</option>
            <option v-for="name in attrOptions" :key="name" :value="name">{{ ATTR_LABELS[name] || name }}</option>
          </select>
        </div>
        <div class="field">
          <label>职业</label>
          <select v-model="filters.job">
            <option value="">全部</option>
            <option v-for="name in jobOptions" :key="name" :value="name">{{ JOB_LABELS[name] || name }}</option>
          </select>
        </div>
        <div class="field">
          <label>类型</label>
          <select v-model="filters.kind">
            <option value="">全部</option>
            <option v-for="name in kindOptions" :key="name" :value="name">{{ KIND_LABELS[name] || name }}</option>
          </select>
        </div>
        <div class="field">
          <label>目标</label>
          <select v-model="filters.target">
            <option value="">全部</option>
            <option v-for="name in targetOptions" :key="name" :value="name">
              {{ { ENEMY_ONE: '敌单体', ENEMY_ALL: '敌全体', USER_ONE: '己方单体', USER_ALL: '己方全体', SELF: '自身', ENEMY_RANDOM: '敌随机' }[name] || name }}
            </option>
          </select>
        </div>
        <div class="field">
          <label>伤害类型</label>
          <select v-model="filters.phys">
            <option value="">全部</option>
            <option v-for="name in physOptions" :key="name" :value="name">{{ PHYS_LABELS[name] || name }}</option>
          </select>
        </div>
        <button class="btn" @click="reset">重置</button>
      </div>

      <!-- 关键词速查：点击即筛选，来源 ETL 自动统计 -->
      <div v-if="keywordGroups.length" style="margin-top: 14px">
        <button class="btn small" @click="showKeywordPanel = !showKeywordPanel">
          {{ showKeywordPanel ? '收起关键词速查 ▲' : '关键词速查 ▼' }}
        </button>
        <div v-if="showKeywordPanel" style="margin-top: 10px">
          <div v-for="group in keywordGroups" :key="group.key" class="row" style="align-items: flex-start; margin-bottom: 8px">
            <span class="tiny faint" style="flex: 0 0 64px; padding-top: 5px">{{ group.label }}</span>
            <div class="chip-group">
              <button
                v-for="term in group.items"
                :key="term.label"
                class="chip"
                :class="{ on: isTermActive(term) }"
                :title="`命中 ${term.count} 条技能（含别名：${term.aliases.join(' / ')}）`"
                @click="clickTerm(term)"
              >
                {{ term.label }} <span class="tiny faint">{{ term.count }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top: 16px">
      <div class="tiny faint" style="margin-bottom: 10px">
        金色数值为技能 Lv.1 时的效果值。技能数值随卡牌等级线性变化，具体卡牌的逐级数值请到卡牌详情页拖动「数值预览」查看。
      </div>
      <div v-for="skill in visible" :key="skill.id" class="skill-card">
        <div class="row" style="justify-content: space-between; align-items: flex-start">
          <div style="min-width: 0">
            <div class="row" style="gap: 8px">
              <span class="skill-name">{{ skill.name }}</span>
              <span v-if="skill.attr" class="badge" :style="{ background: attrColor(skill.attr), color: '#12141c' }">
                {{ attrLabel(skill.attr, ATTR_LABELS) }}
              </span>
              <span class="badge badge-plain">{{ JOB_LABELS[skill.job] || '通用' }}</span>
              <span class="badge badge-plain">{{ KIND_LABELS[skill.kind] || skill.kind || '—' }}</span>
              <span class="badge badge-plain">COST {{ skill.cost > 0 ? skill.cost : '—' }}</span>
            </div>
            <div class="skill-sub">{{ skill.sub }}</div>
            <div class="skill-desc">
              <SkillText :text="skill.desc" :slots="skill.valueSlots" :level="1" />
            </div>
          </div>
          <div style="text-align: right; white-space: nowrap">
            <div class="small"><strong>{{ skill.cards.length }}</strong> 张卡</div>
            <button v-if="skill.cards.length" class="btn small" style="margin-top: 6px" @click="toggle(skill.id)">
              {{ expanded.has(skill.id) ? '收起' : '查看卡牌' }}
            </button>
          </div>
        </div>

        <div v-if="expanded.has(skill.id)" class="row" style="gap: 8px; margin-top: 12px; flex-wrap: wrap">
          <router-link
            v-for="card in skill.cards.slice(0, 40)"
            :key="card.id"
            :to="`/card/${card.id}`"
            style="color: inherit; width: 68px; text-align: center"
          >
            <img :src="cardThumb(card.pictId)" alt="" loading="lazy" style="width: 68px; border-radius: 5px; display: block" />
            <div class="tiny" style="margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
              {{ card.mainName }}
            </div>
          </router-link>
          <span v-if="skill.cards.length > 40" class="tiny faint">… 共 {{ skill.cards.length }} 张</span>
        </div>
      </div>

      <div v-if="!visible.length" class="muted small">没有符合条件的技能。</div>
      <div v-if="filtered.length > 300" class="tiny faint" style="margin-top: 10px">
        仅显示前 300 条，请用关键词或筛选缩小范围。
      </div>
    </section>
  </div>
</template>
