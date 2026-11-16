# -*- coding: utf-8 -*-
"""数据层：把 data/ 下的 JSON 与 .c 源码读进内存。

这一层不认识 HTML，也不认识 HTTP，只回答「有哪些算法、某个算法的源码是什么」。
好处是能单独写单元测试，也能被后面的 render / server 共用。
"""

import json
from pathlib import Path


class Archive(object):
    """整个知识图谱的只读数据仓库，进程内加载一次。"""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data_dir = self.root / "data"
        self.code_dir = self.data_dir / "codes"
        self.img_dir = self.data_dir / "imgs"

        self.meta = self._load_json("meta.json")
        self.layers = self._load_json("layers.json")
        self.chapters = self._load_json("chapters.json")
        self.algos = self._load_json("algos.json")
        self.deps = self._load_json("deps.json")
        self.images = self._load_json("imgs.index.json")

        self.by_id = {}
        for a in self.algos:
            self.by_id[a["id"]] = a
        self.core = [a for a in self.algos if a.get("core")]
        self.img_paths = frozenset(i["path"] for i in self.images)
        self._code_cache = {}

        # 章节按 layer 排一遍，保证页面上的顺序稳定（不依赖 dict 的写入顺序）
        self.chapter_keys = sorted(
            self.chapters.keys(),
            key=lambda k: (self.chapters[k][1], self.chapters[k][0]),
        )

    # ------------------------------------------------------------------ 基础

    def _load_json(self, name):
        p = self.data_dir / name
        if not p.exists():
            raise FileNotFoundError("缺少 data/%s，先跑 python tools/extract.py" % name)
        return json.loads(p.read_text(encoding="utf-8"))

    def get(self, algo_id):
        """按 id 取算法记录，不存在返回 None。"""
        return self.by_id.get(algo_id)

    def code_text(self, algo_id):
        """读 .c 源码原文。

        直接从 data/codes/ 读盘，不读 algos.json 里的副本——
        源文件才是唯一的真相，JSON 只是索引。
        """
        if algo_id in self._code_cache:
            return self._code_cache[algo_id]
        a = self.get(algo_id)
        if not a:
            return ""
        p = self.code_dir / a["ch"] / (a["stem"] + ".c")
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        self._code_cache[algo_id] = text
        return text

    def chapter_title(self, key):
        v = self.chapters.get(key)
        return v[0] if v else key

    def chapter_tag(self, key):
        v = self.chapters.get(key)
        return v[2] if v and len(v) > 2 else ""

    def chapter_layer(self, key):
        v = self.chapters.get(key)
        return v[1] if v else 0

    def by_chapter(self, key):
        return [a for a in self.algos if a["ch"] == key]

    # ------------------------------------------------------------ 图片地址

    def has_image(self, path):
        return path in self.img_paths

    def image_url(self, path):
        """把 data 里的图片逻辑路径转成浏览器可请求的 URL。"""
        safe = path.replace("\\", "/").lstrip("/")
        return "/img/" + safe

    # ------------------------------------------------------------ 检索

    def search(self, q="", chapter=""):
        """服务端检索：算法名 / 文件名 / 简介 / 章节名，任一命中即算。

        大小写不敏感。q 为空时只按章节过滤。
        """
        q = (q or "").strip().lower()
        chapter = (chapter or "").strip()

        hits = []
        for a in self.algos:
            if chapter and a["ch"] != chapter:
                continue
            if q:
                haystack = " ".join([
                    a.get("name", ""),
                    a.get("stem", ""),
                    a.get("brief", ""),
                    a.get("file", ""),
                    self.chapter_title(a["ch"]),
                ]).lower()
                if q not in haystack:
                    continue
            hits.append(a)
        return hits

    def core_list(self):
        """精讲节点按「层 → 原顺序」排。

        图谱绘制、详情页翻页都依赖这个顺序，所以统一从这里取，
        不要在别处再写一次 filter+sort，否则两处顺序迟早会不一致。
        """
        return sorted(self.core, key=lambda a: a.get("layer", 0))

    # ------------------------------------------------------------ 汇总指标

    def stats(self):
        return {
            "core": self.meta.get("core", len(self.core)),
            "total": self.meta.get("total", len(self.algos)),
            "compile_ok": self.meta.get("compile_ok", 0),
            "run_ok": self.meta.get("run_ok", 0),
            "images": self.meta.get("images", len(self.images)),
            "chapters": len(self.chapters),
            "generated": self.meta.get("generated", ""),
        }

    def neighbours(self, algo_id):
        """返回 (上一个, 下一个) 精讲节点的 id，供详情页翻页用。"""
        ids = [a["id"] for a in self.core]
        if algo_id not in ids:
            return (None, None)
        i = ids.index(algo_id)
        return (ids[i - 1], ids[(i + 1) % len(ids)])
