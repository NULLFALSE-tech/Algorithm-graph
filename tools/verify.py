#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""校验 data/ 的完整性与自洽性。有问题就红，没问题就绿。

这是全组共用的「裁判」：谁的 PR 改坏了数据，跑一下就知道。
不联网、不装库，只用标准库。

用法：
    python tools/verify.py            # 全部检查
    python tools/verify.py -v         # 连通过项也打印

退出码：0 = 全绿，1 = 有 FAIL（CI 靠这个拦合并）
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

REQUIRED = ["id", "stem", "ch", "name", "brief", "file", "lines", "note"]

results = []


def check(name, fn):
    try:
        detail = fn()
        results.append(("PASS", name, detail or ""))
    except AssertionError as e:
        results.append(("FAIL", name, str(e)))
    except Exception as e:  # noqa: BLE001
        results.append(("FAIL", name, "%s: %s" % (type(e).__name__, e)))


def load():
    def r(fn):
        p = DATA / fn
        if not p.exists():
            raise SystemExit("缺少 data/%s，先跑 python tools/extract.py" % fn)
        return json.loads(p.read_text(encoding="utf-8"))
    return r("algos.json"), r("chapters.json"), r("layers.json"), \
        r("deps.json"), r("imgs.index.json"), r("meta.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ns = ap.parse_args()

    algos, chapters, layers, deps, imgs, meta = load()
    ids = [a["id"] for a in algos]
    img_paths = {i["path"] for i in imgs}

    # ---------- 1. 字段完整性 ----------
    def c_fields():
        bad = []
        for a in algos:
            miss = [k for k in REQUIRED if k not in a]
            if miss:
                bad.append("%s 缺 %s" % (a.get("id", "?"), "/".join(miss)))
        assert not bad, "; ".join(bad[:5])
        return "%d 条记录字段齐全" % len(algos)
    check("字段完整性", c_fields)

    # ---------- 2. id 唯一 ----------
    def c_unique():
        dup = [k for k, v in Counter(ids).items() if v > 1]
        assert not dup, "重复 id：%s" % dup
        return "%d 个 id 无重复" % len(ids)
    check("id 唯一", c_unique)

    # ---------- 3. 章节归属存在 ----------
    def c_chapters():
        bad = sorted({a["ch"] for a in algos if a["ch"] not in chapters})
        assert not bad, "算法挂在不存在的章节上：%s" % bad
        empty = sorted(set(chapters) - {a["ch"] for a in algos})
        assert not empty, "章节下没有任何算法：%s" % empty
        return "%d 章全部有归属" % len(chapters)
    check("章节归属", c_chapters)

    # ---------- 4. 层级合法 ----------
    def c_layers():
        n = len(layers)
        bad = [a["id"] for a in algos if not isinstance(a.get("layer"), int)
               or not 0 <= a["layer"] < n]
        assert not bad, "layer 越界的算法：%s" % bad[:5]
        return "全部落在 0..%d" % (n - 1)
    check("层级合法", c_layers)

    # ---------- 5. 图片引用可解析 ----------
    def c_imgs():
        bad = []
        for a in algos:
            for p in a.get("imgs") or []:
                if p not in img_paths:
                    bad.append("%s -> %s" % (a["id"], p))
        assert not bad, "引用了不存在的图：%s" % bad[:3]
        no_img = [a["id"] for a in algos if not a.get("imgs")]
        return "%d 张图全部可解析；%d 个算法无配图（%s）" % (
            len(img_paths), len(no_img), ", ".join(no_img) or "无")
    check("图片引用", c_imgs)

    # ---------- 6. 依赖边合法（含环检测） ----------
    def c_deps():
        idset = set(ids)
        bad = []
        for a, b in deps:
            if a not in idset or b not in idset:
                bad.append("%s->%s" % (a, b))
            if a == b:
                bad.append("自环 %s" % a)
        assert not bad, "非法依赖边：%s" % bad[:5]

        graph = {}
        for a, b in deps:
            graph.setdefault(a, []).append(b)
        seen, stack = set(), set()

        def walk(n):
            if n in stack:
                return True
            if n in seen:
                return False
            seen.add(n)
            stack.add(n)
            r = any(walk(m) for m in graph.get(n, []))
            stack.discard(n)
            return r

        cyc = [n for n in graph if walk(n)]
        assert not cyc, "依赖成环：%s" % cyc[:5]
        return "%d 条边，无环，两端都存在" % len(deps)
    check("依赖图", c_deps)

    # ---------- 7. 源码文件与记录一一对应 ----------
    def c_codes():
        code_dir = DATA / "codes"
        files = list(code_dir.rglob("*.c")) if code_dir.exists() else []
        expect = {(a["ch"], a["stem"] + ".c") for a in algos}
        got = {(p.parent.name, p.name) for p in files}
        miss = sorted(expect - got)
        extra = sorted(got - expect)
        assert not miss, "缺源文件：%s" % miss[:5]
        assert not extra, "多出未登记的源文件：%s" % extra[:5]
        return "%d 个 .c 与记录一一对应" % len(files)
    check("源文件齐全", c_codes)

    # ---------- 8. 声明行数 vs 实际行数（最容易发现数据漂移的一条） ----------
    def c_lines():
        bad = []
        for a in algos:
            p = DATA / "codes" / a["ch"] / (a["stem"] + ".c")
            if not p.exists():
                continue
            real = len(p.read_text(encoding="utf-8").splitlines())
            if real != a["lines"]:
                bad.append("%s 声明 %d 实际 %d" % (a["id"], a["lines"], real))
        if bad:
            raise AssertionError("%d 条行数对不上：%s" % (len(bad), "; ".join(bad[:4])))
        return "%d 条行数与源文件一致" % len(algos)
    check("行数一致性", c_lines)

    # ---------- 9. 编译 / 运行状态统计（不判红，只报告） ----------
    def c_status():
        comp = Counter(str(a.get("compile")) for a in algos)
        run = Counter(str(a.get("run")) for a in algos)
        fail = [a["id"] for a in algos if a.get("compile") != "OK"]
        slow = [a["id"] for a in algos if a.get("run") not in ("OK", "")]
        return "compile %s | run %s | 待修：%s" % (
            dict(comp), dict(run), ", ".join(fail + slow) or "无")
    check("编译运行状态", c_status)

    # ---------- 10. 备注（note）可用 ----------
    def c_note():
        bad = []
        for a in algos:
            n = a.get("note") or {}
            if not n.get("steps") and not n.get("detail"):
                bad.append(a["id"])
        assert not bad, "note 为空的算法：%s" % bad[:5]
        with_steps = sum(1 for a in algos if (a.get("note") or {}).get("steps"))
        return "%d 条有 note，其中 %d 条带分步讲解" % (len(algos), with_steps)
    check("备注可用", c_note)

    # ---------- 11. 渲染层能真实产出完整页面（防 render.py 被改坏） ----------
    def c_render():
        """旧版这一项校验的是 8 MB 单文件 index.html 里的 DATA 块。
        改成 Python 现场渲染后，正文不再是磁盘上的文件，所以改成「真跑一次渲染」：
        页面里必须覆盖全部 76 条算法，并且不许出现绝对外链（课程要求用相对路径）。"""
        sys.path.insert(0, str(ROOT))
        from eg import render
        from eg.store import Archive

        ar = Archive(ROOT)  # Archive 内部自己拼 root/data
        html = render.index_page(ar, "", "", interactive=False)

        # 首页图谱只铺「精讲」节点（全量 76 条在"全部源码"列表页），所以查 core
        core_ids = set(a["id"] for a in ar.core)
        missing = sorted(i for i in core_ids if i not in html)
        assert not missing, "首页图谱里没有这些精讲节点：%s" % missing[:5]
        assert str(len(ids)) in html, "首页统计里没出现算法总数 %d" % len(ids)

        # 允许三个绝对地址：数据来源里的 hello-algo 仓库、以及 SVG 必需的命名空间
        probe = html
        for safe in ("https://github.com/krahets/hello-algo",
                     "http://www.w3.org/2000/svg",
                     "http://www.w3.org/1999/xlink"):
            probe = probe.replace(safe, "")
        leaked = [m for m in ("http://", "https://") if m in probe]
        assert not leaked, "渲染结果里出现绝对外链：%s" % leaked

        return "首页铺满 %d 个精讲节点，总数 %d 条，无绝对外链" % (len(core_ids), len(ids))
    check("渲染完整", c_render)

    # ---------- 12. JSON 接口可用 ----------
    # 踩过的坑：重构后 app.py 还在调 render.algo_brief()，函数已经没了，
    # /api/* 全 500，页面却一切正常，肉眼根本发现不了。这里盯死它。
    def c_api():
        import re
        from eg import render as R
        from eg.store import Archive

        a = Archive(ROOT).algos[0]
        brief = R.algo_brief(a)
        for k in ("id", "name", "chapter", "core", "brief"):
            assert k in brief, "algo_brief 少了字段 %s" % k

        full = R.algo_full(Archive(ROOT), a)
        assert str(full.get("code") or "").strip(), "algo_full 没带出源码"
        assert "deps_from" in full and "deps_to" in full, "algo_full 少了依赖边"

        src = (ROOT / "eg" / "app.py").read_text(encoding="utf-8")
        refs = set(re.findall(r"render\.([a-zA-Z_][a-zA-Z0-9_]*)", src))
        missing = sorted(n for n in refs if not hasattr(R, n))
        assert not missing, "app.py 调了 render 里不存在的函数：%s" % missing

        return "两条接口字段齐全；app.py 引用的 %d 个 render 函数都存在" % len(refs)

    check("接口可用", c_api)

    # ---------- 汇总 ----------
    n_fail = sum(1 for r in results if r[0] == "FAIL")
    print("=" * 60)
    for st, name, detail in results:
        if st == "PASS" and not ns.verbose:
            print("  PASS  %-14s" % name)
        else:
            print("  %s  %-14s %s" % (st, name, detail))
    print("=" * 60)
    print(" 汇总：PASS %d  /  FAIL %d" % (len(results) - n_fail, n_fail))
    if n_fail:
        print(" 有 %d 项没通过，看上面 FAIL 那几行的具体说明。" % n_fail)
    else:
        print(" 全绿。可以提 PR 了。")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
