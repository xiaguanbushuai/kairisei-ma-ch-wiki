<script setup>
/**
 * 技能效果文本渲染：
 * 1. 按 <br> 拆成多行（还原游戏里多段效果的排版）；
 * 2. 把 ETL 词典里的术语（敌全体 / 火属性 / 中毒 …）渲染成可点击链接，
 *    点击跳到技能索引页并自动套用对应筛选；
 * 3. 文本里所有承载数值的占位符（{1} / {11} / {52} …）逐个查 ETL 输出的
 *    valueSlots 表算出实际数值（金色高亮）——不再只替换第一个；
 * 4. 查不到槽位的占位符（ETL 尚未验证的效果类型）灰显为「?」，悬停提示
 *    「效果值暂无法计算」，宁可留白也不给错数。
 *
 * 槽位 kind：val = 随等级成长（金色数值）、pct = 随自身当前 HP 变化的百分比、
 *            flat = 固定值（如暴击率/圣剑解放加成，与等级无关）。
 * 条件分岐类技能（如「满足1项条件变更为提升{51}%暴击率」）的文本本身就是游戏卡面
 * 原文，ETL 跟到兄弟变体技能取值后，这里按 <br> 逐行平铺即可还原游戏面板。
 */
import { computed, onMounted, ref } from 'vue'
import { getMatcher, keywordLink, tokenize } from '../keywords.js'

const props = defineProps({
  text: { type: String, default: '' },
  /** ETL 输出的效果值槽位表：{ "<token>": ["val" | "pct", a, b, c] } */
  slots: { type: Object, default: () => ({}) },
  /** 数值对应的技能等级，用于计算与鼠标悬停提示 */
  level: { type: Number, default: null },
  /** 词典尚未加载完成时是否渲染纯文本（默认等待，避免闪烁） */
  eager: { type: Boolean, default: false },
})

const matcher = ref(null)
onMounted(async () => {
  matcher.value = await getMatcher()
})

const TOKEN_RE = /\{(\d+)\}/g

function slotOf(token) {
  const slot = props.slots?.[token]
  return Array.isArray(slot) && slot.length === 4 ? slot : null
}

function valueOf(slot) {
  const [, a, b, c] = slot
  if (!c) return null
  return Math.round((a + b * (props.level || 0)) / c)
}

// 全文本：每个 {N} 都查一次槽位表
const lines = computed(() =>
  (props.text || '')
    .split(/<br\s*\/?>/i)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const segments = []
      let cursor = 0
      let match
      TOKEN_RE.lastIndex = 0
      while ((match = TOKEN_RE.exec(line)) !== null) {
        if (match.index > cursor) segments.push({ text: line.slice(cursor, match.index) })
        const token = match[1]
        const slot = slotOf(token)
        if (slot) segments.push({ token, kind: slot[0], value: valueOf(slot) })
        else segments.push({ token, unknown: true })
        cursor = match.index + match[0].length
      }
      if (cursor < line.length) segments.push({ text: line.slice(cursor) })
      return segments.length ? segments : [{ text: line }]
    }),
)

function partsOf(line) {
  if (!matcher.value) return props.eager ? [{ text: line }] : null
  return tokenize(line, matcher.value)
}
</script>

<template>
  <span v-if="matcher" class="skill-text">
    <span v-for="(line, lineIndex) in lines" :key="lineIndex" class="kw-line">
      <template v-for="(seg, segIndex) in line" :key="segIndex">
        <template v-if="seg.text !== undefined">
          <template v-for="(part, index) in partsOf(seg.text)" :key="`t-${index}`">
            <router-link
              v-if="part.term"
              class="kw"
              :to="keywordLink(part.term, part.alias)"
              :title="`筛选：${part.term.label}`"
            >{{ part.text }}</router-link>
            <template v-else>{{ part.text }}</template>
          </template>
        </template>
        <span
          v-else-if="seg.unknown"
          class="eff-num eff-unknown"
          :title="`效果值 {${seg.token}} 暂无法计算（该效果类型尚未验证）`"
        >?</span>
        <span
          v-else-if="seg.kind === 'pct'"
          class="eff-num"
          :title="`随自身当前 HP 变化的百分比${level ? `（Lv.${level} 面板值）` : ''}`"
        >{{ seg.value }}</span>
        <span
          v-else-if="seg.kind === 'flat'"
          class="eff-num"
          title="固定值（不随技能等级变化）"
        >{{ seg.value }}</span>
        <span v-else class="eff-num" :title="level ? `Lv.${level} 时的效果值` : null">{{ seg.value }}</span>
      </template>
    </span>
  </span>
  <span v-else-if="eager">{{ text }}</span>
</template>
