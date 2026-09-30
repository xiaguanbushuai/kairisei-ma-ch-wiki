/**
 * 技能文本关键词高亮。
 *
 * 词典来自 ETL 生成的 data/keywords.json：每个术语带若干文本别名
 * （中文为主、保留日文原文兼容）与筛选方式（结构化字段或全文检索）。
 * 分词用「最长优先」的正则一次扫描完成，结果按文本缓存避免重复切分。
 */
import { getKeywords } from './api.js'

let matcherPromise = null

/** 懒加载并构建分词器（整个会话只构建一次）。 */
export function getMatcher() {
  if (!matcherPromise) {
    matcherPromise = getKeywords().then((data) => buildMatcher(data))
  }
  return matcherPromise
}

export function buildMatcher(data) {
  const terms = data?.terms || []
  const aliasMap = new Map()
  const aliases = []
  for (const term of terms) {
    for (const alias of term.aliases || []) {
      if (aliasMap.has(alias)) continue
      aliasMap.set(alias, term)
      aliases.push(alias)
    }
  }
  // 长词在前，保证「己方全体」不会被「全体」抢先命中
  aliases.sort((a, b) => b.length - a.length || a.localeCompare(b))
  const pattern = aliases
    .map((alias) => alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')
  return {
    terms,
    groups: data?.groups || [],
    aliasMap,
    regex: pattern ? new RegExp(pattern, 'g') : null,
  }
}

const tokenCache = new Map()

/** 把文本切成 [{ text, term, alias }] 片段；term/alias 仅在命中关键词时存在。 */
export function tokenize(text, matcher) {
  const source = (text || '').replace(/\u3000/g, ' ').trim()
  if (!source) return []
  if (!matcher?.regex) return [{ text: source }]

  const cached = tokenCache.get(source)
  if (cached) return cached

  const regex = new RegExp(matcher.regex.source, 'g')
  const parts = []
  let last = 0
  let match
  while ((match = regex.exec(source)) !== null) {
    if (match.index > last) parts.push({ text: source.slice(last, match.index) })
    parts.push({ text: match[0], term: matcher.aliasMap.get(match[0]), alias: match[0] })
    last = match.index + match[0].length
    if (match[0].length === 0) regex.lastIndex += 1
  }
  if (last < source.length) parts.push({ text: source.slice(last) })

  if (tokenCache.size > 20000) tokenCache.clear()
  tokenCache.set(source, parts)
  return parts
}

/** 关键词 → 技能索引页的筛选链接。 */
export function keywordLink(term, alias) {
  const filter = term?.filter || {}
  const params = new URLSearchParams()
  if (filter.type === 'target') params.set('target', filter.value)
  else if (filter.type === 'attr') params.set('attr', filter.value)
  else if (filter.type === 'phys') params.set('phys', filter.value)
  else params.set('q', alias || term?.label || '')
  return `/skills?${params.toString()}`
}
