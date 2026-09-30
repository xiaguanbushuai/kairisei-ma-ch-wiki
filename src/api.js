/**
 * 数据访问层：按需加载 public/data 下的 JSON 并缓存。
 * 大文件（卡牌、Boss 详情）只在真正用到时拉取。
 */
const cache = new Map()

function load(name) {
  if (!cache.has(name)) {
    cache.set(
      name,
      fetch(`${import.meta.env.BASE_URL}data/${name}`).then((response) => {
        if (!response.ok) throw new Error(`加载 ${name} 失败: ${response.status}`)
        return response.json()
      }),
    )
  }
  return cache.get(name)
}

export const getMeta = () => load('meta.json')
export const getCards = () => load('cards.json')
export const getSkills = () => load('skills.json')
export const getEvolutions = () => load('evolutions.json')
export const getItems = () => load('items.json')
export const getExpTables = () => load('exp_tables.json')
export const getBossIndex = () => load('boss_index.json')
export const getBossDetail = () => load('boss_detail.json')
export const getEnemySkills = () => load('enemy_skills.json')
export const getKeywords = () => load('keywords.json')

/** 卡面图地址。pictId 为 8 位数字。 */
export function cardImage(pictId) {
  if (!pictId) return ''
  return `/cardimg/chr51/chr51_${String(pictId).padStart(8, '0')}.png`
}

/** 缩略图地址（列表页用，体积小）。 */
export function cardThumb(pictId) {
  if (!pictId) return ''
  return `/cardimg/thumb/chr51/chr51_${String(pictId).padStart(8, '0')}.png`
}

export const ATTR_COLOR = {
  FIRE: '#e0533d',
  ICE: '#3d9ae0',
  WIND: '#3dbd7a',
  LIGHT: '#d9b23d',
  DARK: '#9b5fe0',
}

export const RARITY_COLOR = {
  NORMAL: '#8d93a6',
  HIGHNORMAL: '#7fa86a',
  RARE: '#4a9ad9',
  SUPERRARE: '#a76fd9',
  ULTRARARE: '#d9a441',
  EXRARE: '#4fc7c7',
  MILLIONRARE: '#e2618f',
  LEGEND: '#e0533d',
}

/**
 * rarityLabel 的颜色。客户端的 レアリティ 枚举颗粒度太粗
 * （MR / MR+ / MR++ 同为 MILLIONRARE，MMR 与 EX 同为 EXRARE），
 * 展示层统一按 rarityLabel 取值，同一枚举内用同色系递进拉开层次。
 */
export const RARITY_LABEL_COLOR = {
  N: '#8d93a6',
  HN: '#7fa86a',
  R: '#4a9ad9',
  SR: '#a76fd9',
  UR: '#d9a441',
  EX: '#4fc7c7',
  MR: '#c96a94',
  'MR+': '#e2618f',
  'MR++': '#f4518c',
  MMR: '#ff3d7f',
  传说: '#e0533d',
}

/** rarityLabel 的兜底排序，与 ETL 的 RARITY_LABEL_ORDER 保持同步；优先用 meta.enums.rarityLabelOrder。 */
export const RARITY_LABEL_ORDER = {
  N: 0, HN: 1, R: 2, SR: 3, UR: 4,
  EX: 5, MR: 6, 'MR+': 7, 'MR++': 8, MMR: 9, '传说': 10,
}

/** 旧链接里的 rarity=MILLIONRARE 这类枚举写法 → 展开成该枚举覆盖的全部标签。 */
export const LEGACY_RARITY_LABELS = {
  NORMAL: ['N'],
  HIGHNORMAL: ['HN'],
  RARE: ['R'],
  SUPERRARE: ['SR'],
  ULTRARARE: ['UR'],
  EXRARE: ['EX', 'MMR'],
  MILLIONRARE: ['MR', 'MR+', 'MR++'],
  LEGEND: ['传说'],
}

/** 一张卡的展示用稀有度标签。 */
export function rarityLabelOf(card, enums = {}) {
  return card.rarityLabel || enums.rarity?.[card.rarity] || card.rarity || ''
}

/** 标签对应的颜色。 */
export function rarityLabelColor(label) {
  return RARITY_LABEL_COLOR[label] || '#888'
}

/** 把 URL 里的稀有度参数（标签或旧枚举）统一解析成标签数组。 */
export function parseRarityParam(value) {
  return String(value)
    .split(',')
    // URLSearchParams 会把 '+' 解成空格，MR+ / MR++ 需要还原
    .map((item) => item.replace(/ /g, '+').trim())
    .filter(Boolean)
    .flatMap((item) => LEGACY_RARITY_LABELS[item] || [item])
}

export const REWARD_TYPE_LABEL = {
  0: '金币 / 经验',
  4: '大硬币',
  6: '道具',
  8: '素材',
  10: '水晶',
  12: '召唤石',
  13: '卡牌',
  15: '道具',
  19: '其他',
}

export function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '-'
  return Number(value).toLocaleString('zh-CN')
}

/**
 * 技能效果值：ETL 按官方「機能」模型输出的 valueSlots = { "1": ["val", a, b, c], "11": ["pct", a, b, c] }。
 * 键就是技能说明里的 {N} 编号：N = 機能序号(0-based) × 10 + 该機能的显示值序号(1-based)，
 * 機能行取自 skill_player.csv 的「機能ID」列所指技能（skill_role_player → skill_role 回落）。
 * 数值 = round((a + b × 技能等级) / c)，只随技能等级变化，与 ATK / INT 无关。
 * 未被 ETL 验证的效果类型不会出现在 valueSlots 里，前端按「暂无法计算」灰显（宁可留白也不猜）。
 */
export function slotAt(skill, token, level) {
  const slot = skill?.valueSlots?.[String(token)]
  if (!Array.isArray(slot) || slot.length !== 4) return null
  const [, a, b, c] = slot
  if (!c) return null
  return Math.round((a + b * (level || 0)) / c)
}

/** 该槽位是百分比（'pct'，随自身当前 HP 变化）还是固定数值（'val'）。 */
export function slotKind(skill, token) {
  const slot = skill?.valueSlots?.[String(token)]
  return Array.isArray(slot) ? slot[0] : ''
}

/** 部分技能是多属性组合（如 ICE_LIGHT），统一显示为「冰/光」。 */
export function attrLabel(key, map = {}) {
  if (!key) return ''
  return key
    .split('_')
    .map((part) => map[part] || part)
    .filter(Boolean)
    .join('/')
}

/**
 * 属性展示底色：
 * 单属性返回纯色；多属性（如 ICE_LIGHT）返回斜向拼色渐变，
 * 供徽章背景使用，与「冰/光」文字一一对应。
 */
export function attrColor(key, colors = ATTR_COLOR) {
  if (!key) return ''
  const parts = key.split('_').filter((part) => colors[part])
  if (!parts.length) return '#888'
  if (parts.length === 1) return colors[parts[0]]
  const step = 100 / parts.length
  const stops = parts
    .map((part, i) => `${colors[part]} ${(i * step).toFixed(2)}% ${((i + 1) * step).toFixed(2)}%`)
    .join(', ')
  return `linear-gradient(135deg, ${stops})`
}

/**
 * 按「同カードID」把卡牌收拢成同卡族。
 * 同一张卡在客户端里会按进化阶段/稀有度各占一条记录
 * （如 HN 骑士 → R 愤怒之骑士 → SR 暴怒之骑士 → UR 激情之炎涡），
 * 统计数量时应当算作一张。返回 Map<familyId, card[]>。
 */
export function groupFamilies(cards) {
  const families = new Map()
  for (const card of cards) {
    const key = card.sameId || card.id
    if (!families.has(key)) families.set(key, [])
    families.get(key).push(card)
  }
  return families
}

/**
 * 同族代表卡：阶位最高 → 等级上限最高 → ID 最小。
 * 阶位必须按 rarityLabel 比，不能按客户端枚举：枚举口径下 MR++ 与 MR 并列
 * （同为 MILLIONRARE），MMR 反而低于 MR（EXRARE），会把已因子觉醒的族误判成 MR 形态。
 */
export function pickRepresentative(members, labelOrder = RARITY_LABEL_ORDER) {
  const rank = (card) => labelOrder[rarityLabelOf(card)] ?? -1
  return members.reduce((best, card) => {
    if (!best) return card
    const diff = rank(card) - rank(best)
    if (diff !== 0) return diff > 0 ? card : best
    const levelDiff = (card.levelMax || 0) - (best.levelMax || 0)
    if (levelDiff !== 0) return levelDiff > 0 ? card : best
    return card.id < best.id ? card : best
  }, null)
}
