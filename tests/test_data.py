#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据层单元测试。用标准库 unittest，机房不装 pytest 也能跑。

跑法：
    python tests/test_data.py
    python -m unittest discover -s tests -v

和 tools/verify.py 的分工：
    verify.py   —— 给组员用的「一键裁判」，输出中文，看红绿
    本文件      —— 给 CI / 答辩用的「可计数测试」，能报「几个通过几个失败」
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


class TestData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.algos = load("algos.json")
        cls.chapters = load("chapters.json")
        cls.layers = load("layers.json")
        cls.deps = load("deps.json")
        cls.imgs = load("imgs.index.json")

    def test_算法总数(self):
        self.assertEqual(len(self.algos), 76, "算法条数变了？确认是不是有意为之")

    def test_每章都有算法(self):
        used = {a["ch"] for a in self.algos}
        self.assertEqual(set(self.chapters), used, "有章节一条算法都没有")

    def test_id不重复(self):
        ids = [a["id"] for a in self.algos]
        self.assertEqual(len(ids), len(set(ids)))

    def test_层级在范围内(self):
        n = len(self.layers)
        for a in self.algos:
            self.assertIsInstance(a["layer"], int)
            self.assertTrue(0 <= a["layer"] < n, "layer 越界：%s" % a["id"])

    def test_依赖无环(self):
        graph = {}
        for a, b in self.deps:
            graph.setdefault(a, []).append(b)
        seen, stack = set(), set()

        def walk(n):
            if n in stack:
                return True
            if n in seen:
                return False
            seen.add(n)
            stack.add(n)
            bad = any(walk(m) for m in graph.get(n, []))
            stack.discard(n)
            return bad

        cyc = [n for n in graph if walk(n)]
        self.assertFalse(cyc, "依赖成环：%s" % cyc)

    def test_源文件都存在且非空(self):
        for a in self.algos:
            p = DATA / "codes" / a["ch"] / (a["stem"] + ".c")
            self.assertTrue(p.exists(), "缺源文件：%s" % p)
            self.assertGreater(p.stat().st_size, 0, "空文件：%s" % p)

    def test_图片引用都能解析(self):
        known = {i["path"] for i in self.imgs}
        for a in self.algos:
            for p in a.get("imgs") or []:
                self.assertIn(p, known, "%s 引用了不存在的图" % a["id"])

    def test_每条都有备注(self):
        for a in self.algos:
            note = a.get("note") or {}
            self.assertTrue(note.get("steps") or note.get("detail"), "%s 没有备注" % a["id"])

    def test_编译状态是合法枚举(self):
        for a in self.algos:
            self.assertIn(str(a.get("compile")), ("OK", "FAIL"), "%s 的 compile 字段异常" % a["id"])

    def test_文档骨架存在(self):
        """任务卡与交付文档是六个人开工的前提，删了就没人知道自己该干什么。

        旧的职责分工与组员手册已于 2026-11-17 归档到仓库外
        （结课作业/_归档_旧口径_2026-11-17/docs/），现行口径只认这五张卡。
        """
        must = [
            "docs/AI_Prompts_Log.md",
            "docs/Project_Requirements_and_Design.md",
            "docs/踩坑记录.md",
            "README.md",
        ]
        must += ["docs/组员任务卡_2026-11-21/P%d_%s_任务卡.md" % (n, s)
                 for n, s in ((2, "王瑞"), (3, "郭子琪"), (4, "张超明"),
                              (5, "吴家溢"), (6, "焦明远"))]
        for rel in must:
            self.assertTrue((ROOT / rel).exists(), "缺了 %s" % rel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
