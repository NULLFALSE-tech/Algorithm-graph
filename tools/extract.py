#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 index.html 里把知识图谱数据抽出来，变成可以 diff 的独立文件。

为什么要有这一步：
    index.html 是 8.3 MB 的单文件，其中 96% 是 base64 内联的图片。
    直接在 Git 里改它，diff 完全看不出改了什么，review 就是摆设。
    所以把「数据」和「正文」分开：
        index.html   —— 给人看的成品，提交一次后基本不动
        data/        —— 可 diff、可 review、可测试的真数据

用法：
    python tools/extract.py              # 抽取并写入 data/
    python tools/extract.py --check      # 只校验，不写盘（CI 用）

产物：
    data/algos.json        76 条算法元数据，一条一行（diff 友好）
    data/chapters.json     13 章
    data/layers.json       5 层
    data/deps.json         算法之间的前置依赖
    data/meta.json         生成时间与统计
    data/imgs.index.json   87 张图的索引（路径 + 字节数 + sha1），不含图片本体
    data/codes/<章>/<算法>.c   76 个真实 C 源文件
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
DATA = ROOT / "data"

TAG = '<script id="DATA" type="application/json">'


def load_payload(index_path: Path) -> dict:
    """从 HTML 里取出内联 JSON。不用正则整段匹配——8 MB 的贪婪匹配会吃掉内存。"""
    text = index_path.read_text(encoding="utf-8", errors="replace")
    start = text.find(TAG)
    if start < 0:
        raise SystemExit("找不到 %s，确认 index.html 没被改坏" % TAG)
    start += len(TAG)
    end = text.find("</script>", start)
    if end < 0:
        raise SystemExit("DATA 块没有闭合的 </script>")
    return json.loads(text[start:end])


def one_line(obj) -> str:
    """把一条记录压成一行 JSON：Git diff 时能精确到「哪一条变了」。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def dump_lines(path: Path, head: str, rows, tail: str):
    """写成 [\\n{...},\\n{...}\\n] 的形式，一条一行。"""
    body = ",\n".join(rows)
    path.write_text("%s\n%s\n%s\n" % (head, body, tail), encoding="utf-8")


def extract(write: bool = True) -> dict:
    payload = load_payload(INDEX)
    algos = payload["algos"]
    imgs = payload.get("imgs") or {}

    # ---- 拆 code：源文件单独落地，正文里的 code 字段只保留行数 ----
    meta_rows = []
    code_files = []
    for a in algos:
        rec = {k: v for k, v in a.items() if k not in ("code", "imgs")}
        rec["imgs"] = list(a.get("imgs") or [])
        rec["code_lines"] = a.get("lines")
        meta_rows.append(one_line(rec))

        code = a.get("code")
        if code:
            rel = Path("codes") / a["ch"] / (a["stem"] + ".c")
            code_files.append((rel, code))

    # ---- 图片只留索引，不留 base64 ----
    img_rows = []
    for key in sorted(imgs):
        val = imgs[key]
        raw = val or ""
        # 值是 data:image/xxx;base64,... 或纯 svg 文本，两种都兼容
        payload_bytes = raw.split(",", 1)[1] if raw.startswith("data:") else raw
        img_rows.append(one_line({
            "path": key,
            "chars": len(raw),
            "sha1": hashlib.sha1(payload_bytes.encode("utf-8")).hexdigest(),
        }))

    if write:
        DATA.mkdir(exist_ok=True)
        dump_lines(DATA / "algos.json", "[", meta_rows, "]")
        dump_lines(DATA / "imgs.index.json", "[", img_rows, "]")
        (DATA / "chapters.json").write_text(
            json.dumps(payload.get("chapters", {}), ensure_ascii=False, indent=1),
            encoding="utf-8")
        (DATA / "layers.json").write_text(
            json.dumps(payload.get("layers", []), ensure_ascii=False, indent=1),
            encoding="utf-8")
        (DATA / "deps.json").write_text(
            json.dumps(payload.get("deps", []), ensure_ascii=False, indent=1),
            encoding="utf-8")
        (DATA / "meta.json").write_text(
            json.dumps(payload.get("meta", {}), ensure_ascii=False, indent=1),
            encoding="utf-8")

        for rel, code in code_files:
            p = DATA / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(code, encoding="utf-8")

    return {
        "algos": len(algos),
        "chapters": len(payload.get("chapters", {})),
        "layers": len(payload.get("layers", [])),
        "imgs": len(imgs),
        "codes": len(code_files),
        "code_lines": sum(a.get("lines") or 0 for a in algos),
        "deps": len(payload.get("deps", [])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只统计不写盘")
    ns = ap.parse_args()

    if not INDEX.exists():
        raise SystemExit("找不到 index.html：%s" % INDEX)

    st = extract(write=not ns.check)
    print("[抽取] %s" % ("统计模式" if ns.check else "已写入 data/"))
    print("  算法      %d 个" % st["algos"])
    print("  章节      %d 章 / %d 层" % (st["chapters"], st["layers"]))
    print("  图片      %d 张（仅索引）" % st["imgs"])
    print("  源文件    %d 个 / 声明 %d 行" % (st["codes"], st["code_lines"]))
    print("  依赖边    %d 条" % st["deps"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
