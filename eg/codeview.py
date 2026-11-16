# -*- coding: utf-8 -*-
"""C 源码的逐行着色。

为什么不用一串正则反复 replace：
    那样会出「套娃」——先把 "int" 包成 <span class="t-str">"int"</span>，
    下一轮关键字正则又把 span 里的 int 再包一层，最后 HTML 嵌套错乱。
    单遍扫描一次读完一行，token 边界天然互斥，不会重入。

这一条也是迁移时对原单文件版做的修正（原版就是连续 replace 的写法）。
"""

import re

KEYWORDS = frozenset("""
int void char bool float double long short unsigned signed size_t
struct union enum typedef return if else for while do break continue
const static extern register auto volatile sizeof NULL true false
include define switch case default goto inline
""".split())

_BLOCK_OPEN = re.compile(r"^\s*/\*")
_BLOCK_MID = re.compile(r"^\s*\*")  # 块注释的中间行，习惯上也当注释

CLASS_OF = {
    "cm": "t-cm",
    "str": "t-str",
    "kw": "t-kw",
    "num": "t-num",
}


def esc(s):
    """只转义会和 HTML 冲突的三个字符，和原版的 esc() 行为一致。"""
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tokenize(line):
    """把一行 C 代码切成 [(kind, text)]，kind ∈ {code, kw, num, str, cm}。"""
    out = []
    buf = []

    def flush():
        if buf:
            out.append(("code", "".join(buf)))
            del buf[:]

    i = 0
    n = len(line)
    while i < n:
        ch = line[i]

        # 行注释：// 之后整行都是注释
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            flush()
            out.append(("cm", line[i:]))
            return out

        # 块注释：/* ... */，同一行内闭合就继续扫，否则吞到行尾
        if ch == "/" and i + 1 < n and line[i + 1] == "*":
            flush()
            close = line.find("*/", i + 2)
            if close < 0:
                out.append(("cm", line[i:]))
                return out
            out.append(("cm", line[i:close + 2]))
            i = close + 2
            continue

        # 字符串 / 字符字面量：整体吃掉，内部不参与任何着色
        if ch == '"' or ch == "'":
            flush()
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == ch:
                    j += 1
                    break
                j += 1
            out.append(("str", line[i:j]))
            i = j
            continue

        # 标识符 / 数字
        if ch.isalnum() or ch == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            flush()
            if word[0].isdigit():
                out.append(("num", word))
            elif word in KEYWORDS:
                out.append(("kw", word))
            else:
                out.append(("code", word))
            i = j
            continue

        buf.append(ch)
        i += 1

    flush()
    return out


def highlight_line(line):
    if _BLOCK_OPEN.match(line) or _BLOCK_MID.match(line):
        return '<span class="t-cm">%s</span>' % esc(line)

    parts = []
    for kind, text in tokenize(line):
        if kind == "code":
            parts.append(esc(text))
        else:
            parts.append('<span class="%s">%s</span>' % (CLASS_OF[kind], esc(text)))
    return "".join(parts)


def render_code(code_text):
    """整段源码 → 带行号的 HTML 行序列。

    用 splitlines() 而不是 split("\\n")：后者遇到文件末尾换行会多出一个空行，
    行号会虚增一行，和 verify.py 统计出来的 lines 对不上。
    """
    rows = []
    for i, line in enumerate(code_text.splitlines(), 1):
        rows.append(
            '<span class="row"><span class="ln">%d</span>%s</span>'
            % (i, highlight_line(line))
        )
    return "".join(rows)


def stats(code_text):
    """给文档和演示用的小统计。"""
    lines = code_text.splitlines()
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if _BLOCK_OPEN.match(l) or _BLOCK_MID.match(l))
    return {
        "lines": len(lines),
        "blank": blank,
        "comment": comment,
        "chars": len(code_text),
    }
