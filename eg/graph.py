# -*- coding: utf-8 -*-
"""图谱布局：把「层 + 章 + 依赖边」算成屏幕坐标。

原单文件版是在浏览器里用 JS 算的，这里原样搬到 Python。
公式一致，所以生成的 SVG 和原来像素级相同（这一条在 tests 里有断言）。
"""

# 画布常量，调这几个数就能整体改版式
LAYER_W = 244      # 相邻两层的水平间距
NODE_W = 180       # 节点宽
NODE_H = 46        # 节点高
NODE_GAP = 16      # 同层节点上下间距
PAD_X = 60         # 左右留白
PAD_Y = 96         # 顶部留白（给层标题）


def _num(v):
    """浮点转成短字符串：96.0 -> 96，22.5 -> 22.5。"""
    if isinstance(v, float):
        s = "%.2f" % v
        s = s.rstrip("0").rstrip(".")
        return "0" if s in ("", "-0") else s
    return str(v)


def layout(core, n_layers):
    """计算每个精讲节点的坐标。

    返回 (pos, width, height)：
        pos   {algo_id: (x, y)}，均已乘好列宽/行高
    规则：
        第 i 层占第 i 列；同层节点在列内垂直居中，避免上层空着下层贴着顶。
    """
    groups = [[] for _ in range(n_layers)]
    for a in core:
        layer = a.get("layer", 0)
        if 0 <= layer < n_layers:
            groups[layer].append(a)

    max_n = max([len(g) for g in groups] or [0])
    height = PAD_Y + max_n * (NODE_H + NODE_GAP) + 36
    width = PAD_X * 2 + (n_layers - 1) * LAYER_W + NODE_W

    pos = {}
    for li, group in enumerate(groups):
        top = PAD_Y + (max_n - len(group)) * (NODE_H + NODE_GAP) / 2.0
        for k, a in enumerate(group):
            pos[a["id"]] = (PAD_X + li * LAYER_W, top + k * (NODE_H + NODE_GAP))
    return pos, width, height


def columns(n_layers, height):
    """每一层的背景条与标题位置。"""
    out = []
    for i in range(n_layers):
        x = PAD_X + i * LAYER_W
        out.append({
            "rect_x": x - 10,
            "rect_y": 60,
            "rect_w": NODE_W + 20,
            "rect_h": height - 76,
            "title_x": x + 4,
            "title_y": 38,
        })
    return out


def _bezier(x1, y1, x2, y2, c1x, c2x):
    return "M%s %s C%s %s,%s %s,%s %s" % (
        _num(x1), _num(y1), _num(c1x), _num(y1),
        _num(c2x), _num(y2), _num(x2), _num(y2),
    )


def edges(deps, pos, by_id):
    """依赖边 → [(css_class, 起点 id, 终点 id, path d)]。

    同层：向左拱一下，避免直线穿过节点。
    跨层：从节点右侧连到目标左侧，控制点按水平距离取一半。
    """
    out = []
    for pair in deps:
        s, t = pair[0], pair[1]
        if s not in pos or t not in pos:
            continue
        a = by_id.get(s)
        b = by_id.get(t)
        if not a or not b:
            continue

        ax, ay = pos[s]
        bx, by = pos[t]

        if a["layer"] == b["layer"]:
            x1, y1 = ax, ay + NODE_H / 2.0
            x2, y2 = bx, by + NODE_H / 2.0
            bow = min(44.0, 20.0 + abs(y2 - y1) * 0.1)
            d = _bezier(x1, y1, x2, y2, x1 - bow, x2 - bow)
        else:
            x1, y1 = ax + NODE_W, ay + NODE_H / 2.0
            x2, y2 = bx, by + NODE_H / 2.0
            c = max(40.0, (x2 - x1) / 2.0)
            d = _bezier(x1, y1, x2, y2, x1 + c, x2 - c)

        cls = "edge" + (" far" if b["layer"] - a["layer"] >= 2 else "")
        out.append((cls, s, t, d))
    return out


def graph_payload(archive):
    """给 /api/graph 用的纯数据版本（别人做二次开发时不至于去解析 SVG）。"""
    pos, width, height = layout(archive.core, len(archive.layers))
    nodes = []
    for a in archive.core:
        x, y = pos[a["id"]]
        nodes.append({
            "id": a["id"],
            "name": a["name"],
            "stem": a["stem"],
            "layer": a["layer"],
            "x": round(x, 2),
            "y": round(y, 2),
        })
    links = [{"s": s, "t": t} for s, t in archive.deps
             if s in pos and t in pos]
    return {
        "width": width,
        "height": height,
        "layers": archive.layers,
        "nodes": nodes,
        "links": links,
    }
