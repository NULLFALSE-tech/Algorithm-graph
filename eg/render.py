# -*- coding: utf-8 -*-
"""渲染层：用 Python 拼出整站 HTML。

设计取向（也是这个项目最大的改动）：
原来的 index.html 把数据塞进 <script id="DATA">，再由浏览器 JS 拼 DOM。
现在所有 HTML 都在服务端由 Python 生成，前端只剩几十行代码处理悬停高亮。
好处：
  1. 每个算法有独立 URL（/a/array），能直接分享、能被搜索引擎收录。
  2. 关掉 JS 照样能看（老师演示的电脑不一定允许脚本）。
  3. 「用 Python 写界面」这件事在代码里是看得见的，不是一句声称。
"""

import html as _html
import json

from .codeview import render_code
from .graph import columns, edges, layout, _num


def json_dumps(obj):
    """统一的 JSON 出口：不转义中文，方便直接肉眼核对接口返回。"""
    return json.dumps(obj, ensure_ascii=False, indent=2)


def search_form(q, action, interactive):
    """搜索框。静态导出时改成一句说明——表单没有后端可提交，点了只会让人困惑。"""
    if not interactive:
        return ('<div class="search-note">静态预览版：搜索与章节筛选需要后端，'
                '回项目根目录运行 <code>python app.py</code> 即可使用</div>')
    return ('<form class="search-form" method="get" action="%s" style="flex:1;display:flex">'
            '<input class="search" name="q" value="%s" '
            'placeholder="搜算法名、文件名、关键词，回车筛选" autocomplete="off">'
            '</form>') % (action, esc(q))


def error_page(code, title, detail=""):
    """出错页。刻意做得极简：不依赖样式表，样式表挂了也能看。"""
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%d · %s</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:#f6f8fa;color:#1f2328;
  font:16px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.box{max-width:560px;padding:40px 44px;background:#fff;border:1px solid #d0d7de;border-radius:14px}
.code{font:600 44px/1 Consolas,monospace;color:#0969da;margin:0 0 10px}
h1{margin:0 0 12px;font-size:20px}
p{margin:0 0 18px;color:#59636e}
code{background:#eff2f5;padding:2px 6px;border-radius:4px;font-family:Consolas,monospace;font-size:14px}
a{color:#0969da;text-decoration:none;font-size:14px}
a:hover{text-decoration:underline}
</style></head><body><div class="box">
<div class="code">%d</div>
<h1>%s</h1>
<p>%s</p>
<a href="/">← 回知识图谱</a> &nbsp;·&nbsp; <a href="/all">全部源码</a>
</div></body></html>""" % (code, esc(title), code, esc(title), detail)


def esc(s):
    """统一转义，避免每处都写 html.escape。"""
    return _html.escape(str("" if s is None else s), quote=True)


# ---------------------------------------------------------------- 通用块

def stats_html(ar):
    s = ar.stats()
    items = [
        ("算法节点", s["core"]),
        ("全部源码", s["total"]),
        ("编译通过", s["compile_ok"]),
        ("实跑通过", s["run_ok"]),
        ("原版图解", s["images"]),
        ("章节", s["chapters"]),
    ]
    return "".join(
        '<span class="stat"><b>%s</b>%s</span>' % (v, esc(k)) for k, v in items
    )


def chips_html(ar, active="", link=True):
    """章节筛选标签。静态导出时 link=False，渲染成不可点的 span，避免点了没反应。"""
    tag = "a" if link else "span"
    href = ' href="/"' if link else ""
    out = ['<%s class="chip%s"%s>全部章节</%s>' % (tag, "" if active else " on", href, tag)]
    for ch in ar.chapter_keys:
        meta = ar.chapters[ch]
        on = " on" if ch == active else ""
        href = ' href="/?ch=%s"' % esc(ch) if link else ""
        out.append('<%s class="chip%s"%s>%s</%s>' % (tag, on, href, esc(meta[0]), tag))
    return "".join(out)


def svg_html(ar):
    """把图谱算成 SVG 字符串。坐标全由 Python 计算。"""
    n = len(ar.layers)
    pos, width, height = layout(ar.core, n)

    parts = [
        '<svg id="kg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">'
        % (width, height)
    ]

    for i, col in enumerate(columns(n, height)):
        parts.append(
            '<rect class="col" x="%s" y="%s" width="%s" height="%s" rx="8"/>'
            % (_num(col["rect_x"]), _num(col["rect_y"]),
               _num(col["rect_w"]), _num(col["rect_h"]))
        )
        parts.append(
            '<text class="lt" x="%s" y="%s">%s</text>'
            % (_num(col["title_x"]), _num(col["title_y"]), esc(ar.layers[i]))
        )

    for cls, s, t, d in edges(ar.deps, pos, ar.by_id):
        parts.append(
            '<path class="%s" data-s="%s" data-t="%s" d="%s"/>' % (cls, esc(s), esc(t), d)
        )

    for a in ar.core:
        x, y = pos[a["id"]]
        parts.append(
            '<a class="node" href="/a/%s" data-id="%s" transform="translate(%s,%s)">'
            '<rect width="180" height="46" rx="7"/>'
            '<text class="nt" x="12" y="20">%s</text>'
            '<text class="ns" x="12" y="36">%s.c</text></a>'
            % (esc(a["id"]), esc(a["id"]), _num(x), _num(y),
               esc(a["name"]), esc(a["stem"]))
        )

    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- JSON 接口
# 正文页面全是服务端渲染好的，这两条只服务 /api/*，给想自己写脚本抓数据的人用。

def algo_brief(a):
    """搜索结果的精简字段：够画一张卡片，不带源码全文、不带运行输出。"""
    return {
        "id": a["id"],
        "name": a["name"],
        "stem": a["stem"],
        "chapter": a["ch"],
        "layer": a.get("layer"),
        "core": bool(a.get("core")),
        "lines": a.get("lines", 0),
        "brief": a.get("brief", ""),
        "compile": a.get("compile"),
        "imgs": len(a.get("imgs") or []),
    }


def algo_full(ar, a):
    """单条算法的全量字段：源码、备注、配图、依赖边、编译运行结果。"""
    edges = ar.deps or []
    return {
        "id": a["id"],
        "name": a["name"],
        "stem": a["stem"],
        "chapter": a["ch"],
        "chapter_title": ar.chapter_title(a["ch"]),
        "layer": a.get("layer"),
        "layer_name": ar.chapter_layer(a["ch"]),
        "core": bool(a.get("core")),
        "lines": a.get("lines", 0),
        "brief": a.get("brief", ""),
        "compile": a.get("compile"),
        "run": a.get("run"),
        "err": a.get("err") or "",
        "output": a.get("out") or [],
        "note": a.get("note"),
        "imgs": a.get("imgs") or [],
        "code": ar.code_text(a["id"]),
        "deps_from": [b for s, b in edges if s == a["id"]],
        "deps_to": [s for s, b in edges if b == a["id"]],
    }


def card_html(a, ch_name):
    tags = ['<span class="tag %s">%s</span>' % ("core" if a["core"] else "", "精讲" if a["core"] else "导读")]
    if a.get("compile") == "OK":
        tags.append('<span class="tag ok">编译通过</span>')
    else:
        tags.append('<span class="tag no">库文件</span>')
    if a.get("imgs"):
        tags.append('<span class="tag">含图解</span>')

    return (
        '<a class="card" href="/a/%s"><h3>%s</h3>'
        '<div class="fn">%s.c · %d 行</div><p>%s</p>%s</a>'
        % (esc(a["id"]), esc(a["name"]), esc(a["stem"]), a.get("lines", 0),
           esc(a.get("brief", "")), "".join(tags))
    )


def list_html(ar, items=None):
    """按章节分组的源码清单。items 传过滤后的子集，不传就全显示。"""
    pool = ar.core_list() if items is None else items
    if not pool:
        return ('<div class="note">没有匹配的源码。可能是关键词打错了，'
                '也可能是把范围缩到了某一章——<a href="/all">看全部 76 条</a>再试一次。</div>')

    out = ['<div class="count-note" style="font:400 13px system-ui,-apple-system,sans-serif;'
           'color:var(--ink3);margin:0 0 10px">共 %d 条，当前显示 %d 条</div>'
           % (len(ar.algos), len(pool))]
    for ch in ar.chapter_keys:
        meta = ar.chapters[ch]
        group = [a for a in pool if a.get("ch") == ch]
        if not group:
            continue
        out.append(
            '<h2 class="sec">%s <span style="font:400 12px Consolas,monospace;'
            'color:var(--ink3)">%s</span></h2><div class="grid">'
            % (esc(meta[0]), esc(meta[2]) if len(meta) > 2 else "")
        )
        for a in group:
            out.append(card_html(a, meta[0]))
        out.append("</div>")
    return "".join(out)


def note_html(note):
    """「这段代码怎么跑」的三列表格 + 讲解段 + 比喻。"""
    if not note:
        return ""
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (esc(r[0]), esc(r[1]), esc(r[2] if len(r) > 2 else ""))
        for r in note.get("steps", [])
    )
    paras = "".join(
        "<p>%s</p>" % esc(p) for p in note.get("detail", "").split("\n\n") if p.strip()
    )
    return (
        '<h4>这段代码到底怎么跑 <span class="n">%s</span></h4>'
        '<table class="st"><thead><tr><th>阶段</th><th>代码在做什么</th>'
        '<th>变量与内存怎么变</th></tr></thead><tbody>%s</tbody></table>'
        '<div class="explain" style="margin-top:16px">%s</div>'
        '<div class="note"><b>打个比方：</b>%s<br><b>跑多快：</b>%s</div>'
        % (esc(note.get("kind", "")), rows, paras,
           esc(note.get("analogy", "")), esc(note.get("cost", "")))
    )


def figs_html(ar, a):
    if not a.get("imgs"):
        return ('<h4>原版图解</h4><div class="note">'
                '本章没有与该源码文件名对应的官方图解，未做替代配图。</div>')
    figs = "".join(
        '<figure><a href="/img/%s" target="_blank">'
        '<img src="/img/%s" alt="%s" loading="lazy"></a>'
        '<figcaption>%s</figcaption></figure>'
        % (esc(p), esc(p), esc(p), esc(p.split("/")[-1]))
        for p in a["imgs"]
    )
    return ('<h4>原版图解 <span class="n">hello-algo docs / 官方 SVG</span></h4>'
            '<div class="figs">%s</div>' % figs)


def output_html(a):
    """实跑输出。三种「没有输出」的情形要分开说，不能一律显示成失败。"""
    if a.get("out"):
        return '<pre class="out">%s</pre>' % esc("\n".join(a["out"]))
    if a.get("run") == "TIMEOUT":
        msg = "这份源码故意跑大数据量演示复杂度，6 秒内未结束，已中止；不是错误。"
    elif a.get("compile") != "OK":
        msg = "该文件没有 main()，只提供函数给同章其它文件调用，无法单独链接运行。"
    else:
        msg = "未取到输出"
    return '<pre class="out"><span class="empty">%s</span></pre>' % esc(msg)


def detail_body(ar, a):
    """详情正文。抽屉和独立页共用同一份，保证两处不会走样。"""
    ch_meta = ar.chapters.get(a.get("ch", ""), [""])
    tags = ['<span class="tag %s">%s</span>' % (
        "core" if a["core"] else "", (a.get("note") or {}).get("kind", "源码"))]
    if a.get("compile") == "OK":
        tags.append('<span class="tag ok">gcc 编译通过</span>')
    else:
        tags.append('<span class="tag no">无 main，库文件</span>')
    if a.get("run") == "OK":
        tags.append('<span class="tag ok">实跑通过</span>')
    if a.get("imgs"):
        tags.append('<span class="tag">%d 张官方图解</span>' % len(a["imgs"]))

    code = render_code(ar.code_text(a["id"]))
    winpath = a.get("winpath", "")

    return (
        '<div id="dTags" style="margin-bottom:14px">%s</div>'
        '<p class="brief">%s</p>'
        '%s'
        '<h4>真实 C 代码 <span class="n">逐字节取自仓库，未改写</span></h4>'
        '<div class="codebox"><div class="codebar"><span>%s</span></div>'
        '<pre class="code">%s</pre></div>'
        '%s'
        '<h4>本机实跑输出 <span class="n">gcc 16.2.0 编译后真实 stdout</span></h4>'
        '%s'
        '<h4>在本机跑一遍</h4><div class="runbox">'
        '<p>前置条件：把 hello-algo 仓库 clone 到<b>与本项目同级</b>的目录，'
        '并装好 MSYS2（UCRT64）与 gcc。然后在 PowerShell 里执行：</p>'
        '<code>cd ..\\hello-algo</code>'
        '<code>.\\run-c.cmd %s</code>'
        '<p>若输出中文乱码，先在 PowerShell 执行 '
        '<code>[Console]::OutputEncoding = [System.Text.Encoding]::UTF8</code>。'
        '源码本身是 UTF-8，不要加 <code>-fexec-charset=GBK</code>。</p></div>'
        % ("".join(tags), esc(a.get("brief", "")), figs_html(ar, a),
           esc(winpath), code, note_html(a.get("note")), output_html(a),
           esc(winpath))
    )


# ---------------------------------------------------------------- 整页

# 详情页要用的补充样式：原 CSS 是围绕「右侧抽屉」写的，
# 独立页把同样的内容放进主区域，需要把宽度和滚动条改掉。
_EXTRA_CSS = """
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:26px 28px;margin:22px 0 40px}
.panel .dbody{padding:0;overflow:visible}
.panel h2{margin:0 0 6px;font-size:26px}
.crumb{font:13px/1.6 Consolas,monospace;color:var(--ink3);margin-bottom:4px}
.pager{display:flex;gap:10px;margin:26px 0 0;flex-wrap:wrap}
.pager a{font-size:13px;color:var(--ink2);text-decoration:none;
  border:1px solid var(--line);border-radius:7px;padding:7px 12px;background:#fff}
.pager a:hover{border-color:#c9d1d9;color:var(--ink)}
a.node{cursor:pointer}
.search-note{flex:1;font-size:13px;color:var(--ink3);border:1px dashed var(--line);
  border-radius:8px;padding:9px 13px;background:#fff;line-height:1.6}
.search-note code{font-family:Consolas,monospace;background:#eff2f5;
  padding:1px 5px;border-radius:4px;font-size:12px}
"""

_HEAD = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<link rel="stylesheet" href="/static/style.css">
<style>%s</style>
</head><body>
"""

_FOOT = """
<div class="foot">
  <p><b>代码来源</b> hello-algo 仓库 <code>codes/c/</code> 目录，逐文件读取原文，没有改写、没有补全、没有示例代码。<b>图解来源</b> 同一仓库 <code>docs/</code> 下的官方 SVG。</p>
  <p><b>实跑标注</b> 「编译通过 / 实跑输出」由本机 MSYS2 UCRT64 GCC 16.2.0 逐个 gcc 编译并运行抓取；没有 main 的库文件与故意跑大数据量的复杂度演示会如实标注，不当作失败也不伪造输出。</p>
  <p><b>许可</b> hello-algo 采用 CC BY-NC-SA 4.0，自学自改可以，不能商用；二次分发需署名并同协议共享。</p>
  <p>%s</p>
</div>
</body></html>
"""

# 前端只剩悬停高亮这一点逻辑，其余全在服务端完成
_JS = """
(function(){
  var kg=document.getElementById('kg'); if(!kg) return;
  kg.addEventListener('mouseover',function(e){
    var g=e.target.closest('.node'); if(!g) return;
    var id=g.dataset.id;
    kg.querySelectorAll('.edge').forEach(function(p){
      p.classList.toggle('hi', p.dataset.s===id || p.dataset.t===id);
    });
  });
  kg.addEventListener('mouseout',function(e){
    if(!e.target.closest('.node')) return;
    kg.querySelectorAll('.edge').forEach(function(p){ p.classList.remove('hi'); });
  });
})();
"""


def index_page(ar, q="", ch="", interactive=True):
    """图谱主页。q/ch 来自 URL，过滤在服务端做完再吐 HTML。"""
    s = ar.stats()
    # 服务端过滤：命中的节点在图谱里高亮，未命中的淡化
    hits = ar.search(q) if q else ar.core_list()
    dim = set()
    if q or ch:
        keep = {a["id"] for a in hits if (not ch or a.get("ch") == ch)}
        dim = {a["id"] for a in ar.core_list() if a["id"] not in keep}

    svg = svg_html(ar)
    if dim:
        # 给未命中的节点打上 dim 类，前端一行都不用管
        for aid in dim:
            svg = svg.replace(
                '<a class="node" href="/a/%s" data-id="%s"' % (esc(aid), esc(aid)),
                '<a class="node dim" href="/a/%s" data-id="%s"' % (esc(aid), esc(aid)),
            )

    hint = ""
    if q or ch:
        hint = '<span class="hint">命中 %d 份源码（图谱只显示精讲节点）</span>' % len(hits)

    return _HEAD % ("C 语言算法知识图谱", _EXTRA_CSS) + """
<header class="hero"><div class="hero-in">
  <div class="kicker">hello-algo / 本地源码与官方图解</div>
  <h1>C 语言算法知识图谱</h1>
  <p class="lede">按学习顺序把算法连成一张图。点开任意一个节点：先看 hello-algo 原版图解，再看仓库里一字未改的真实 C 代码，紧接着是这段代码到底怎么跑，最后是本机实跑抓到的输出。</p>
  <div class="stats">%s</div>
</div></header>
<div class="bar"><div class="bar-in">
  %s
  <a class="seg" href="/all" style="text-decoration:none"><button>全部源码</button></a>
  %s
</div></div>
<div class="wrap">
  <div class="chips">%s</div>
  <section>
    <div class="graphcard">%s
    <div class="legend">连线表示建议的学习先后，不是数学依赖：跨层的曲线从左指向右，同列左侧的弧线表示这一层内部也有先后。图谱只画带精讲的 %d 个主干节点；「全部源码」可看全部 %d 份。</div></div>
  </section>
</div>
""" % (stats_html(ar), search_form(q, "/", interactive), hint,
                   chips_html(ar, ch, interactive), svg, s["core"], s["total"]) \
        + _FOOT % ("生成时间 %s · 页面由 Python 服务端渲染 · 共 %d 张官方图解"
                   % (s["generated"], s["images"])) + "<script>%s</script>" % _JS


def all_page(ar, q="", interactive=True):
    """全部源码清单页。同样是服务端过滤 + 服务端渲染。"""
    hits = ar.search(q) if q else ar.core_list()
    return _HEAD % ("全部源码 · C 语言算法知识图谱", _EXTRA_CSS) + """
<header class="hero"><div class="hero-in">
  <div class="kicker">hello-algo / codes/c</div>
  <h1>全部源码 · %d 份</h1>
  <p class="lede">按章节列出仓库里的每一份 C 代码。带「精讲」标记的会出现在图谱里。</p>
  <div class="stats">%s</div>
</div></header>
<div class="bar"><div class="bar-in">
  %s
  <a class="seg" href="/" style="text-decoration:none"><button>回图谱</button></a>
</div></div>
<div class="wrap">%s</div>
""" % (len(ar.algos), stats_html(ar), search_form(q, "/all", interactive), list_html(ar, hits)) \
        + _FOOT % ("页面由 Python 服务端渲染") + ""


def detail_page(ar, a, interactive=True):
    """单个算法的独立页。URL 可分享，无 JS 也能读。"""
    core = ar.core_list()
    ids = [x["id"] for x in core]
    prev_a = next_a = None
    if a["id"] in ids:
        i = ids.index(a["id"])
        prev_a = core[(i - 1) % len(core)]
        next_a = core[(i + 1) % len(core)]

    pager = ['<a href="/all">← 全部源码</a>', '<a href="/">← 回图谱</a>']
    if prev_a:
        pager.append('<a href="/a/%s">← 上一个：%s</a>' % (esc(prev_a["id"]), esc(prev_a["name"])))
    if next_a:
        pager.append('<a href="/a/%s">下一个：%s →</a>' % (esc(next_a["id"]), esc(next_a["name"])))

    return _HEAD % ("%s · C 语言算法知识图谱" % a["name"], _EXTRA_CSS) + """
<div class="wrap">
  <div class="panel">
    <div class="crumb">%s</div>
    <h2>%s</h2>
    <div class="fn" style="color:var(--ink3);font:13px Consolas,monospace;margin-bottom:16px">%s · %d 行</div>
    <div class="dbody">%s</div>
    <div class="pager">%s</div>
  </div>
</div>
""" % (esc(a.get("file", "")), esc(a["name"]), esc(a.get("file", "")),
       a.get("lines", 0), detail_body(ar, a), "".join(pager)) \
        + _FOOT % ("页面由 Python 服务端渲染")
