<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  attrColor,
  attrLabel,
  cardImage,
  cardThumb,
  getCards,
  getEvolutions,
  getExpTables,
  getItems,
  getMeta,
  getSkills,
  formatNumber,
  rarityLabelColor,
  rarityLabelOf,
  slotKind,
} from '../api.js'
import SkillText from '../components/SkillText.vue'

const route = useRoute()

const cardMap = ref(new Map())
const skills = ref({})
const evolutions = ref({})
const items = ref({})
const expTables = ref({})
const meta = ref(null)
const loading = ref(true)

const JOB_LABELS = { MERCENARY: '佣兵', MILLIONAIRE: '富豪', THIEF: '盗贼', SINGER: '歌姬', NULL: '通用' }
const ATTR_LABELS = { FIRE: '火', ICE: '冰', WIND: '风', LIGHT: '光', DARK: '暗' }
const TARGET_LABELS = {
  ENEMY_ONE: '敌单体',
  ENEMY_ALL: '敌全体',
  USER_ONE: '己方单体',
  USER_ALL: '己方全体',
  SELF: '自身',
  ENEMY_RANDOM: '敌随机',
}
const KIND_LABELS = { ATTACK: '攻击', SORCERY: '魔法', RECOVERY: '回复', SUPPORT: '支援', DEFENSE: '防御', JAMMING: '妨害' }

onMounted(async () => {
  const [metaData, cardList, skillMap, evolutionMap, itemMap, tables] = await Promise.all([
    getMeta(),
    getCards(),
    getSkills(),
    getEvolutions(),
    getItems(),
    getExpTables(),
  ])
  meta.value = metaData
  cardMap.value = new Map(cardList.map((card) => [String(card.id), card]))
  skills.value = skillMap
  evolutions.value = evolutionMap
  items.value = itemMap
  expTables.value = tables
  loading.value = false
})

const cardId = computed(() => String(route.params.id))
const card = computed(() => cardMap.value.get(cardId.value))

/** 引用此卡作为进化素材的来源卡 */
const usedAsMaterial = computed(() => {
  const result = []
  for (const [fromId, evolution] of Object.entries(evolutions.value)) {
    if (evolution.materials?.some((material) => String(material.cardId) === cardId.value)) {
      const owner = cardMap.value.get(fromId)
      if (owner) result.push({ card: owner, evolution })
    }
  }
  return result
})

/** 进化为当前卡的来源卡 */
const preEvolution = computed(() => {
  const result = []
  for (const [fromId, evolution] of Object.entries(evolutions.value)) {
    if (String(evolution.to) === cardId.value) {
      const owner = cardMap.value.get(fromId)
      if (owner) result.push(owner)
    }
  }
  return result
})

const nextEvolution = computed(() => evolutions.value[cardId.value] || null)

function materialInfo(cardIdValue) {
  const found = cardMap.value.get(String(cardIdValue))
  return found
    ? { name: found.mainName, title: found.title, rarity: found.rarity, rarityLabel: found.rarityLabel, pictId: found.pictId, stack: found.stack }
    : { name: `#${cardIdValue}`, title: '', rarity: '', rarityLabel: '', pictId: 0, stack: false }
}

const mainSkill = computed(() => (card.value ? skills.value[card.value.skillId] : null))
const arthurSkill = computed(() => (card.value?.arthurSkillId ? skills.value[card.value.arthurSkillId] : null))
const supportSkills = computed(() =>
  (card.value?.supportSkillIds || []).map((id) => skills.value[id]).filter(Boolean),
)

/** 是否存在「百分比」类槽位（如「叠加目前血量4%的威力」——随自身当前 HP 变化） */
const hasPercentSlot = computed(() =>
  Object.keys(mainSkill.value?.valueSlots || {}).some((token) => slotKind(mainSkill.value, token) === 'pct'),
)

/** 尚未验证的占位符编号，形如 {11}、{52} */
const unresolvedLabel = computed(() =>
  (mainSkill.value?.unresolvedTokens || []).map((token) => `{${token}}`).join('、'),
)

/** 技能数值预览等级：默认卡牌满级，可拖动查看任意等级（数值只随等级变化，与 ATK / INT 无关） */
const viewLevel = ref(1)
watch(
  card,
  (value) => {
    if (value) viewLevel.value = value.levelMax || 1
  },
  { immediate: true },
)

/** 升级曲线：累积经验 */
const levelCurve = computed(() => {
  if (!card.value) return []
  const table = expTables.value[card.value.expTableId]
  if (!table || !table.length) return []
  const maxLevel = Math.min(card.value.levelMax || table.length + 1, table.length + 1)
  const points = []
  let cumulative = 0
  for (let level = 1; level <= maxLevel; level += 1) {
    points.push({ level, step: level === 1 ? 0 : table[level - 2] || 0, cumulative })
    cumulative += table[level - 1] || 0
  }
  return points
})

const curveChart = computed(() => {
  const points = levelCurve.value
  if (points.length < 2) return null
  const width = 640
  const height = 180
  const padding = { left: 52, right: 12, top: 12, bottom: 26 }
  const maxX = points.length - 1
  const maxY = points[points.length - 1].cumulative || 1
  const plotWidth = width - padding.left - padding.right
  const plotHeight = height - padding.top - padding.bottom
  const coords = points.map((point, index) => {
    const x = padding.left + (index / maxX) * plotWidth
    const y = padding.top + plotHeight - (point.cumulative / maxY) * plotHeight
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
    y: padding.top + plotHeight - ratio * plotHeight,
    value: Math.round(maxY * ratio),
  }))
  const levelTicks = points.filter((point) => point.level === 1 || point.level % 10 === 0)
  return { width, height, padding, plotWidth, plotHeight, coords, ticks, levelTicks, maxX, maxY }
})

/** 每 10 级一行，便于查看 */
const levelTable = computed(() =>
  levelCurve.value.filter((point) => point.level % 10 === 0 || point.level === 1),
)
</script>

<template>
  <div v-if="loading" class="loading">正在加载 …</div>
  <div v-else-if="!card" class="panel">未找到该卡牌（ID {{ cardId }}）。</div>

  <div v-else>
    <div class="row small" style="margin-bottom: 12px">
      <router-link to="/cards" class="faint">← 返回卡牌列表</router-link>
      <span class="faint">/</span>
      <span class="muted">ID {{ card.id }}</span>
    </div>

    <section class="panel">
      <div class="detail-head">
        <div class="detail-art">
          <img v-if="card.pictId" :src="cardImage(card.pictId)" :alt="card.mainName" />
          <div v-else class="no-image" style="aspect-ratio: 3/4; display: grid; place-items: center">无图</div>
        </div>

        <div>
          <div class="row" style="gap: 8px; margin-bottom: 6px">
            <span class="badge" :style="{ background: rarityLabelColor(rarityLabelOf(card, meta.enums)), color: '#12141c' }">
              {{ rarityLabelOf(card, meta.enums) }}
            </span>
            <span class="badge badge-plain">{{ JOB_LABELS[card.job] || '通用' }}</span>
            <span
              v-if="card.attr"
              class="badge"
              :style="{ background: attrColor(card.attr), color: '#12141c' }"
            >{{ attrLabel(card.attr, ATTR_LABELS) }}属性</span>
            <span class="badge badge-plain">COST {{ card.cost > 0 ? card.cost : '—' }}</span>
            <span v-if="card.stack" class="badge badge-plain">素材 / 堆叠卡</span>
          </div>

          <h1 style="margin-bottom: 2px">{{ card.mainName }}</h1>
          <div class="muted small">{{ card.title }}</div>

          <div class="stat-grid" style="margin-top: 14px">
            <div class="stat">
              <div class="stat-label">HP</div>
              <div class="stat-value">{{ formatNumber(card.hp) }} <small>→ {{ formatNumber(card.hpMax) }}</small></div>
            </div>
            <div class="stat">
              <div class="stat-label">ATK 物理攻击</div>
              <div class="stat-value">{{ formatNumber(card.atk) }} <small>→ {{ formatNumber(card.atkMax) }}</small></div>
            </div>
            <div class="stat">
              <div class="stat-label">INT 魔法攻击</div>
              <div class="stat-value">{{ formatNumber(card.int) }} <small>→ {{ formatNumber(card.intMax) }}</small></div>
            </div>
            <div class="stat">
              <div class="stat-label">MND 回复 / 精神</div>
              <div class="stat-value">{{ formatNumber(card.mnd) }} <small>→ {{ formatNumber(card.mndMax) }}</small></div>
            </div>
            <div class="stat">
              <div class="stat-label">等级上限</div>
              <div class="stat-value">{{ card.levelMax }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">名声上限</div>
              <div class="stat-value">{{ card.fameMax }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">忠诚度上限</div>
              <div class="stat-value">{{ card.loveMax }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">出售价格</div>
              <div class="stat-value">{{ formatNumber(card.sellGold) }} <small>金币</small></div>
            </div>
            <div v-if="card.addExp > 0" class="stat">
              <div class="stat-label">融合提供经验</div>
              <div class="stat-value">{{ formatNumber(card.addExp) }} <small>EXP</small></div>
            </div>
          </div>

          <div class="row small muted" style="margin-top: 12px; gap: 16px">
            <span>
              入手途径：<strong :title="card.channel || '卡表未记录'">{{ card.source }}</strong>
            </span>
            <span>成长方式：<strong>{{ card.growth }}</strong></span>
            <span class="faint" :title="'客户端 card.csv 卡牌出处原文'">
              （原始记录：{{ card.acquire || '空' }}）
            </span>
            <span>卡牌作用：{{ card.usage || '—' }}</span>
            <span v-if="card.decomposable === 1">可分解（分解基数 {{ card.decomposeRadix }}）</span>
            <span v-if="card.developRadix > 0">可培养（培养基数 {{ card.developRadix }}）</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 技能 -->
    <section class="panel">
      <div class="panel-title">
        <h2>技能</h2>
        <span v-if="card.levelMax > 1" class="row tiny faint" style="gap: 8px">
          <span>数值预览</span>
          <input v-model.number="viewLevel" type="range" min="1" :max="card.levelMax" step="1" class="lv-range" />
          <span class="badge badge-plain">Lv.{{ viewLevel }}</span>
          <button v-if="viewLevel !== card.levelMax" class="btn small" type="button" @click="viewLevel = card.levelMax">
            跳到满级
          </button>
        </span>
      </div>

      <div v-if="mainSkill" class="skill-card">
        <div class="row" style="justify-content: space-between">
          <span class="skill-name">通常技能 · {{ mainSkill.name }}</span>
          <span class="row" style="gap: 6px">
            <span v-if="mainSkill.attr" class="badge" :style="{ background: attrColor(mainSkill.attr), color: '#12141c' }">
              {{ attrLabel(mainSkill.attr, ATTR_LABELS) }}
            </span>
            <span class="badge badge-plain">{{ KIND_LABELS[mainSkill.kind] || mainSkill.kind || '—' }}</span>
            <span class="badge badge-plain">COST {{ mainSkill.cost > 0 ? mainSkill.cost : '—' }}</span>
          </span>
        </div>
        <div class="skill-sub">{{ mainSkill.sub }}</div>
        <div class="skill-desc">
          <SkillText :text="mainSkill.desc" :slots="mainSkill.valueSlots" :level="viewLevel" />
        </div>
        <div class="row tiny faint" style="margin-top: 8px; gap: 14px">
          <span>目标：{{ TARGET_LABELS[mainSkill.target] || mainSkill.target || '—' }}</span>
          <span>物理 / 魔法：{{ mainSkill.physMagic === 'MAGIC' ? '魔法' : '物理' }}</span>
          <span>技能等级：{{ mainSkill.rank || '—' }}</span>
          <span>仇恨倍率：{{ mainSkill.hate }}</span>
          <span>技能 ID：{{ mainSkill.id }}</span>
        </div>
        <div class="tiny faint" style="margin-top: 6px">
          <template v-if="mainSkill.mainToken">
            金色数值 = 该技能在 Lv.{{ viewLevel }} 时的效果值（只随技能等级变化，与 ATK / INT 无关）。
          </template>
          <template v-if="hasPercentSlot">
            「叠加目前血量百分比」恒定，实际威力随自身当前 HP 变化。
          </template>
          <template v-if="mainSkill.unresolvedTokens?.length">
            灰底 <span class="eff-num eff-unknown">?</span> 表示该占位符（{{ unresolvedLabel }}）的效果类型尚未验证，暂不显示数值——悬停可见原占位符编号。
          </template>
          <template v-if="!mainSkill.mainToken && !mainSkill.unresolvedTokens?.length">
            说明中的 <code>{N}</code> 为效果值占位符，游戏内按效果槽位计算。
          </template>
        </div>
      </div>
      <div v-else class="muted small">此卡没有主技能记录。</div>

      <div v-if="arthurSkill" style="margin-top: 14px">
        <h3>亚瑟加成技能</h3>
        <div class="skill-card">
          <div class="row" style="justify-content: space-between">
            <span class="skill-name">{{ arthurSkill.name }}</span>
            <span class="row" style="gap: 6px">
              <span v-if="arthurSkill.attr" class="badge" :style="{ background: attrColor(arthurSkill.attr), color: '#12141c' }">
                {{ attrLabel(arthurSkill.attr, ATTR_LABELS) }}
              </span>
              <span class="badge badge-plain">{{ KIND_LABELS[arthurSkill.kind] || arthurSkill.kind || '—' }}</span>
              <span class="badge badge-plain">COST {{ arthurSkill.cost > 0 ? arthurSkill.cost : '—' }}</span>
            </span>
          </div>
          <div class="skill-sub">{{ arthurSkill.sub }}</div>
          <div class="skill-desc">
            <SkillText :text="arthurSkill.desc" :slots="arthurSkill.valueSlots" :level="viewLevel" />
          </div>
          <div class="row tiny faint" style="margin-top: 8px; gap: 14px">
            <span>目标：{{ TARGET_LABELS[arthurSkill.target] || arthurSkill.target || '—' }}</span>
            <span>物理 / 魔法：{{ arthurSkill.physMagic === 'MAGIC' ? '魔法' : '物理' }}</span>
            <span>技能 ID：{{ arthurSkill.id }}</span>
          </div>
          <div class="tiny faint" style="margin-top: 6px">
            亚瑟加成版：数值与通常技能不同（通常为 2～3 倍），并额外附带连携威力提升。
          </div>
        </div>
      </div>

      <div v-if="supportSkills.length" style="margin-top: 14px">
        <h3>支援技能（按技能等级）</h3>
        <div v-for="(skill, index) in supportSkills" :key="skill.id" class="skill-card">
          <div class="row" style="justify-content: space-between">
            <span class="skill-name">{{ skill.name }}</span>
            <span class="badge badge-plain">Lv.{{ index + 1 }}</span>
          </div>
          <div class="skill-desc">
            <SkillText :text="skill.desc" :slots="skill.valueSlots" :level="viewLevel" />
          </div>
        </div>
      </div>
    </section>

    <!-- 进化 -->
    <section class="panel">
      <div class="panel-title"><h2>进化</h2></div>

      <div v-if="preEvolution.length || nextEvolution" class="evo-chain">
        <template v-if="preEvolution.length">
          <router-link
            v-for="item in preEvolution"
            :key="item.id"
            class="evo-node"
            :to="`/card/${item.id}`"
            style="color: inherit"
          >
            <div class="tiny faint">{{ item.title }}</div>
            <div class="small"><strong>{{ item.mainName }}</strong></div>
            <div class="tiny faint">ID {{ item.id }}</div>
          </router-link>
          <span class="evo-arrow">→</span>
        </template>

        <div class="evo-node current">
          <div class="tiny faint">{{ card.title }}</div>
          <div class="small"><strong>{{ card.mainName }}</strong></div>
          <div class="tiny faint">当前 · ID {{ card.id }}</div>
        </div>

        <template v-if="nextEvolution && nextEvolution.to">
          <span class="evo-arrow">→</span>
          <router-link class="evo-node" :to="`/card/${nextEvolution.to}`" style="color: inherit">
            <div class="tiny faint">{{ materialInfo(nextEvolution.to).title }}</div>
            <div class="small"><strong>{{ materialInfo(nextEvolution.to).name }}</strong></div>
            <div class="tiny faint">ID {{ nextEvolution.to }}</div>
          </router-link>
        </template>
      </div>

      <div v-else class="muted small">此卡没有进化记录。</div>

      <div v-if="nextEvolution" style="margin-top: 16px">
        <h3>进化所需</h3>
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>项目</th>
                <th>内容</th>
                <th class="num">数量</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>金币</td>
                <td colspan="2" class="num">{{ formatNumber(nextEvolution.gold) }}</td>
              </tr>
              <tr v-for="material in nextEvolution.materials" :key="material.cardId">
                <td>
                  <router-link :to="`/card/${material.cardId}`" class="row" style="gap: 8px; flex-wrap: nowrap">
                    <img
                      v-if="materialInfo(material.cardId).pictId"
                      :src="cardThumb(materialInfo(material.cardId).pictId)"
                      alt=""
                      style="width: 34px; border-radius: 4px"
                    />
                    <span>{{ materialInfo(material.cardId).name }}</span>
                  </router-link>
                </td>
                <td class="muted small">
                  {{ materialInfo(material.cardId).title }}
                  <span v-if="material.fame">· 名声 {{ material.fame }}</span>
                </td>
                <td class="num">×{{ material.num }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="tiny faint" style="margin-top: 6px">
          进化类型：{{ nextEvolution.type || '—' }}；等级继承：{{ nextEvolution.keepLevel ? '是' : '否' }}
        </div>
      </div>

      <div v-if="usedAsMaterial.length" style="margin-top: 16px">
        <h3>此卡可作为以下卡牌的进化素材</h3>
        <ul class="list-plain small">
          <li v-for="entry in usedAsMaterial" :key="entry.card.id">
            <router-link :to="`/card/${entry.card.id}`">{{ entry.card.title }} {{ entry.card.mainName }}</router-link>
            <span class="faint tiny">
              （需要
              {{ entry.evolution.materials.find((m) => String(m.cardId) === cardId)?.num || 1 }} 张）
            </span>
          </li>
        </ul>
      </div>
    </section>

    <!-- 升级 -->
    <section class="panel">
      <div class="panel-title">
        <h2>升级经验</h2>
        <span class="tiny faint">经验表 ID {{ card.expTableId }}（累积经验）</span>
      </div>

      <div v-if="curveChart" class="table-wrap">
        <svg :viewBox="`0 0 ${curveChart.width} ${curveChart.height}`" style="width: 100%; min-width: 480px; height: auto">
          <line
            v-for="tick in curveChart.ticks"
            :key="`t${tick.y}`"
            :x1="curveChart.padding.left"
            :x2="curveChart.width - curveChart.padding.right"
            :y1="tick.y"
            :y2="tick.y"
            stroke="var(--border)"
            stroke-dasharray="3 3"
          />
          <text
            v-for="tick in curveChart.ticks"
            :key="`tl${tick.y}`"
            :x="curveChart.padding.left - 6"
            :y="tick.y + 4"
            text-anchor="end"
            font-size="10"
            fill="var(--text-faint)"
          >
            {{ tick.value.toLocaleString() }}
          </text>
          <polyline :points="curveChart.coords.join(' ')" fill="none" stroke="var(--accent)" stroke-width="2" />
          <text
            v-for="point in curveChart.levelTicks"
            :key="`x${point.level}`"
            :x="curveChart.padding.left + ((point.level - 1) / curveChart.maxX) * curveChart.plotWidth"
            :y="curveChart.height - 8"
            text-anchor="middle"
            font-size="10"
            fill="var(--text-faint)"
          >
            Lv{{ point.level }}
          </text>
        </svg>
      </div>

      <div v-if="levelTable.length" class="table-wrap" style="margin-top: 10px">
        <table class="data">
          <thead>
            <tr>
              <th>等级</th>
              <th class="num">本级所需经验</th>
              <th class="num">累计所需经验</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="point in levelTable" :key="point.level">
              <td>Lv.{{ point.level }}</td>
              <td class="num">{{ formatNumber(point.step) }}</td>
              <td class="num">{{ formatNumber(point.cumulative) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="muted small">没有该等级段的经验数据。</div>
    </section>

    <!-- 资料 -->
    <section class="panel">
      <div class="panel-title"><h2>卡牌资料</h2></div>
      <div class="grid-2">
        <div>
          <div class="small"><span class="faint">插画师：</span>{{ card.illustrator || '—' }}</div>
          <div class="small" style="margin-top: 6px"><span class="faint">声优：</span>{{ card.cv || '—' }}</div>
          <div class="small" style="margin-top: 10px">
            <span class="faint">同卡 ID：</span>{{ card.sameId }}
            <span class="faint" style="margin-left: 12px">基卡 ID：</span>{{ card.baseId }}
            <span class="faint" style="margin-left: 12px">卡面 ID：</span>{{ card.pictId }}
          </div>
        </div>
        <div>
          <div class="small faint">卡牌故事</div>
          <p class="small" style="margin-top: 6px; line-height: 1.85">{{ card.flavor || '（无）' }}</p>
        </div>
      </div>
    </section>
  </div>
</template>
