# -*- coding: utf-8 -*-
"""检查 Boss 索引/详情覆盖情况，挑选演示用样例。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
idx = json.load(open(os.path.join(HERE, "public", "data", "boss_index.json"), encoding="utf-8"))
det = json.load(open(os.path.join(HERE, "public", "data", "boss_detail.json"), encoding="utf-8"))

print("boss 总数:", len(idx))
print("hasOrder:", sum(1 for b in idx if b["hasOrder"]))
print("waveCount>1:", sum(1 for b in idx if b["waveCount"] > 1))
print("past:", sum(1 for b in idx if b["past"]))
print("有奖励卡:", sum(1 for b in idx if b["rewardCards"]))

cands = [b for b in idx if b["hasOrder"] and b["waveCount"] >= 2]
cands.sort(key=lambda b: (-b["waveCount"], -len(b["rewardCards"])))
print("\n候选（有行动轴 + 多波次）:")
for boss in cands[:8]:
    detail = det[str(boss["id"])]
    parts = sum(len(wave["parts"]) for wave in detail["waves"])
    drops = len(detail["enemyDrops"])
    print(
        f"  boss={boss['id']} {boss['name']} | {boss['groupName']} {boss['difficulty']} "
        f"波={boss['waveCount']} 部位={parts} 掉落={drops} BP={boss['bpUse']} 奖励卡={len(boss['rewardCards'])}"
    )

print("\n往期 Boss 缺失排查: past 计数 =", sum(1 for b in idx if b["past"]))
