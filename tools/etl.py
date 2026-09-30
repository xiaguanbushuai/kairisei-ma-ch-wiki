# -*- coding: utf-8 -*-
"""乖离性百万亚瑟王 国服资料站 ETL。

把服务端资源集里的官方主表（CSV）与归一化主数据（JSON）转换成前端可用的
结构化 JSON，输出到 public/data/ 目录。

数据源目录可用环境变量 KAIRI_SRC 覆盖，默认见下方 DEFAULT_SRC。

用法:
    python tools/etl.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SRC = r"D:\新建文件夹 (2)\kairisei-ma-cn602-server\resource-set"
SRC = os.environ.get("KAIRI_SRC", DEFAULT_SRC)
CONTROL = os.path.join(SRC, "_local", "control", "server")
CARD_MASTER = os.path.join(CONTROL, "cn602-card-master")
BATTLE_MASTER = os.path.join(CONTROL, "cn602-battle-master")
IMAGE_ROOT = os.path.join(SRC, "resources", "image")

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PROJECT, "public", "data")

# ---------------------------------------------------------------- 枚举映射

# 国服玩家习惯简称：N / HN / R / SR / UR / MR（+ MR+ / MR++ / MMR）
RARITY = {
    "NORMAL": "N",
    "HIGHNORMAL": "HN",
    "RARE": "R",
    "SUPERRARE": "SR",
    "ULTRARARE": "UR",
    "EXRARE": "EX",
    "MILLIONRARE": "MR",
    "LEGEND": "传说",
}
RARITY_ORDER = {key: idx for idx, key in enumerate(RARITY)}


def rarity_label(rarity: str, level_max: int) -> str:
    """按国服显示习惯生成稀有度徽标：MR+ / MR++ / MMR。"""
    base = RARITY.get(rarity, rarity)
    if rarity == "MILLIONRARE":
        if level_max == 65:
            return "MR+"
        if level_max == 70:
            return "MR++"
    elif rarity == "EXRARE" and level_max == 80:
        # 因子覚醒（★7）形态，客户端显示为 MMILLION RARE
        return "MMR"
    return base


# rarityLabel 的权威排序（低 → 高）。
# 客户端的 レアリティ 枚举颗粒度太粗（MR / MR+ / MR++ 共用 MILLIONRARE，
# MMR 与 EX 共用 EXRARE），所以筛选、排序、统计一律以 rarityLabel 为准，
# 这张表是唯一事实源，前端不得自行拼接。
RARITY_LABEL_ORDER = [
    "N",
    "HN",
    "R",
    "SR",
    "UR",
    "EX",
    "MR",
    "MR+",
    "MR++",
    "MMR",
    "传说",
]

ATTR = {
    "FIRE": "火",
    "ICE": "冰",
    "WIND": "风",
    "LIGHT": "光",
    "DARK": "暗",
    "NULL": "",
}


# ---------------------------------------------------------------- 卡牌来源

# 来源分档顺序（即筛选 chip 顺序）。判定规则按 _SOURCE_RULES 从上到下，
# 更特异的途径（BOSS币）先于宽松的（扭蛋 / 副本）。
#
# ⚠️ card.csv 的「卡牌出处」(col94) 混了两个维度：
#   1) 入手途径：水晶扭蛋 / 活动副本 / BOSS币扭蛋 / 特典卡 …
#   2) 成长方式：进化 / 乖离进化 / 因子覚醒 / 限界突破（同族内进阶形态才有）
# 前者答「这张卡从哪来」，后者答「这个形态怎么来的」。二者已拆成两个字段：
#   source  = 入手途径，取同卡族内稀有度最低的可判形态（族的「根」）
#   growth  = 成长方式，取本形态自身的记录
# 旧版把两者塞进一个档，导致按「扭蛋」筛选时只命中初始形态，
# MMR/MR++ 等进阶形态全被漏掉。
SOURCE_ORDER = [
    "扭蛋",
    "副本掉落",
    "BOSS币",
    "特典 / 活动",
    "日服卡牌",
    "其他 / 未标注",
]

# 成长方式档（本形态自身是怎么来的）
GROWTH_ORDER = [
    "直接获得",
    "进化",
    "乖离进化",
    "因子觉醒",
    "限界突破",
    "其他",
]

_KANA_RE = re.compile(r"[ぁ-んァ-ヶ]")
# 卡名里的画师署名（如 -画师:しきみ-）允许保留日文，不作为“未翻译”的依据
_ARTIST_RE = re.compile(r"-画师[:：][^-]*-")
_SOURCE_RULES = [
    ("BOSS币", ("boss币",)),
    ("扭蛋", ("扭蛋", "抽卡")),
    ("副本掉落", ("副本",)),
    ("特典 / 活动", ("特典", "活动", "pvp", "任务", "礼包", "首充")),
]
_GROWTH_RULES = [
    ("因子觉醒", ("因子",)),
    ("限界突破", ("限界突破",)),
    ("乖离进化", ("乖离",)),
    ("进化", ("进化",)),
]
# 用于判定一条 col94 原文是否属于「入手途径」而非「成长方式」
_CHANNEL_KEYS = ("扭蛋", "抽卡", "副本", "boss币", "特典", "活动", "pvp", "任务", "礼包", "首充")


def is_channel(acquire: str) -> bool:
    """col94 原文是否为「入手途径」（而非进化/觉醒/突破等成长方式）。"""
    a = (acquire or "").strip()
    if not a or "未進化" in a:
        return False
    low = a.lower()
    return any(key in low for key in _CHANNEL_KEYS)


def card_growth(acquire: str, card_id: int = 0, evo_kind: dict[str, str] | None = None) -> str:
    """把 col94 原文归入「成长方式」档。

    col94 明确写着 进化 / 乖离进化 / 因子覚醒 / 限界突破 的直接采用；
    写着入手途径（如「水晶扭蛋」）或为空时，再看 card_evolution.csv 里
    本卡是否作为 進化後ID 出现 —— 有则按進化タイプ反推，无则「直接获得」。
    タイプ映射（已与 col94 交叉验证）：NORMAL=进化、GOD=乖离进化、
    LIMIT=限界突破（因子覚醒在表里同样是 LIMIT，无法区分）、KNIGHTS=圆桌骑士专属进化。
    """
    a = (acquire or "").strip()
    if a and "未進化" not in a:
        low = a.lower()
        for label, keys in _GROWTH_RULES:
            if any(key in low for key in keys):
                return label
        return "直接获得" if is_channel(a) else "其他"
    kind = (evo_kind or {}).get(str(card_id), "")
    if kind == "NORMAL":
        return "进化"
    if kind == "GOD":
        return "乖离进化"
    if kind == "LIMIT":
        return "限界突破"
    if kind == "KNIGHTS":
        return "其他"
    return "直接获得"


def card_source(acquire: str, title: str, main_name: str) -> str:
    """把 acquire 原文归入「入手途径」分档。

    「日服卡牌」= 名字（剔除画师署名）仍含日文假名的未翻译先行卡，
    实测 2416 条 acquire 全部为空，与其它档天然互斥。
    """
    if _KANA_RE.search(_ARTIST_RE.sub("", f"{title} {main_name}")):
        return "日服卡牌"
    a = (acquire or "").strip()
    if not a or "未進化" in a:
        return "其他 / 未标注"
    low = a.lower()
    for label, keys in _SOURCE_RULES:
        if any(key in low for key in keys):
            return label
    return "其他 / 未标注"

def load_source_overrides() -> dict[str, str]:
    """读入手工来源覆盖表（tools/source_override.json）。

    键可以是卡牌 ID，也可以是同卡族 ID（sameId，一族共用一条）。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "source_override.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    overrides = {str(k): str(v).strip() for k, v in data.items() if not str(k).startswith("_")}
    log(f"  来源覆盖表 {len(overrides)} 条")
    return overrides


JOB = {
    "MERCENARY": "佣兵",
    "MILLIONAIRE": "富豪",
    "THIEF": "盗贼",
    "SINGER": "歌姬",
    "NULL": "",
}

SKILL_KIND = {
    "ATTACK": "攻击",
    "SORCERY": "魔法",
    "RECOVERY": "回复",
    "SUPPORT": "支援",
    "DEFENSE": "防御",
    "JAMMING": "妨害",
}

SKILL_TARGET = {
    "ENEMY_ONE": "敌单体",
    "ENEMY_ALL": "敌全体",
    "USER_ONE": "己方单体",
    "USER_ALL": "己方全体",
    "SELF": "自身",
    "ENEMY_RANDOM": "敌随机",
}

SKILL_PHYS_MAGIC = {
    "PHYSICS": "物理",
    "MAGIC": "魔法",
    "ALL": "物理+魔法",
}

REWARD_TYPE = {
    0: "金币/经验",
    4: "大硬币",
    6: "道具",
    8: "素材",
    10: "水晶",
    12: "召唤石",
    13: "卡牌",
    15: "道具",
    19: "其他",
}


# ---------------------------------------------------------------- 关键词索引
# 技能描述里高频出现的术语 → 技能索引页可点击筛选项。
# filter.type:
#   target / attr / phys -> 精确匹配技能结构化字段
#   text                 -> 关键词全文检索（点谁搜谁，命中别名原文）
# 别名同时收录日文原文，兼容敌方技能与旧版文案。
KEYWORD_GROUPS = [
    ("target", "目标"),
    ("attr", "属性"),
    ("phys", "伤害类型"),
    ("stat", "能力增减"),
    ("status", "状态效果"),
    ("mechanic", "机制"),
]

KEYWORD_TERMS = [
    # (分组, 展示名, 筛选条件, [文本别名...])
    ("target", "敌单体", {"type": "target", "value": "ENEMY_ONE"}, ["敌单体", "敵単体"]),
    ("target", "敌全体", {"type": "target", "value": "ENEMY_ALL"}, ["敌全体", "敵全体"]),
    ("target", "己方单体", {"type": "target", "value": "USER_ONE"}, ["己方单体", "己方1人", "味方1人"]),
    ("target", "己方全体", {"type": "target", "value": "USER_ALL"}, ["己方全体", "己方全员", "味方全体"]),
    ("target", "自身", {"type": "target", "value": "SELF"}, ["自身", "自分", "自己"]),
    ("target", "敌随机", {"type": "target", "value": "ENEMY_RANDOM"}, ["敌随机", "ランダム"]),
    ("attr", "火属性", {"type": "attr", "value": "FIRE"}, ["火属性", "火ダメージ"]),
    ("attr", "冰属性", {"type": "attr", "value": "ICE"}, ["冰属性", "氷ダメージ"]),
    ("attr", "风属性", {"type": "attr", "value": "WIND"}, ["风属性", "風ダメージ"]),
    ("attr", "光属性", {"type": "attr", "value": "LIGHT"}, ["光属性", "光ダメージ"]),
    ("attr", "暗属性", {"type": "attr", "value": "DARK"}, ["暗属性", "闇ダメージ"]),
    ("phys", "物理伤害", {"type": "phys", "value": "PHYSICS"}, ["物理伤害", "物理ダメージ", "物理ダメ"]),
    ("phys", "魔法伤害", {"type": "phys", "value": "MAGIC"}, ["魔法伤害", "魔法ダメージ", "魔法ダメ"]),
    ("stat", "物理攻击", {"type": "text", "value": ""}, ["物理攻击", "物理攻撃"]),
    ("stat", "魔法攻击", {"type": "text", "value": ""}, ["魔法攻击", "魔法攻撃"]),
    ("stat", "物理防御", {"type": "text", "value": ""}, ["物理防御", "物理防御力"]),
    ("stat", "魔法防御", {"type": "text", "value": ""}, ["魔法防御", "魔法防御力"]),
    ("stat", "全防御", {"type": "text", "value": ""}, ["全防御"]),
    ("stat", "全伤害", {"type": "text", "value": ""}, ["全伤害", "全ダメージ"]),
    ("stat", "回复量", {"type": "text", "value": ""}, ["回复量", "回復量"]),
    ("stat", "暴击", {"type": "text", "value": ""}, ["暴击", "クリティカル"]),
    ("status", "中毒", {"type": "text", "value": ""}, ["中毒", "毒"]),
    ("status", "麻痹", {"type": "text", "value": ""}, ["麻痹", "麻痺"]),
    ("status", "冻结", {"type": "text", "value": ""}, ["冻结", "凍結"]),
    ("status", "混乱", {"type": "text", "value": ""}, ["混乱"]),
    ("status", "睡眠", {"type": "text", "value": ""}, ["睡眠"]),
    ("status", "诅咒", {"type": "text", "value": ""}, ["诅咒", "呪い"]),
    ("status", "眩晕", {"type": "text", "value": ""}, ["眩晕", "気絶"]),
    ("status", "沉默", {"type": "text", "value": ""}, ["沉默", "沈黙"]),
    ("status", "束缚", {"type": "text", "value": ""}, ["束缚", "束縛"]),
    ("status", "恐怖", {"type": "text", "value": ""}, ["恐怖"]),
    ("status", "狂化", {"type": "text", "value": ""}, ["狂化"]),
    ("status", "感电", {"type": "text", "value": ""}, ["感电", "帯電"]),
    ("status", "无敌", {"type": "text", "value": ""}, ["无敌", "無敵"]),
    ("status", "护盾", {"type": "text", "value": ""}, ["护盾"]),
    ("status", "反击", {"type": "text", "value": ""}, ["反击", "反撃"]),
    ("status", "吸血", {"type": "text", "value": ""}, ["吸血", "吸収"]),
    ("status", "必中", {"type": "text", "value": ""}, ["必中"]),
    ("status", "即死", {"type": "text", "value": ""}, ["即死"]),
    ("status", "复活", {"type": "text", "value": ""}, ["复活", "復活"]),
    ("status", "解除", {"type": "text", "value": ""}, ["解除"]),
    ("status", "净化", {"type": "text", "value": ""}, ["净化"]),
    ("status", "反射", {"type": "text", "value": ""}, ["反射"]),
    ("status", "回复", {"type": "text", "value": ""}, ["回复", "回復"]),
    ("mechanic", "抽牌", {"type": "text", "value": ""}, ["抽牌", "抽卡", "ドロー"]),
    ("mechanic", "能量", {"type": "text", "value": ""}, ["能量", "コスト"]),
    ("mechanic", "连锁", {"type": "text", "value": ""}, ["连锁", "連携"]),
    ("mechanic", "每回合", {"type": "text", "value": ""}, ["每回合"]),
    ("mechanic", "上限", {"type": "text", "value": ""}, ["上限"]),
]


def build_keywords(skills: dict[str, dict]) -> dict:
    """扫描技能文本，统计每个术语的命中数，输出前端分词/筛选用的词典。"""
    skill_list = list(skills.values())
    haystacks = [f"{s.get('name', '')} {s.get('sub', '')} {s.get('desc', '')}" for s in skill_list]

    terms = []
    for group, label, flt, aliases in KEYWORD_TERMS:
        kind = flt["type"]
        if kind == "target":
            count = sum(1 for s in skill_list if s.get("target") == flt["value"])
        elif kind == "attr":
            value = flt["value"]
            count = sum(1 for s in skill_list if value in (s.get("attr") or "").split("_"))
        elif kind == "phys":
            count = sum(1 for s in skill_list if s.get("physMagic") in (flt["value"], "ALL"))
        else:
            count = sum(1 for hay in haystacks if any(alias in hay for alias in aliases))
        if count <= 0:
            continue
        terms.append({"label": label, "group": group, "filter": flt, "aliases": aliases, "count": count})

    order = {key: idx for idx, (key, _) in enumerate(KEYWORD_GROUPS)}
    terms.sort(key=lambda item: (order.get(item["group"], 99), -item["count"], item["label"]))
    log(f"  关键词 {len(terms)} 条（候选 {len(KEYWORD_TERMS)}）")
    return {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "groups": [{"key": key, "label": label} for key, label in KEYWORD_GROUPS],
        "terms": terms,
    }


def log(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------- 读取工具


def read_csv(name: str, folder: str) -> list[list[str]]:
    """读取主表，跳过以 # 开头的表头/分区行，返回数据行。"""
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        log(f"  ! 缺失 {name}")
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        raw = list(csv.reader(handle))
    rows = []
    for row in raw:
        if not row or not any((cell or "").strip() for cell in row):
            continue
        if (row[0] or "").strip().startswith("#"):
            continue
        rows.append(row)
    return rows


def read_json(name: str) -> dict:
    path = os.path.join(CONTROL, name)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def at(row: list[str], index: int) -> str:
    return (row[index] if index < len(row) else "") or ""


def num(value: str) -> int:
    value = (value or "").strip()
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u3000", " ")).strip()


def is_numeric(value: str) -> bool:
    return bool(re.fullmatch(r"\d+", (value or "").strip()))


def is_blank_desc(value: str) -> bool:
    """変体行（発動条件分岐行）的 desc 视为空：官方表里 6189 行是空串，
    另有 190 行把 desc 写成字面 "0"。这些行不是本体描述，但它们的「機能ID」([49])
    正是条件分岐变体所指的兄弟技能，必须参与变体编号。"""
    desc = text(value)
    return (not desc) or desc == "0"


# ---------------------------------------------------------------- 读入源数据


def build_exp_tables() -> dict[str, list[int]]:
    rows = read_csv("card_lvup_exp.csv", CARD_MASTER)
    tables: dict[str, list[int]] = {}
    for row in rows:
        table_id = at(row, 0)
        if not is_numeric(table_id):
            continue
        values = [num(cell) for cell in row[1:]]
        while values and values[-1] == 0:
            values.pop()
        tables[table_id] = values
    log(f"  经验表 {len(tables)} 张")
    return tables


# ============ 技能效果值：按「機能」槽位 + 官方显示列 ============
# 权威来源（详见 .workbuddy/memory/2026-09-29.md 第七轮）：
#   skill_player.csv        [4] スキル効果値表示パラメータ番号 = desc 里的 {N}
#                           [5] スキル効果値表示機能番号（1-based）、[7] スキル効果値表示タイプ
#   skill_role_player.csv   一行 = 一个「機能」；[8] 機能タイプ、[20..29] パラメータ1~10
#   skill_role.csv          同为「機能」表但整体少一列（機能1 从 col7 起）→ srp 缺失时回落
#   skill_role_param_rule.csv  機能タイプ → 各参数语义（VALUE / 枚举）
#
# desc 里的 {N} = 機能序号(0-based) × 10 + 该機能的显示值序号(1-based)。
# 校验：skill_player.csv [4] 的十位 == [5]-1，命中 20262/20368（99.5%）。
# 所有数值统一为 round((a + b × 技能等级) / c)，只随技能等级变化，与 ATK / INT 无关。
#
# 只对「游戏内实测 / CN 百科多卡交叉验证」过的機能タイプ出值，其余留空（前端灰显「暂无法计算」）。
# 不再用参数模式跨类型套公式——反例：REGENERATE_FIXED 按攻击类模式会把 ~1188 错算成个位数。
VALUE_TOKEN_RE = re.compile(r"\{(\d+)\}点")
PERCENT_TOKEN_RE = re.compile(r"\{(\d+)\}%")
TOKEN_RE = re.compile(r"\{(\d+)\}")
STAT_TOKENS = {"ATK", "INT", "DEF", "MDEF", "MND", "MAX_HP", "HP"}

# 已驗證：属性增减类（*_FIXED）—— パラメータ4=基数、パラメータ5=每级增量、除数恒 1000
#   实测 14500311 DEF_UP_FIXED (455000, 7000) → lv80 = 1015；CN 百科多张卡（3271 / 5451 / 5381）交叉验证
STAT_FIXED_TYPES = {
    "ATK_UP_FIXED", "DEF_UP_FIXED", "ATK_BREAK_FIXED", "GUARD_BREAK_FIXED", "PARAM_LIMIT_BREAK_FIXED",
    "ATK_UP_FIXED_ATTR_BONUS", "DEF_UP_FIXED_ATTR_BONUS",
    "ATK_UP_FIXED_SUPPORT", "DEF_UP_FIXED_SUPPORT",
    "ATK_UP_FIXED_PARAM_UNIQUE", "DEF_UP_FIXED_PARAM_UNIQUE",
}
# 已驗證：*_BY_SELF_PARAM —— 显示值1 = パラメータ4 ÷ 10（百分比）、显示值2 = パラメータ6 × 等级
#   实测 12508092 (40, 0, 36) → lv80 = 2880 点 / 4%
SELF_PARAM_TYPES = {
    "ATK_UP_BY_SELF_PARAM", "DEF_UP_BY_SELF_PARAM", "ATK_BREAK_BY_SELF_PARAM",
    "GUARD_BREAK_BY_SELF_PARAM", "PARAM_LIMIT_BREAK_BY_SELF_PARAM",
}
# 已驗證：攻击类 —— 显示值1 = パラメータ1 + パラメータ2 × 等级 ÷ 1000
#   ！！パラメータ3 是「威力倍率 ×1000」，不是除数：1011114792 的文本写着
#   「物理攻撃力300%の4回攻撃」而它的 p3 = 3000，直接印证。
#   交叉验证：技能里「祝福后」重述同一效果的 BLESS 行（无除法）与该行数值在
#   20 个 p3 ≠ 1000 的样本上完全一致，而按 ÷p3 读法 0 个一致（check_divisor.py）。
ATTACK_TYPES = {"ATTACK_AA", "ATTACK_AP", "ATTACK_PA", "ATTACK_PP"}
# 已驗證：回复类 —— 与攻击类同布局：(パラメータ1 × 1000 + パラメータ2 × 等级) ÷ パラメータ3
#   实测 10177067 感谢的祝歌 lv80：14305692 (4089, 57000, 1000) → (4089000 + 4560000) ÷ 1000 = 8649 ✓
#   （p4=参照属性如 MND，仅影响连携/公式外的部分，不动显示值）
HEAL_TYPES = {"HEAL_FIXED"}
# 已驗證：CRITICAL_UP —— 显示值1 = パラメータ2 ÷ 10（暴击率%）；パラメータ1 = 持续回合；パラメータ3 恒 0
#   实测 10180052 新春型薇薇：14404221 (2, 400, 0) → 40%；条件变体 (2,700,0) → 70% / (2,1000,0) → 100% ✓
#   属固定值（不随等级变化），故 kind = "flat"
CRITICAL_TYPES = {"CRITICAL_UP"}
# 已驗證：BURST_GAUGE_QUICK_UP —— 显示值1 = パラメータ1（圣剑解放加成%），直接读、不随等级变化
#   实测 10180052：14404221 (5, 0) → 5% ✓
BURST_GAUGE_TYPES = {"BURST_GAUGE_QUICK_UP"}
# 已驗證（用户游戏内实测，2026-09-30）：REGENERATE_FIXED —— 布局与攻击/回复类同构、整体后移 1 位
#   显示值1 = (パラメータ2 × 1000 + パラメータ3 × 等级) ÷ パラメータ4
#   实测 14200642 (3, 532, 9000, 1000) → lv1 = 541、lv80 = 1252 ✓（10157016 龙骑型艾菲·歌姬）
REGENERATE_FIXED_TYPES = {"REGENERATE_FIXED"}
# 已驗證：ATTR_DEF_UP / ATTR_DEF_DOWN（各属性抗性增减）
#   パラメータ1 = 持续回合、[4] = 基数、[5] = 每级增量、[6] = 属性；除数恒 1000
#   显示值序号为 2（与官方「表示パラメータ番号」= 2 一致，对应文本里的 {2}）
#   实测 12505142 (3, 0, 0, 997, 14000, FIRE) → lv1 = 1011、lv80 = 2117 ✓（10157008 龙骑型艾菲·富豪）
#   实测 13602861 (3, 0, 0, 1225, 81000, ICE) → lv1 = 1306、lv80 = 7705 ✓（10157028 外敌型塞莉艾）
ATTR_DEF_TYPES = {"ATTR_DEF_UP", "ATTR_DEF_DOWN"}
ATTR_KEYS = {"FIRE", "ICE", "WIND", "LIGHT", "DARK"}
# 已驗證：REFLECTION（反射所受伤害%）—— 显示值1 = (パラメータ2 + パラメータ3 × 等级) ÷ 100
#   游戏为整数除法（截断非四舍五入）：实测 12400252 (2, 15400, 770) → lv1 = 161、lv80 = 770 ✓（10154040）
#   （round(161.7) = 162 与游戏不符，故该槽位带 floor 标记）
REFLECTION_TYPES = {"REFLECTION"}
# 已驗證：COVERING（嘲讽减伤%）/ WEAKNESS（标记易伤%）—— 固定值 = パラメータ2 ÷ 10，不随等级
#   实测 12504722 (1, 500) → 50% ✓（10153008）；13602672 (3, 100) → 10% ✓，
#   同卡条件变体文本「变更为 30%」与该机能另一行吻合（10154060）
COVER_WEAK_TYPES = {"COVERING", "WEAKNESS"}
# 已驗證：ATK_OP_DRAIN（吸血%）—— 固定值 = パラメータ1，不随等级
#   实测 12101592 (50) → 50% ✓（10156008 新春型斯卡哈）
DRAIN_TYPES = {"ATK_OP_DRAIN"}
# 已驗證：ENCHANT（各属性追加伤害）—— 显示值1 = パラメータ2 + パラメータ5 × 技能等级（不经除法）
#   パラメータ1 = 持续回合、[2] = 基数、[3] = 恒 1000、[5] = 每级增量、[6] = 属性
#   实测 12400261 (1, 675, 1000, 0, 45, ICE) → lv1 = 720、lv80 = 4275 ✓（10155036 圣夜型乌莎哈）
#   实测 12505402 (2, 2210, 1000, 0, 113, ICE) → lv1 = 2323、lv80 = 11250 ✓（10159008 异界型尼禄）
#   仅接受 [3] == 1000 的行（880/884）；[3] = 1300 的 4 行量纲存疑，保持留空（宁缺勿错）
ENCHANT_TYPES = {"ENCHANT"}
# 已驗證：ATK_OP_PIERCING（无视 N% 物/魔防御）—— 固定值 = パラメータ1
#   实测 11106072 (70) → 70% ✓（10156056 戏雪型柯妮·佣兵）
ATK_PIERCING_TYPES = {"ATK_OP_PIERCING"}
# 已驗證：持续伤害族（毒/燃烧/冰冻/裂风/感电）—— 显示值2 = (パラメータ4 × 1000 + パラメータ5 × 等级) ÷ 1000
#   パラメータ1 = 回合、[2] = 100、[4] = 基数、[5] = 每级增量、[6] = 系数、[8] = 参照属性
#   实测 5 张卡全部一致：13604371/13604251/13604101/13604701 (2,100,0,200,4720,500) → lv1 = 204、lv80 = 577 ✓
#   （10173012 侵蚀型阿莱米拉 / 10172044 礼装型珀西瓦尔 / 10170048 / 10175064 / 10169052）
DOT_TYPES = {"POISON", "BURN", "FREEZE", "BLEED", "ELECTRIC"}
# 已驗證：BLESS（「祝福」发动后重述的强化效果）—— 显示值 7/8/9 = 基数 + 每级增量（不经除法）
#   三组 (基数, 每级增量) 相邻排列：[4][5] → 显示值7、[6][7] → 显示值8、[8][9] → 显示值9
#   实测 12507612 (4,0,1,4732,66) → 显示值7 lv1 = 4798、lv80 = 10012 ✓（10173060 侵蚀型雪莉柯特·富豪）
#   显示值8/9 无实测，由结构推定：14404092 的 8 = 基础 HEAL_FIXED 同值；
#   1011114792 的 9 : 8 = 155000:31000 = 5:1（「每张卡 +N，最多 5 张」的 5 倍关系）
BLESS_TYPES = {"BLESS"}
# 已驗證：TRANCE_GAUGE_VALUE_DOWN（灼热破坏%）—— 固定值 = パラメータ2，[1] 必须是 "TRANCE"
#   实测 1013608202 (TRANCE, 8) → 8% ✓（10256008 圣夜型佣兵亚瑟&蒂蕾妮娅）
TRANCE_TYPES = {"TRANCE_GAUGE_VALUE_DOWN"}
# 已驗證：ATK_OP_DRAIN_ALL（全队吸血%）—— 固定值 = パラメータ1
#   实测 11108802 (10) → 10% ✓（10170004 复制型斯卡哈·幼魔女）
DRAIN_ALL_TYPES = {"ATK_OP_DRAIN_ALL"}
# 已驗證：ATK_OP_REVENGE（按累计损血提升威力%）—— 固定值 = パラメータ1，[3] 必须是参照属性名
#   实测 11106092 (40, 0, MAX_HP, 50) → 40% ✓（10155092 异界型杏子&佣兵亚瑟）
REVENGE_TYPES = {"ATK_OP_REVENGE"}
# 已驗證：ATK_OP_DAMAGE_INCREASE（叠加当前血量的威力%）—— 显示值2 = パラメータ3 ÷ 10
#   实测 11107852 (0, 0, 200, 0, HP) → 20% ✓（10166073 异界型雷姆）
DAMAGE_INC_TYPES = {"ATK_OP_DAMAGE_INCREASE"}


def slot_rules(eff_type: str, params: list, raw: list) -> dict:
    """機能タイプ → {显示值序号: (kind, a, b, c)}；未验证类型返回空 dict（前端灰显）。"""
    p = params
    if eff_type in ATTACK_TYPES:
        if (p[0] or 0) > 0 and (p[2] or 0) > 1:
            return {1: ("val", p[0] * 1000, p[1] or 0, 1000)}
        return {}
    if eff_type in STAT_FIXED_TYPES:
        # 结构性校验：パラメータ2 必须是属性名、パラメータ3 必须为 1
        if raw[1] in STAT_TOKENS and (p[2] or 0) == 1 and ((p[3] or 0) > 0 or (p[4] or 0) > 0):
            return {1: ("val", p[3] or 0, p[4] or 0, 1000)}
        return {}
    if eff_type in SELF_PARAM_TYPES:
        out: dict = {}
        if raw[1] in STAT_TOKENS and raw[2] in STAT_TOKENS:
            if (p[3] or 0) > 0:
                out[1] = ("pct", p[3], p[4] or 0, 10)
            if (p[5] or 0) > 0:
                out[2] = ("val", 0, p[5], 1)
        return out
    if eff_type in HEAL_TYPES:
        if (p[0] or 0) > 0 and (p[2] or 0) > 1:
            return {1: ("val", p[0] * 1000, p[1] or 0, 1000)}
        return {}
    if eff_type in CRITICAL_TYPES:
        if (p[1] or 0) > 0:
            return {1: ("flat", p[1], 0, 10)}
        return {}
    if eff_type in BURST_GAUGE_TYPES:
        if (p[0] or 0) > 0:
            return {1: ("flat", p[0], 0, 1)}
        return {}
    if eff_type in REGENERATE_FIXED_TYPES:
        # 结构校验：回合 > 0、基数 > 0、除数 > 1（增量可为 0 = 固定值，不随等级）
        if (p[0] or 0) > 0 and (p[1] or 0) > 0 and (p[3] or 0) > 1:
            return {1: ("val", p[1] * 1000, p[2] or 0, p[3], "floor")}
        return {}
    if eff_type in ATTR_DEF_TYPES:
        # 结构校验：回合 > 0、基数 > 0、[6] 必须是属性名（增量可为 0）
        if (p[0] or 0) > 0 and (p[3] or 0) > 0 and raw[5] in ATTR_KEYS:
            return {2: ("val", p[3] * 1000, p[4] or 0, 1000, "floor")}
        return {}
    if eff_type in REFLECTION_TYPES:
        if (p[1] or 0) > 0 and (p[2] or 0) > 0:
            return {1: ("val", p[1], p[2], 100, "floor")}
        return {}
    if eff_type in COVER_WEAK_TYPES:
        # パラメータ3 ≠ 0 的行来自共通表且量级/语义不同，暂不处理（宁缺勿错）
        if (p[1] or 0) > 0 and (p[2] or 0) == 0:
            return {1: ("flat", p[1], 0, 10, "floor")}
        return {}
    if eff_type in DRAIN_TYPES:
        if (p[0] or 0) > 0:
            return {1: ("flat", p[0], 0, 1, "floor")}
        return {}
    if eff_type in ENCHANT_TYPES:
        # 结构校验：回合 > 0、基数 > 0、[3] 必须为 1000、[6] 必须是属性名（增量可为 0）
        if ((p[0] or 0) > 0 and (p[1] or 0) > 0 and (p[2] or 0) == 1000
                and raw[5] in ATTR_KEYS):
            return {1: ("val", p[1], p[4] or 0, 1)}
        return {}
    if eff_type in ATK_PIERCING_TYPES:
        # 结构校验：p1 > 0 且 p2 == 0（p2 ≠ 0 的 34 行量纲存疑，留空不猜）
        if (p[0] or 0) > 0 and (p[1] or 0) == 0:
            return {1: ("flat", p[0], 0, 1)}
        return {}
    if eff_type in DOT_TYPES:
        # 结构校验：回合 > 0、系数 > 0、基数 > 0、[8] 必须是参照属性名
        if (p[0] or 0) > 0 and (p[1] or 0) > 0 and (p[3] or 0) > 0 and raw[7] in STAT_TOKENS:
            return {2: ("val", p[3] * 1000, p[4] or 0, 1000, "floor")}
        return {}
    if eff_type in BLESS_TYPES:
        # 「祝福」后重述的效果值：三组 (基数, 每级增量) 相邻排列，不经除法
        if (p[0] or 0) > 0 and (p[2] or 0) == 1:
            out = {}
            for unit, ai, bi in ((7, 3, 4), (8, 5, 6), (9, 7, 8)):
                if (p[ai] or 0) or (p[bi] or 0):
                    out[unit] = ("val", p[ai] or 0, p[bi] or 0, 1)
            return out
        return {}
    if eff_type in TRANCE_TYPES:
        if raw[0] == "TRANCE" and (p[1] or 0) > 0:
            return {1: ("flat", p[1], 0, 1)}
        return {}
    if eff_type in DRAIN_ALL_TYPES:
        if (p[0] or 0) > 0:
            return {1: ("flat", p[0], 0, 1)}
        return {}
    if eff_type in REVENGE_TYPES:
        if (p[0] or 0) > 0 and raw[2] in STAT_TOKENS:
            return {1: ("flat", p[0], 0, 1)}
        return {}
    if eff_type in DAMAGE_INC_TYPES:
        # 仅「叠加目前血量/攻击力 X% 的威力」这一档（unit 2）；unit 1 的「点伤害」档未经实测，留空
        if (p[2] or 0) > 0:
            return {2: ("flat", p[2], 0, 10)}
        return {}
    return {}


def load_role_rows() -> dict:
    """skill_id → [(機能タイプ, パラメータ[10], 原始值[10])]，按行序；玩家表优先、共通表回落。"""
    roles: dict = {}
    filled: set = set()
    for name, type_col, first_param in (("skill_role_player.csv", 8, 20), ("skill_role.csv", 7, 19)):
        fresh: set = set()
        for row in read_csv(name, BATTLE_MASTER):
            skill_id = at(row, 0)
            if not is_numeric(skill_id) or skill_id in filled:
                continue
            fresh.add(skill_id)
            roles.setdefault(skill_id, []).append((
                at(row, type_col).strip(),
                [num(at(row, i)) for i in range(first_param, first_param + 10)],
                [at(row, i).strip() for i in range(first_param, first_param + 10)],
            ))
        filled |= fresh
    return roles


def resolve_slots(func_id: str, roles: dict, variant_ids: list | None = None) -> dict:
    """把「本体 + 発動条件分岐変体」的機能行列表转成 {token: [kind, a, b, c, mode?]}。

    mode 缺省为 round（四舍五入）；"floor" 表示游戏用整数除法需向下取整（如 REFLECTION）。

    槽位规则（全库验证 93.03%）：槽位 = 5 × 变体序号 + 变体内行号；
    token = 槽位 × 10 + 显示值序号（1 = 百分比/首值、2 = 基值）。
    本体 = 变体 0（占槽 0~4），第 k 个条件变体占槽 5k~5k+4（每变体最多 5 个機能）。
    实测：10180052 的 {51} = 变体 1 第 0 行（暴击率 70%）、{151} = 变体 3 第 0 行（100%）；
          10163064 的 {61} = 变体 1 第 1 行（血量百分比 20%）。
    """
    blocks: list = [(func_id, roles.get(func_id, []))]
    for fid in (variant_ids or []):
        blocks.append((fid, roles.get(fid, [])))
    per_skill: dict = {}
    for variant_index, (_fid, rows) in enumerate(blocks):
        for row_index, (eff_type, params, raw) in enumerate(rows[:5]):
            for unit, rule in slot_rules(eff_type, params, raw).items():
                kind, a, b, c = rule[0], rule[1], rule[2], rule[3]
                slot = [kind, a, b, c]
                # 第 5 位为取整模式；仅非默认（round）时写出，避免无谓改动既有数据
                if len(rule) > 4 and rule[4] != "round":
                    slot.append(rule[4])
                per_skill[str((variant_index * 5 + row_index) * 10 + unit)] = slot
    return per_skill


def variant_func_ids(variants: list, chosen_row: list) -> list:
    """同一技能 ID 的其余每一行 = 一个「発動条件分岐」機能ブロック，
    取它们的「機能ID」（[49]）所指技能的角色行，按行序编号为变体 1、2、3…

    - 不去重：同一機能ID 可以出现多次（如 1012400522 的分岐行 1/2 都指向 1012400524，
      但 token 里的 {151} 要求它是「第 3 个变体」），去重会把编号整体前移。
    - 不再按 desc 是否为空过滤：13600492 这类技能的変体行同样带着完整 desc
      （文本相同、[49] 指向兄弟技能 13600494），过滤掉会让 {71} 变成越界槽。
    实测四种取法的占位符覆盖率：blank 99.70% / blank-nodedup 99.79% /
    all 99.73% / all-nodedup 99.82%（越界槽 0，其余三法分别剩 24/5/19 个）。"""
    out: list = []
    for row in variants:
        if row is chosen_row:
            continue
        fid = at(row, 49).strip()
        if fid:
            out.append(fid)
    return out


def build_player_skills() -> dict[str, dict]:
    rows = read_csv("skill_player.csv", BATTLE_MASTER)
    roles = load_role_rows()
    # skill_player.csv 同一 ID 有多行 = 该技能的多个「变体」（本体 + 発動条件分岐行），
    # 每行自带 desc / 显示列 / 機能ID（[49]，7855 行指向兄弟技能，如 11102372 → 11102374）。
    # 機能列表取自「機能ID」对应技能的角色行，因此逐变体解析后再挑最优的一条。
    grouped: dict[str, list] = {}
    for row in rows:
        skill_id = at(row, 0)
        if is_numeric(skill_id):
            grouped.setdefault(skill_id, []).append(row)

    skills: dict[str, dict] = {}
    tokens_total = tokens_hit = 0
    unresolved_types: dict = {}
    picked_branch = 0
    for skill_id, variants in grouped.items():
        best = None
        for index, row in enumerate(variants):
            desc = text(at(row, 3))
            if is_blank_desc(desc):
                continue                      # 変体行（desc 空或字面 "0"），旧实现会覆盖正式行
            func_id = at(row, 49).strip() or skill_id
            slots = resolve_slots(func_id, roles, variant_func_ids(variants, row))
            desc_tokens = sorted({m for m in TOKEN_RE.findall(desc)}, key=int)
            unresolved = [t for t in desc_tokens if t not in slots]
            hit = len(desc_tokens) - len(unresolved)
            score = (hit, -len(unresolved), -index)
            if best is None or score > best["score"]:
                best = {
                    "score": score, "row": row, "desc": desc, "func_id": func_id,
                    "slots": slots, "unresolved": unresolved, "tokens": desc_tokens,
                }
        if best is None:
            continue
        row, desc = best["row"], best["desc"]
        slots, unresolved, desc_tokens = best["slots"], best["unresolved"], best["tokens"]
        func_types = [t for t, _, _ in roles.get(best["func_id"], [])]
        blocks = [best["func_id"]] + variant_func_ids(variants, best["row"])
        if best["func_id"] != skill_id:
            picked_branch += 1
        tokens_total += len(desc_tokens)
        tokens_hit += len(desc_tokens) - len(unresolved)
        for t in unresolved:
            variant_index, row_index = divmod(int(t) // 10, 5)
            vrows = roles.get(blocks[variant_index], []) if variant_index < len(blocks) else []
            eff_type = vrows[row_index][0] if row_index < len(vrows) else "(无此機能)"
            is_variant = variant_index > 0
            key = f"{eff_type}（条件变体）" if is_variant else eff_type
            unresolved_types[key] = unresolved_types.get(key, 0) + 1
        display_param = at(row, 4).strip()
        skills[skill_id] = {
            "id": num(skill_id),
            "name": text(at(row, 1)),
            "sub": text(at(row, 2)),
            "desc": desc,
            "category": at(row, 9).strip(),
            "kind": at(row, 10).strip(),
            "attr": at(row, 11).strip(),
            "job": at(row, 12).strip(),
            "physMagic": at(row, 13).strip(),
            "cost": num(at(row, 14)),
            "rank": at(row, 17).strip(),
            "hate": num(at(row, 18)),
            "target": at(row, 19).strip(),
            "valueSlots": slots,
            "mainToken": display_param if display_param in slots else "",
            "displayType": at(row, 7).strip(),
            "funcTypes": func_types,
            "unresolvedTokens": unresolved,
        }
    with_slots = sum(1 for s in skills.values() if s["valueSlots"])
    with_open = sum(1 for s in skills.values() if s["unresolvedTokens"])
    log(f"  玩家技能 {len(skills)} 条（{with_slots} 条有可算槽位，{with_open} 条仍有算不出的占位符；"
        f"采用分支变体 {picked_branch} 条）")
    log(f"  desc 占位符覆盖 {tokens_hit}/{tokens_total}"
        f"（{tokens_hit / tokens_total * 100:.1f}%）；未覆盖機能タイプ top8："
        f"{sorted(unresolved_types.items(), key=lambda x: -x[1])[:8]}")
    return skills


def build_enemy_skills() -> dict[str, dict]:
    rows = read_csv("skill_enemy.csv", BATTLE_MASTER)
    skills: dict[str, dict] = {}
    for row in rows:
        skill_id = at(row, 0)
        if not is_numeric(skill_id):
            continue
        skills[skill_id] = {
            "id": num(skill_id),
            "name": text(at(row, 1)),
            "desc": text(at(row, 3)),
            "attr": at(row, 11).strip(),
            "target": at(row, 19).strip(),
        }
    log(f"  敌方技能 {len(skills)} 条")
    return skills


def build_enemies() -> dict[str, dict]:
    rows = read_csv("enemy.csv", BATTLE_MASTER)
    enemies: dict[str, dict] = {}
    for row in rows:
        enemy_id = at(row, 0)
        if not is_numeric(enemy_id):
            continue
        enemies[enemy_id] = {
            "id": num(enemy_id),
            "name": text(at(row, 6)),
            "attr": at(row, 7).strip(),
            "hp": num(at(row, 8)),
            "atk": num(at(row, 9)),
            "int": num(at(row, 10)),
            "mnd": num(at(row, 11)),
            "def": num(at(row, 12)),
            "mdef": num(at(row, 13)),
            "dmgCut": num(at(row, 14)),
            "dmgCutAttr": [num(at(row, i)) for i in range(15, 20)],
            "size": at(row, 24).strip(),
        }
    log(f"  敌人 {len(enemies)} 条")
    return enemies


def build_enemy_parties() -> dict[str, dict]:
    rows = read_csv("enemy_party.csv", BATTLE_MASTER)
    parties: dict[str, dict] = {}
    for row in rows:
        party_id = at(row, 0)
        if not is_numeric(party_id):
            continue
        slots = []
        for slot in range(4):
            base = 2 + slot * 3
            enemy_id = at(row, base)
            if not is_numeric(enemy_id):
                continue
            slots.append(
                {
                    "slot": slot + 1,
                    "enemyId": num(enemy_id),
                    "hpRate": num(at(row, base + 1)),
                    "parent": num(at(row, base + 2)),
                }
            )
        parties[party_id] = {"id": num(party_id), "slots": slots}
    log(f"  敌人队伍 {len(parties)} 条")
    return parties


def build_ai_orders() -> dict[str, dict]:
    rows = read_csv("enemy_ai_order.csv", BATTLE_MASTER)
    orders: dict[str, dict] = {}
    for row in rows:
        order_id = at(row, 0)
        if not is_numeric(order_id):
            continue
        orders[order_id] = {
            "id": num(order_id),
            "partyCondition": at(row, 1).strip(),
            "transCondition": at(row, 2).strip(),
            "hpMin": num(at(row, 3)),
            "hpMax": num(at(row, 4)),
            "bodyHpMin": num(at(row, 5)),
            "bodyHpMax": num(at(row, 6)),
            "turns": [num(at(row, i)) for i in range(7, 18)],
            "loopStart": num(at(row, 18)),
            "loopTurns": [num(at(row, i)) for i in range(19, 29)],
            "trigger": at(row, 29).strip(),
            "triggerParams": [num(at(row, i)) for i in range(30, 38)],
        }
    log(f"  行动轴 {len(orders)} 条")
    return orders


def build_boss_char_map() -> dict[str, int]:
    rows = read_csv("teambattle_boss.csv", BATTLE_MASTER)
    mapping: dict[str, int] = {}
    for row in rows:
        boss_id = at(row, 0)
        char_id = at(row, 1)
        if is_numeric(boss_id) and is_numeric(char_id):
            mapping[boss_id] = num(char_id)
    log(f"  Boss-角色映射 {len(mapping)} 条")
    return mapping


def build_evolutions() -> dict[str, dict]:
    rows = read_csv("card_evolution.csv", CARD_MASTER)
    result: dict[str, dict] = {}
    for row in rows:
        from_id = at(row, 0)
        if not is_numeric(from_id):
            continue
        materials = []
        for slot in range(6):
            base = 5 + slot * 3
            material_id = at(row, base)
            if not is_numeric(material_id):
                continue
            materials.append(
                {
                    "cardId": num(material_id),
                    "fame": num(at(row, base + 1)),
                    "num": num(at(row, base + 2)),
                }
            )
        to_id = at(row, 4)
        # 部分行只有 ID 没有进化目标（如已到最终形态的占位行），跳过
        if not is_numeric(to_id):
            continue
        result[from_id] = {
            "from": num(from_id),
            "to": num(to_id),
            "type": at(row, 1).strip(),
            "keepLevel": bool(num(at(row, 2))),
            "gold": num(at(row, 3)),
            "materials": materials,
        }
    log(f"  进化链 {len(result)} 条")
    return result


def build_cards(
    skills: dict[str, dict],
    stack_templates: dict[str, dict],
    source_overrides: dict[str, str] | None = None,
) -> list[dict]:
    source_overrides = source_overrides or {}
    rows = read_csv("card.csv", CARD_MASTER)

    # 第一遍：按同卡族（col2 同カードID）确定「入手途径」。
    # 同族各形态的 col94 不同（初始=扭蛋、进阶=进化/因子覚醒/限界突破），
    # 取族内稀有度最低、且有入手途径记录的那一形态作为整族的入手途径。
    rarity_rank = {name: idx for idx, name in enumerate(RARITY)}
    parsed: list[tuple] = []
    family_best: dict[int, tuple[int, int, str]] = {}
    for row in rows:
        card_id = at(row, 0)
        if not is_numeric(card_id):
            continue
        cid = num(card_id)
        same_id = num(at(row, 2)) or cid
        acquire = text(at(row, 94))
        rank = rarity_rank.get(at(row, 7).strip(), 99)
        parsed.append((cid, same_id, rank, acquire, row))
        if is_channel(acquire):
            key = (rank, cid)
            prev = family_best.get(same_id)
            if prev is None or key < (prev[0], prev[1]):
                family_best[same_id] = (rank, cid, acquire)
    family_channel = {fid: v[2] for fid, v in family_best.items()}
    log(f"  卡族入手途径可判 {len(family_channel)} / {len({p[1] for p in parsed})}")

    # 進化後ID → 進化タイプ，用于给 col94 为空的卡反推成长方式
    evo_kind: dict[str, str] = {}
    for evo_row in read_csv("card_evolution.csv", CARD_MASTER):
        if len(evo_row) > 4 and evo_row[4].strip().isdigit():
            evo_kind[evo_row[4].strip()] = evo_row[1].strip()
    log(f"  进化目标类型 {len(evo_kind)} 条")

    cards: list[dict] = []
    stats = {"skillMissing": 0, "sourceInherited": 0}
    for card_id, same_id, _rank, acquire, row in parsed:
        skill_id = at(row, 26).strip()
        skill = skills.get(skill_id)
        if skill_id and not skill:
            stats["skillMissing"] += 1
        support_ids = [at(row, i).strip() for i in (29, 30, 31)]
        support_ids = [value for value in support_ids if is_numeric(value)]
        stack = stack_templates.get(card_id) or {}
        # 国服卡表 cost 大面积缺失（7650/8437 为 0），客户端实际显示的是主技能的 コスト；
        # 卡表有值时优先用卡表（如妖精卡 卡表=1、技能=4，游戏显示 1）
        cost = num(at(row, 9))
        if cost <= 0:
            cost = (skill or {}).get("cost", 0) or 0
        title = text(at(row, 4))
        main_name = text(at(row, 5))
        # 入手途径来自卡族根形态；本形态自身的记录另存为 growth
        channel = family_channel.get(same_id, "")
        if channel and channel != acquire:
            stats["sourceInherited"] += 1
        source = card_source(channel, title, main_name)
        source_override = source_overrides.get(str(card_id)) or source_overrides.get(str(same_id)) or ""
        if source_override:
            source = source_override
            stats["sourceOverridden"] = stats.get("sourceOverridden", 0) + 1
        cards.append(
            {
                "id": card_id,
                "baseId": num(at(row, 1)),
                "sameId": num(at(row, 2)),
                "title": title,
                "mainName": main_name,
                "stack": bool(num(at(row, 6))),
                "rarity": at(row, 7).strip(),
                "rarityPlus": at(row, 8).strip(),
                "rarityLabel": rarity_label(at(row, 7).strip(), num(at(row, 23))),
                "cost": cost,
                "hp": num(at(row, 10)),
                "hpMax": num(at(row, 11)),
                "atk": num(at(row, 13)),
                "atkMax": num(at(row, 14)),
                "int": num(at(row, 16)),
                "intMax": num(at(row, 17)),
                "mnd": num(at(row, 19)),
                "mndMax": num(at(row, 20)),
                "limitBreak": num(at(row, 22)),
                "levelMax": num(at(row, 23)),
                "loveMax": num(at(row, 24)),
                "fameMax": num(at(row, 25)),
                "skillId": num(skill_id) if is_numeric(skill_id) else 0,
                "arthurSkillId": num(at(row, 27)) if is_numeric(at(row, 27)) else 0,
                "supportSkillIds": [num(value) for value in support_ids],
                "skillLevelMax": num(at(row, 34)),
                "pictId": num(at(row, 36)),
                "expTableId": at(row, 41).strip(),
                "sellGold": num(at(row, 42)),
                "materialType": num(at(row, 43)),
                "flavor": text(at(row, 44)),
                "illustrator": text(at(row, 45)),
                "cv": text(at(row, 46)),
                "acquire": acquire,
                "channel": channel,
                "source": source,
                "growth": card_growth(acquire, card_id, evo_kind),
                "sourceManual": bool(source_override),
                "usage": text(at(row, 93)),
                "decomposable": num(at(row, 95)),
                "decomposeRadix": num(at(row, 96)),
                "developRadix": num(at(row, 97)),
                "attr": (skill or {}).get("attr", ""),
                "job": (skill or {}).get("job", ""),
                "skillName": (skill or {}).get("name", ""),
                "skillKind": (skill or {}).get("kind", ""),
                "addExp": stack.get("add_exp", 0),
                "baseAddPrice": stack.get("base_add_price", 0),
            }
        )
    log(
        f"  卡牌 {len(cards)} 条（技能缺失 {stats['skillMissing']}，"
        f"来源由族根继承 {stats['sourceInherited']}）"
    )
    return cards


# ---------------------------------------------------------------- Boss


def boss_name(boss: dict) -> str:
    return text(boss.get("11") or "")


def build_bosses(
    enemies: dict[str, dict],
    parties: dict[str, dict],
    orders: dict[str, dict],
    char_map: dict[str, int],
    cards: list[dict],
) -> list[dict]:
    battle = read_json("cn602-battle-runtime-master.json")
    replays = {str(item["boss_id"]): item for item in battle.get("replays", [])}
    rewards = {str(item["boss_id"]): item for item in battle.get("rewards", [])}
    recommendations = {str(item["bossid"]): item for item in battle.get("recommendations", [])}
    card_name = {str(card["id"]): card for card in cards}

    # 往期 Boss 与当前分组是同一批 ID 的子集，这里只用来打标记
    past_ids = {
        str(boss.get("0"))
        for group in battle.get("past_boss_groups", [])
        for boss in (group.get("13") or group.get("10") or [])
    }

    bosses: list[dict] = []
    seen: set[str] = set()

    def emit(group: dict, past: bool) -> None:
        group_id = group.get("0")
        group_name = text(group.get("4") or "")
        group_sub = text(group.get("6") or "")
        boss_list = group.get("10") or group.get("13") or []
        for boss in boss_list:
            boss_id = str(boss.get("0"))
            if boss_id in seen:
                continue
            seen.add(boss_id)
            is_past = boss_id in past_ids
            replay = replays.get(boss_id) or {}
            waves = []
            for wave_index, entry in enumerate(replay.get("battles") or []):
                party_id = str(entry.get("enemy_party_id"))
                party = parties.get(party_id) or {}
                parts = []
                for slot in party.get("slots", []):
                    enemy = enemies.get(str(slot["enemyId"])) or {}
                    parts.append(
                        {
                            "slot": slot["slot"],
                            "enemyId": slot["enemyId"],
                            "name": enemy.get("name", ""),
                            "attr": enemy.get("attr", ""),
                            "hp": enemy.get("hp", 0),
                            "atk": enemy.get("atk", 0),
                            "int": enemy.get("int", 0),
                            "mnd": enemy.get("mnd", 0),
                            "def": enemy.get("def", 0),
                            "mdef": enemy.get("mdef", 0),
                            "dmgCut": enemy.get("dmgCut", 0),
                            "dmgCutAttr": enemy.get("dmgCutAttr", []),
                            "size": enemy.get("size", ""),
                            "hpRate": slot["hpRate"],
                            "parent": slot["parent"],
                        }
                    )
                order = orders.get(party_id)
                waves.append(
                    {
                        "index": wave_index + 1,
                        "enemyPartyId": int(party_id) if party_id.isdigit() else 0,
                        "parts": parts,
                        "order": order,
                    }
                )
            reward = rewards.get(boss_id) or {}
            reward_cards = []
            for entry in boss.get("12") or []:
                card_id = str(entry.get("0"))
                card = card_name.get(card_id)
                reward_cards.append(
                    {
                        "id": int(card_id) if card_id.isdigit() else 0,
                        "name": (card or {}).get("mainName", ""),
                        "title": (card or {}).get("title", ""),
                        "rarity": (card or {}).get("rarity", ""),
                        "pictId": (card or {}).get("pictId", 0),
                    }
                )
            recommendation = recommendations.get(boss_id)
            bosses.append(
                {
                    "id": int(boss_id) if boss_id.isdigit() else 0,
                    "name": boss_name(boss),
                    "groupId": group_id,
                    "groupName": group_name,
                    "groupSub": group_sub,
                    "past": is_past,
                    "difficulty": text(boss.get("4") or ""),
                    "bpUse": num(str(boss.get("5") or "")),
                    "bpUseHalf": num(str(boss.get("6") or "")),
                    "onlyMyDeck": num(str(boss.get("1") or "")),
                    "continue": num(str(boss.get("7") or "")),
                    "startRule": num(str(boss.get("24") or "")),
                    "characterId": char_map.get(boss_id, 0),
                    "rewardCards": reward_cards,
                    "waves": waves,
                    "resultRewards": reward.get("result_rewards", []),
                    "firstClearRewards": reward.get("first_clear_rewards", []),
                    "enemyDrops": reward.get("enemy_drops", []),
                    "recommend": (
                        {
                            "name": text(recommendation.get("name") or ""),
                            "attr": recommendation.get("attr", 0),
                            "cards": [c for c in recommendation.get("recommendid", []) if c],
                        }
                        if recommendation
                        else None
                    ),
                }
            )

    for group in battle.get("groups", []):
        emit(group, False)

    log(f"  Boss {len(bosses)} 个（含波次与掉落，往期 {len(past_ids)} 个）")
    return bosses


# ---------------------------------------------------------------- 主流程


def main() -> int:
    if not os.path.isdir(CONTROL):
        log(f"数据源不存在: {CONTROL}")
        log("可通过环境变量 KAIRI_SRC 指定 resource-set 目录")
        return 1

    os.makedirs(OUT, exist_ok=True)
    started = time.time()
    log("读取主表 ...")

    exp_tables = build_exp_tables()
    skills = build_player_skills()
    enemy_skills = build_enemy_skills()
    enemies = build_enemies()
    parties = build_enemy_parties()
    orders = build_ai_orders()
    char_map = build_boss_char_map()
    evolutions = build_evolutions()

    card_master = read_json("cn602-card-runtime-master.json")
    stack_templates = {
        str(item["cardid"]): item for item in card_master.get("stack_card_templates", [])
    }
    log(f"  素材卡模板 {len(stack_templates)} 条")
    fusion_policy = card_master.get("card_progression_policy") or {}
    source_overrides = load_source_overrides()
    cards = build_cards(skills, stack_templates, source_overrides)

    log("读取道具与 Boss ...")
    item_master = read_json("cn602-item-runtime-master.json")
    items = {
        str(item["item_id"]): {
            "id": item["item_id"],
            "name": text(item.get("name", "")),
            "pictId": item.get("pict_id", 0),
            "type": item.get("item_type", ""),
            "desc": text(item.get("description", "")),
            "maxOwned": item.get("max_owned", 0),
        }
        for item in item_master.get("items", [])
    }
    log(f"  道具 {len(items)} 条")

    bosses = build_bosses(enemies, parties, orders, char_map, cards)

    # 图片映射：卡面图文件名规则 chr51_<8位>.png
    image_dir = os.path.join(IMAGE_ROOT, "chr51")
    image_ids: set[str] = set()
    if os.path.isdir(image_dir):
        for name in os.listdir(image_dir):
            match = re.fullmatch(r"chr51_(\d{8})\.png", name)
            if match:
                image_ids.add(str(int(match.group(1))))
    available = sum(1 for card in cards if str(card["pictId"]) in image_ids)
    log(f"  卡面图 {len(image_ids)} 张，命中卡牌 {available}/{len(cards)}")

    # 卡牌拆分：索引（列表页用）与详情（按需加载）
    # 同卡族：同カードID 相同的多条记录 = 同一张卡的不同进化阶段/稀有度版本
    family_ids = {card["sameId"] for card in cards}
    family_ids_playable = {card["sameId"] for card in cards if not card["stack"]}
    log(f"  同卡族 {len(family_ids)} 组（排除素材卡 {len(family_ids_playable)} 组）")

    # 技能只保留被卡牌引用的，缩减体积
    used_skill_ids = {str(card["skillId"]) for card in cards if card["skillId"]}
    used_skill_ids.update(str(card["arthurSkillId"]) for card in cards if card["arthurSkillId"])
    for card in cards:
        used_skill_ids.update(str(value) for value in card["supportSkillIds"])
    slim_skills = {key: value for key, value in skills.items() if key in used_skill_ids}
    log(f"  技能裁剪 {len(skills)} -> {len(slim_skills)}（被引用）")

    keywords = build_keywords(slim_skills)

    # Boss 拆分：索引（列表页用）与详情（按需加载）
    boss_index = []
    boss_detail: dict[str, dict] = {}
    for boss in bosses:
        key = str(boss["id"])
        boss_index.append(
            {
                "id": boss["id"],
                "name": boss["name"],
                "groupId": boss["groupId"],
                "groupName": boss["groupName"],
                "groupSub": boss["groupSub"],
                "past": boss["past"],
                "difficulty": boss["difficulty"],
                "bpUse": boss["bpUse"],
                "bpUseHalf": boss["bpUseHalf"],
                "onlyMyDeck": boss["onlyMyDeck"],
                "continue": boss["continue"],
                "startRule": boss["startRule"],
                "characterId": boss["characterId"],
                "waveCount": len(boss["waves"]),
                "rewardCards": boss["rewardCards"],
                "recommendAttr": (boss["recommend"] or {}).get("attr", 0),
                "hasOrder": any(wave.get("order") for wave in boss["waves"]),
            }
        )
        boss_detail[key] = {
            "id": boss["id"],
            "waves": boss["waves"],
            "resultRewards": boss["resultRewards"],
            "firstClearRewards": boss["firstClearRewards"],
            "enemyDrops": boss["enemyDrops"],
            "recommend": boss["recommend"],
        }
    log(f"  Boss 索引 {len(boss_index)} / 详情 {len(boss_detail)}")

    outputs = {
        "meta.json": {
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": SRC,
            "counts": {
                "cards": len(cards),
                "cardFamilies": len(family_ids),
                "cardFamiliesPlayable": len(family_ids_playable),
                "skills": len(slim_skills),
                "enemySkills": len(enemy_skills),
                "evolutions": len(evolutions),
                "items": len(items),
                "bosses": len(bosses),
                "enemies": len(enemies),
                "images": len(image_ids),
            },
            "enums": {
                "rarity": RARITY,
                "rarityOrder": RARITY_ORDER,
                "rarityLabelOrder": {label: idx for idx, label in enumerate(RARITY_LABEL_ORDER)},
                "sourceOrder": SOURCE_ORDER,
                "growthOrder": GROWTH_ORDER,
                "attr": ATTR,
                "job": JOB,
                "skillKind": SKILL_KIND,
                "skillTarget": SKILL_TARGET,
                "skillPhysMagic": SKILL_PHYS_MAGIC,
                "rewardType": {str(k): v for k, v in REWARD_TYPE.items()},
            },
            "fusion": {
                "goldPerMaterialPerBaseLevel": fusion_policy.get("fusion_gold_per_material_per_base_level", 0),
                "maxMaterialCount": fusion_policy.get("maximum_card_material_count", 0),
                "successTypes": fusion_policy.get("fusion_success_types", []),
            },
        },
        "cards.json": cards,
        "skills.json": slim_skills,
        "enemy_skills.json": enemy_skills,
        "evolutions.json": evolutions,
        "items.json": items,
        "exp_tables.json": exp_tables,
        "boss_index.json": boss_index,
        "boss_detail.json": boss_detail,
        "keywords.json": keywords,
    }

    for name, payload in outputs.items():
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        size = os.path.getsize(path) / 1024
        log(f"  写出 {name:<20} {size:>9.1f} KB")

    log(f"完成，用时 {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
