<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  attrColor,
  attrLabel,
  RARITY_COLOR,
  REWARD_TYPE_LABEL,
  cardImage,
  cardThumb,
  formatNumber,
  getBossDetail,
  getBossIndex,
  getCards,
} from '../api.js'

const route = useRoute()

const bossMap = ref(new Map())
const details = ref({})
const cardMap = ref(new Map())
const loading = ref(true)

const ATTR_LABELS = { FIRE: '火', ICE: '冰', WIND: '风', LIGHT: '光', DARK: '暗', NULL: '无' }
const ATTR_INDEX = { 1: 'FIRE', 2: 'ICE', 3: 'WIND', 4: 'LIGHT', 5: 'DARK' }
const START_RULE = {
  0: '常规',
  1: '仅自身卡组（单人）',
  2: '仅单人',
  3: '仅多人',
}
const PARTY_CONDITION = {
  NULL: '—',
  PARTS_ALL_BREAK: '全部部位破坏后',
  PARTS_ONE_BREAK: '任意部位破坏后',
}
const TRIGGER_LABEL = {
  NULL: '—',
  PHYSIC_DAMAGE: '受到物理伤害时',
  MAGIC_DAMAGE: '受到魔法伤害时',
}

onMounted(async () => {
  const [list, detail, cards] = await Promise.all([getBossIndex(), getBossDetail(), getCards()])
  bossMap.value = new Map(list.map((boss) => [String(boss.id), boss]))
  details.value = detail
  cardMap.value = new Map(cards.map((card) => [String(card.id), card]))
  loading.value = false
})

const bossId = computed(() => String(route.params.id))
const boss = computed(() => bossMap.value.get(bossId.value))
const detail = computed(() => details.value[bossId.value])

function rewardLabel(reward) {
  if (!reward) return '—'
  const type = REWARD_TYPE_LABEL[reward.type] || `类型 ${reward.type}`
  if (reward.type === 13 && reward.reward_typeid) {
    const card = cardMap.value.get(String(reward.reward_typeid))
    if (card) return `${card.title} ${card.mainName}`
  }
  return type
}

function rewardCard(reward) {
  if (reward?.type === 13 && reward.reward_typeid) return cardMap.value.get(String(reward.reward_typeid))
  return null
}

/** 行动轴：把 turns / loopTurns 数组转成「回合 → 行动」列表 */
function orderTurns(order) {
  const rows = []
  ;(order?.turns || []).forEach((value, index) => {
    if (value) rows.push({ turn: index + 1, action: value, loop: false })
  })
  ;(order?.loopTurns || []).forEach((value, index) => {
    if (value) rows.push({ turn: index + 1, action: value, loop: true })
  })
  return rows.sort((a, b) => a.turn - b.turn)
}

function hasOrderData(order) {
  if (!order) return false
  return orderTurns(order).length > 0 || order.trigger && order.trigger !== 'NULL'
}
</script>

<template>
  <div v-if="loading" class="loading">正在加载 …</div>
  <div v-else-if="!boss" class="panel">未找到该 Boss（ID {{ bossId }}）。</div>

  <div v-else>
    <div class="row small" style="margin-bottom: 12px">
      <router-link to="/bosses" class="faint">← 返回 Boss 列表</router-link>
      <span class="faint">/</span>
      <span class="muted">{{ boss.groupName }} · {{ boss.difficulty }}</span>
    </div>

    <section class="panel">
      <div class="row" style="align-items: flex-start; gap: 18px">
        <div style="flex: 1 1 auto">
          <div class="row" style="gap: 8px; margin-bottom: 6px">
            <span class="badge badge-plain">{{ boss.difficulty || '—' }}</span>
            <span class="badge badge-plain">BP {{ boss.bpUse }}<template v-if="boss.bpUseHalf"> / 半 {{ boss.bpUseHalf }}</template></span>
            <span class="badge badge-plain">{{ START_RULE[boss.startRule] || '常规' }}</span>
            <span class="badge badge-plain">{{ boss.continue === 1 ? '可续关' : '不可续关' }}</span>
            <span class="badge badge-plain">{{ boss.past ? '往期' : '活动 / 素材' }}</span>
          </div>

          <h1 style="margin-bottom: 2px">{{ boss.name || `#${boss.id}` }}</h1>
          <div class="muted small">{{ boss.groupName }}<template v-if="boss.groupSub"> · {{ boss.groupSub }}</template></div>
          <div class="tiny faint" style="margin-top: 6px">Boss ID {{ boss.id }}<template v-if="boss.characterId"> · 角色 ID {{ boss.characterId }}</template></div>

          <div v-if="boss.rewardCards?.length" style="margin-top: 14px">
            <div class="small faint" style="margin-bottom: 6px">奖励卡牌</div>
            <div class="row" style="gap: 8px">
              <router-link
                v-for="reward in boss.rewardCards"
                :key="reward.id"
                :to="`/card/${reward.id}`"
                style="color: inherit; text-align: center; width: 74px"
              >
                <img :src="cardThumb(reward.pictId || reward.id)" alt="" style="width: 74px; border-radius: 6px" />
                <div class="tiny" style="margin-top: 4px">{{ reward.name || `#${reward.id}` }}</div>
              </router-link>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 波次与部位 -->
    <section v-for="wave in detail?.waves || []" :key="wave.index" class="panel">
      <div class="panel-title">
        <h2>第 {{ wave.index }} 波</h2>
        <span class="tiny faint">敌人队伍 ID {{ wave.enemyPartyId }}</span>
      </div>

      <div v-if="wave.parts.length" class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>部位</th>
              <th>名称</th>
              <th>属性</th>
              <th class="num">HP</th>
              <th class="num">HP 倍率</th>
              <th class="num">ATK</th>
              <th class="num">INT</th>
              <th class="num">MND</th>
              <th class="num">DEF</th>
              <th class="num">MDEF</th>
              <th class="num">减伤</th>
              <th>属性减伤 火/冰/风/光/暗</th>
              <th class="num">本体</th>
              <th>体型</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="part in wave.parts" :key="part.slot">
              <td>敵{{ part.slot }}</td>
              <td>{{ part.name || `#${part.enemyId}` }}</td>
              <td>
                <span
                  v-if="part.attr && attrLabel(part.attr, ATTR_LABELS)"
                  class="badge"
                  :style="{ background: attrColor(part.attr), color: '#12141c' }"
                >{{ attrLabel(part.attr, ATTR_LABELS) }}</span>
                <span v-else class="faint">—</span>
              </td>
              <td class="num">{{ formatNumber(part.hp) }}</td>
              <td class="num">{{ part.hpRate ? `${part.hpRate}%` : '100%' }}</td>
              <td class="num">{{ formatNumber(part.atk) }}</td>
              <td class="num">{{ formatNumber(part.int) }}</td>
              <td class="num">{{ formatNumber(part.mnd) }}</td>
              <td class="num">{{ formatNumber(part.def) }}</td>
              <td class="num">{{ formatNumber(part.mdef) }}</td>
              <td class="num">{{ part.dmgCut || 0 }}</td>
              <td class="tiny faint">
                {{ (part.dmgCutAttr || []).some((v) => v) ? (part.dmgCutAttr || []).join(' / ') : '—' }}
              </td>
              <td class="num">{{ part.parent === 0 ? '本体' : `部位${part.parent}` }}</td>
              <td>{{ part.size || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="muted small">该波次没有部位数据。</div>

      <!-- 行动轴 -->
      <div v-if="hasOrderData(wave.order)" style="margin-top: 16px">
        <h3>行动轴</h3>
        <div class="row small" style="gap: 16px">
          <span v-if="wave.order.partyCondition && wave.order.partyCondition !== 'NULL'">
            触发前提：{{ PARTY_CONDITION[wave.order.partyCondition] || wave.order.partyCondition }}
          </span>
          <span v-if="wave.order.hpMin || wave.order.hpMax">
            HP 条件：{{ wave.order.hpMin }}% ~ {{ wave.order.hpMax }}%
          </span>
          <span v-if="wave.order.bodyHpMin || wave.order.bodyHpMax">
            本体 HP 条件：{{ wave.order.bodyHpMin }}% ~ {{ wave.order.bodyHpMax }}%
          </span>
          <span v-if="wave.order.loopStart">循环自第 {{ wave.order.loopStart }} 回合起</span>
          <span v-if="wave.order.trigger && wave.order.trigger !== 'NULL'">
            条件触发：{{ TRIGGER_LABEL[wave.order.trigger] || wave.order.trigger }}
          </span>
        </div>

        <div class="table-wrap" style="margin-top: 10px">
          <table class="data">
            <thead>
              <tr>
                <th>回合</th>
                <th class="num">行动序号</th>
                <th>阶段</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in orderTurns(wave.order)" :key="`${row.loop}-${row.turn}`">
                <td>第 {{ row.turn }} 回合</td>
                <td class="num">{{ row.action }}</td>
                <td class="tiny faint">{{ row.loop ? '循环阶段' : '开场阶段' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="tiny faint" style="margin-top: 6px">
          行动序号对应敌方技能表中的行动条目；客户端按该序号播放对应行动。
        </div>
      </div>
    </section>

    <!-- 掉落 -->
    <section class="panel">
      <div class="panel-title"><h2>奖励与掉落</h2></div>

      <h3>结算奖励</h3>
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>奖励</th>
              <th>类型</th>
              <th class="num">数量</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(reward, index) in detail?.resultRewards || []" :key="`r${index}`">
              <td>
                <router-link v-if="rewardCard(reward)" :to="`/card/${rewardCard(reward).id}`">
                  {{ rewardLabel(reward) }}
                </router-link>
                <span v-else>{{ rewardLabel(reward) }}</span>
              </td>
              <td class="tiny faint">type {{ reward.type }}</td>
              <td class="num">{{ formatNumber(reward.num) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!(detail?.resultRewards || []).length" class="muted small">无记录。</div>

      <h3 style="margin-top: 18px">首次通关奖励</h3>
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>奖励</th>
              <th>类型</th>
              <th class="num">数量</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(reward, index) in detail?.firstClearRewards || []" :key="`f${index}`">
              <td>
                <router-link v-if="rewardCard(reward)" :to="`/card/${rewardCard(reward).id}`">
                  {{ rewardLabel(reward) }}
                </router-link>
                <span v-else>{{ rewardLabel(reward) }}</span>
              </td>
              <td class="tiny faint">type {{ reward.type }}</td>
              <td class="num">{{ formatNumber(reward.num) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!(detail?.firstClearRewards || []).length" class="muted small">无记录。</div>

      <template v-if="(detail?.enemyDrops || []).length">
        <h3 style="margin-top: 18px">部位掉落</h3>
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th class="num">波次</th>
                <th class="num">部位</th>
                <th>掉落</th>
                <th class="num">概率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(drop, index) in detail.enemyDrops" :key="`d${index}`">
                <td class="num">{{ (drop.battle_index ?? 0) + 1 }}</td>
                <td class="num">敵{{ (drop.enemy_index ?? 0) + 1 }}</td>
                <td>
                  <router-link v-if="rewardCard(drop.reward)" :to="`/card/${rewardCard(drop.reward).id}`">
                    {{ rewardLabel(drop.reward) }}
                  </router-link>
                  <span v-else>{{ rewardLabel(drop.reward) }} ×{{ drop.reward?.num ?? 1 }}</span>
                </td>
                <td class="num">
                  {{ drop.chance_per_million ? `${(drop.chance_per_million / 10000).toFixed(2)}%` : '必掉' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <div v-if="detail?.recommend?.name" style="margin-top: 18px">
        <h3>推荐编成</h3>
        <div class="small muted">{{ detail.recommend.name }}</div>
      </div>
    </section>
  </div>
</template>
