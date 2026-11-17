#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""查我的分工：负责哪份文档 + 负责哪几章算法 + 第二阶段要补什么。

用法：
    python tools/whoami.py            # 六个人总览 + 覆盖性自检
    python tools/whoami.py P4         # 只看 P4
    python tools/whoami.py P4 --todo  # 只看还没写讲义的（讲义是加分项）

这是「分工可验证」的实现：分工表不是嘴上说说，脚本能算出来。
第一阶段分工（DUTY）口径与 README 第七节、需求文档末尾的分工表一致；
第二阶段任务（NEXT）口径与 docs/组员任务卡_2026-11-21/ 里的人卡一致。改的时候两边一起改。
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LECTURE = ROOT / "docs" / "讲义"          # 讲义是可选的加分项，目录可以不存在

# 分工表：代号 -> (姓名, 角色, 负责文档, 负责章节)
# 文档维度决定谁交什么；章节维度决定后面谁修数据、谁写讲义。
# ⚠️ 需求文档按课程要求只有一个文件（Project_Requirements_and_Design.md），
#    P2/P3/P4 三人分章同写一份文档 —— 这正是那次真实合并冲突的来源，不是笔误。
# ⚠️ 改这里必须同步改 README 第七节与需求文档末尾的分工表
DUTY = {
    "P1": ("邓宇轩", "组长 / 服务层与集成", "README.md",
           ["chapter_computational_complexity"]),
    "P2": ("王瑞", "需求 · 第一章 背景与目标",
           "docs/Project_Requirements_and_Design.md",
           ["chapter_array_and_linkedlist", "chapter_stack_and_queue", "chapter_hashing"]),
    "P3": ("郭子琪", "需求 · 第二章 功能与数据",
           "docs/Project_Requirements_and_Design.md",
           ["chapter_tree", "chapter_heap", "chapter_graph"]),
    "P4": ("张超明", "需求 · 第三章 技术方案与验收 ★ 先遣员",
           "docs/Project_Requirements_and_Design.md",
           ["chapter_searching", "chapter_sorting"]),
    "P5": ("吴家溢", "AI 使用记录（汇总全组 6 人）", "docs/AI_Prompts_Log.md",
           ["chapter_divide_and_conquer", "chapter_greedy", "chapter_backtracking"]),
    # P6 原来分的是 web/explore.html，改为 Python 渲染后这个文件已删除，
    # 检索页现在是 eg/render.py 里的 search / list_html / chips_html 三处
    "P6": ("焦明远", "检索页 + 列表页", "eg/render.py",
           ["chapter_dynamic_programming"]),
}

# 第二阶段任务（2026-11-21 起）：代号 -> (任务, 目标文件)
# 口径：每人 1 件事、1 次提交、1 个 PR、不超过 30 分钟，全程浏览器操作。
# 任务细则、AI 提示词、验收标准全在 docs/组员任务卡_2026-11-21/ 里对应那一份，这里只留一句索引。
# 章节归属（DUTY 第四项）第二阶段不变，仍用于讲义的覆盖性自检。
NEXT = {
    "P1": ("组长：合并 5 个 PR、录演示视频、填选题表",
           "README.md"),
    "P2": ("需求文档重编号 + 新增「二、知识原理」",
           "docs/Project_Requirements_and_Design.md"),
    "P3": ("新增「四、可视化设计」输入→处理→展示→交互",
           "docs/Project_Requirements_and_Design.md"),
    "P4": ("更新 README §7.1 第二阶段分工为新口径", "README.md"),
    "P5": ("新建演示视频口播稿（6 分 30 秒分镜）", "docs/演示脚本.md"),
    "P6": ("补贡献说明 + 解决与 §7.1 的合并冲突", "README.md"),
}


def load():
    p = DATA / "algos.json"
    if not p.exists():
        raise SystemExit("缺少 data/algos.json，先跑 python tools/extract.py")
    return json.loads(p.read_text(encoding="utf-8"))


def doc_state(rel):
    """你负责的文档现在是什么状态：没建 / 空壳 / 有内容。"""
    p = ROOT / rel
    if not p.exists():
        return "没建"
    try:
        n = len(p.read_text(encoding="utf-8", errors="replace").strip())
    except Exception:
        return "有内容"
    return "空壳" if n < 200 else "有内容"


def lecture_done(stem, ch):
    """讲义是否已写（存在且正文 > 200 字）。讲义是加分项，没写不算欠账。"""
    p = LECTURE / ch / (stem + ".md")
    if not p.exists():
        return False
    return len(p.read_text(encoding="utf-8", errors="replace")) > 200


def report(algos, who=None, only_todo=False):
    keys = [who.upper()] if who else list(DUTY)
    seen = set()

    for key in keys:
        name, role, doc, chs = DUTY[key]
        mine = [a for a in algos if a["ch"] in chs]
        seen |= {a["id"] for a in mine}
        todo = [a for a in mine if not lecture_done(a["stem"], a["ch"])]

        print("\n%s · %s · %s" % (key, name, role))
        print("  你负责的文档：%s  [%s]" % (doc, doc_state(doc)))
        if key in NEXT:
            task, target = NEXT[key]
            print("  第二阶段任务：%s" % task)
            print("  第二阶段改：%s  [%s]" % (target, doc_state(target)))
        print("  你负责的章节：%d 章 / %d 条算法（讲义已写 %d，未写 %d —— 讲义是加分项）"
              % (len(chs), len(mine), len(mine) - len(todo), len(todo)))
        print("-" * 68)
        for a in mine:
            ok = lecture_done(a["stem"], a["ch"])
            if only_todo and ok:
                continue
            mark = "✓" if ok else " "
            core = "*" if a.get("core") else " "
            print("  [%s]%s %-32s %-18s %4d 行" % (mark, core, a["id"], a["name"], a["lines"]))

    if who:
        return

    # 覆盖性自检：76 条必须全覆盖、零重叠
    all_ids = [a["id"] for a in algos]
    own = {}
    for key, (_, _, _, chs) in DUTY.items():
        for a in algos:
            if a["ch"] in chs:
                own.setdefault(a["id"], []).append(key)
    dup = {k: v for k, v in own.items() if len(v) > 1}
    miss = [i for i in all_ids if i not in own]

    print("\n" + "=" * 68)
    print("分工覆盖自检：算法 %d 条 / 已分配 %d 条" % (len(all_ids), len(own)))
    print("  重复认领：%s" % (dup if dup else "无"))
    print("  无人认领：%s" % (miss if miss else "无"))
    if dup or miss:
        print("  ⚠️ 分工表有问题，改 DUTY，同步改 README 第七节与需求文档分工表")
    else:
        print("  ✅ 76 条不重不漏，分工表与数据一致")

    print("\n文档进度（W1 四步走的产出）：")
    for key, (name, _, doc, _) in DUTY.items():
        print("  %s  %-6s %-38s %s" % (key, name, doc, doc_state(doc)))

    print("\n第二阶段任务（细则见 docs/组员任务卡_2026-11-21/）：")
    for key, (name, _, _, _) in DUTY.items():
        task, target = NEXT[key]
        print("  %s  %-6s %s" % (key, name, task))
        print("      改 %-44s [%s]" % (target, doc_state(target)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("who", nargs="?", help="P1~P6，不填则看全部")
    ap.add_argument("--todo", action="store_true", help="只列还没写讲义的")
    ns = ap.parse_args()

    if ns.who and ns.who.upper() not in DUTY:
        raise SystemExit("代号只有 P1~P6")

    report(load(), ns.who, ns.todo)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
