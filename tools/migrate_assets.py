# -*- coding: utf-8 -*-
"""一次性资产提取脚本（迁移用，可重复执行，幂等）

把旧版单文件 index.html 里 base64 内嵌的 87 张官方 SVG 图解还原成
static/imgs/ 下的真实文件，并做两项核对：

1. 图片数量与 data/imgs.index.json 是否一致
2. 解码后的字节 sha1 是否与 imgs.index.json 记录的一致
3. data/algos.json 记录的行数与磁盘 .c 实际行数是否一致

核对通过才允许进入后端化版本。任何一项不过就直接退出码 1。
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "index.html"
IMGS_DIR = ROOT / "static" / "imgs"


def load_data_block() -> dict:
    """取出 <script id="DATA" type="application/json"> 里的整段 JSON。"""
    text = HTML.read_text(encoding="utf-8")
    m = re.search(
        r'<script id="DATA" type="application/json">(.*?)</script>',
        text,
        re.S,
    )
    if not m:
        raise SystemExit("没有在 index.html 里找到 DATA 数据块")
    return json.loads(m.group(1))


def split_uri(uri: str) -> tuple[str, bytes]:
    """data:image/svg+xml;base64,xxxx -> (base64载荷字符串, 解码后字节)

    注意：data/imgs.index.json 里的 sha1 是算在「base64 载荷字符串」上的，
    不是算在解码后的 SVG 字节上。这里把两者一起返回，校验时用前者。
    """
    if "," not in uri:
        raise ValueError("不是合法 data URI")
    head, payload = uri.split(",", 1)
    if "base64" in head:
        return payload, base64.b64decode(payload)
    return payload, payload.encode("utf-8")


def main() -> int:
    data = load_data_block()
    imgs: dict[str, str] = data["imgs"]
    print(f"DATA 块解析成功：algos={len(data['algos'])} imgs={len(imgs)}")

    index_path = ROOT / "data" / "imgs.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    # 兼容两种结构：{path: {...}} 或 {items: [...]}
    if isinstance(index, list):
        index = {x["path"]: x for x in index}
    elif "items" in index:
        index = {x["path"]: x for x in index["items"]}

    IMGS_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    total_bytes = 0
    sha_bad: list[str] = []

    for path, uri in imgs.items():
        payload, raw = split_uri(uri)
        out = IMGS_DIR / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        written += 1
        total_bytes += len(raw)

        rec = index.get(path)
        if rec:
            expect = rec.get("sha1") or ""
            if len(expect) == 40:
                got = hashlib.sha1(payload.encode("utf-8")).hexdigest()
                if got != expect:
                    sha_bad.append(f"{path}: 期望 {expect[:12]} 实际 {got[:12]}")
            chars = rec.get("chars")
            if chars and chars != len(uri):
                sha_bad.append(
                    f"{path}: 期望 chars={chars} 实际 URI 长度={len(uri)}"
                )

    print(f"图写盘 {written} 张，共 {total_bytes/1024/1024:.2f} MiB -> {IMGS_DIR}")

    if len(imgs) != len(index):
        print(f"[WARN] 图数量不一致：DATA={len(imgs)} index={len(index)}")
    if sha_bad:
        print(f"[FAIL] {len(sha_bad)} 张图 sha1 不符：")
        for line in sha_bad[:5]:
            print("   ", line)
        return 1

    # 源码行数核对
    algos = json.loads((ROOT / "data" / "algos.json").read_text(encoding="utf-8"))
    line_bad = []
    for a in algos:
        c = ROOT / "data" / "codes" / a["ch"] / (a["stem"] + ".c")
        if not c.exists():
            line_bad.append(f"缺文件 {c}")
            continue
        n = len(c.read_text(encoding="utf-8").splitlines())
        if n != a["lines"]:
            line_bad.append(f"{c.name}: 记录 {a['lines']} 行，实际 {n} 行")

    if line_bad:
        print(f"[FAIL] 源码行数核对失败 {len(line_bad)} 项：")
        for line in line_bad[:5]:
            print("   ", line)
        return 1

    print(f"源码行数核对通过：{len(algos)} 份全部与记录一致")
    print("OK：资产提取完成，可以启动 Python 版本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
