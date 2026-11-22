# AI 使用记录 · C 语言算法知识图谱

> 课程要求：记录**最具代表性的 3 次**提示词、AI 的原始输出、以及人工介入微调/修复的部分。
> 本组 6 人都用了 AI，下面先详录 3 个「AI 出错并被人工纠回」的完整案例，再按人简录其余 15 次，
> 保证每个人都能在提交历史里对上自己的那条记录。

**工具**：WorkBuddy（Claude / DeepSeek / Qwen 混用）、Trae、VS Code + Continue
**统计**：6 人 · 18 次有效交互 · 其中 **9 次 AI 输出有错**，全部由人工定位后修正

---

## 一、三个完整案例

### 案例 1 · P1 邓宇轩：让 AI 把 8.37 MB 单文件重构成 Python 包，它给了 Flask

**1. 我的提示词（原文）**

```
你是 Python 后端工程师。我有一个 8.37 MB 的静态单文件 index.html，里面内联了
<script id="DATA"> 的 JSON 和 87 张 base64 SVG。请把它重构成一个 Python 项目：
- 数据抽到 data/ 目录，图片落成独立文件
- 用 Web 框架提供服务，首页、列表页、详情页三个路由
- 页面 HTML 由服务端渲染，不要在前端用 JS 拼 DOM
约束：我们的课要在老师的电脑上现场演示，环境是 Windows + 学校发的 Python。
```

**2. AI 的原始输出（节选，全文 214 行）**

```python
from flask import Flask, render_template, abort
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html", algos=load_algos())

@app.route("/a/<algo_id>")
def detail(algo_id):
    algo = ALGOS.get(algo_id) or abort(404)
    return render_template("detail.html", algo=algo)
```
（配套还生成了 `requirements.txt`：`Flask==3.0.0`，以及 `templates/` 下 4 个 Jinja2 模板）

**3. 我怎么审查的**

- 打开 `requirements.txt` 第一行就是 `Flask==3.0.0`。**这是第三方包，而演示机的校园网装不上**——
  我在本机 `pip install flask` 试了一次，沙箱内直接超时；即便装上，老师机器上也得重来一遍。
- 更要命的是它把「服务端渲染」理解成「Jinja2 模板」，于是又多引入一个依赖（Jinja2）。
- 我逐行回它：**「只许用 Python 标准库。Flask 和 Jinja2 都不能出现，请用 http.server 重写路由，HTML 用 f-string 直接拼。」**

**4. 最后改成了什么**

`app.py` 变成 18 行的入口薄壳，`eg/app.py` 用 `http.server.BaseHTTPRequestHandler` 手写 8 条路由，
HTML 由 `eg/render.py` 里的 f-string 拼出。最终 `requirements.txt` **被删掉**——项目零依赖。

---

### 案例 2 · P1 邓宇轩：AI 生成的 render.py 里 `\n` 被写成 `/n`，模块直接 import 失败

**1. 我的提示词（原文）**

```
请在 render.py 里加一个 chips_html(ar, active) 函数，输出章节标签栏：
遍历 ar.chapter_keys，每个章节生成一个 <a class="chip">，当前章节加 active 类。
```

**2. AI 的原始输出（原文）**

```python
def chips_html(ar, active=""):
    out = []
    for ch in ar.chapter_keys:/n
        cls = "chip on" if ch == active else "chip"
        out.append('<a class="%s" href="/?ch=%s">%s</a>' % (cls, ch, ar.chapter_title(ch)))
    return "".join(out)
```

**3. 我怎么审查的**

- 跑 `python tools/verify.py` 直接报 `SyntaxError: invalid syntax`，位置在 `render.py:157`。
- 仔细看：`for ch in ar.chapter_keys:` 后面跟的是 **`/n`**，不是换行符 `
`。
  这是中文输入法/复制链路把反斜杠吃掉了。
- 更阴的是同一类错误在 `list_html` 里又出现一次（`:206`），因为两处是同一段 AI 输出复制的。
- 教训：**这类字符级错误不能靠肉眼扫，必须靠跑。** 我最初还想用 sed 批量替换，结果 Bash heredoc 层层转义反而把它改坏了，
  最后是用编辑器逐处 `Edit` 改回来的。

**4. 最后改成了什么**

两处 `/n` 改回真换行；并在 `tools/verify.py` 里加了第 11 条「渲染完整」——
它会**真的跑一次 `render.index_page()`**，语法错误在这一步就暴露，不用等浏览器。

---

### 案例 3 · P6 焦名远：AI 给的搜索高亮代码把用户输入直接插进 HTML

**1. 我的提示词（原文）**

```
请改 eg/render.py 的 list_html，让搜索结果高亮命中的关键词。
输入 q 来自 URL 参数，已经在 app.py 里 decode 过。
```

**2. AI 的原始输出（原文）**

```python
def hilite(text, q):
    if not q:
        return text
    return text.replace(q, '<mark>%s</mark>' % q)
```
（然后在 `card_html` 里直接 `hilite(a["brief"], q)`，返回值未转义就拼进 HTML）

**3. 我怎么审查的**

- AI 完全没有提转义。`q` 来自 `?q=`，攻击者可以传 `?q=<script>alert(1)</script>`，
  经 `hilite` 拼进页面就是**反射型 XSS**。
- 即便不考虑攻击，正常输入 `a<b` 也会把后面的排版吃掉。
- 我拿 `http://127.0.0.1:8770/all?q=%3Cscript%3Ealert(1)%3C/script%3E` 试了一次，页面上真的出现了可执行的 `<script>`。
- 我回它：**「q 必须先进 esc() 再进 replace，而且 replace 的替换串里的 q 也要 esc。」**

**4. 最后改成了什么**

```python
def hilite(text, q):
    text = esc(text)
    if not q:
        return text
    return text.replace(esc(q), "<mark>%s</mark>" % esc(q))
```
先整体转义、再对转义后的形式做替换，保证任何输入都不可能变成标签。

---

## 二、按人简录（其余 15 次）

| 成员 | 场景 | AI 输出的问题 | 人工怎么处理 |
|---|---|---|---|
| P1 邓宇轩 | 生成 `tools/verify.py` 第 11 项校验 | 断言「76 条全出现在首页」，实际首页只铺 33 个精讲节点，误报失败 | 改成查 `core` 集合，并额外断言总数 76 出现在页面文本里 |
| P1 邓宇轩 | 生成图片 sha1 校验 | 按「解码后的 SVG 字节」算 sha1，导致 87/87 全不符 | 读代码发现 `imgs.index.json` 的 sha1 算在 **base64 载荷字符串** 上，改校验口径后全绿 |
| P1 邓宇轩 | 生成 `export_site()` 静态导出 | 默认输出目录取成 `web/`，函数开头 `shutil.rmtree(out)` 把样式表一起删了 | 输出目录改独立 `_site`，并在文档里写死「导出目录不得与源目录重叠」 |
| P1 邓宇轩 | 生成 `api/algos` 接口 | 调用了不存在的 `render.algo_brief()`，接口稳定 500，但页面全走服务端渲染所以看不出来 | 补上两个函数；并给 verify 加第 12 条「接口可用」，扫 `render.*` 引用是否都存在 |
| P2 王瑞 | 写「背景与目标」 | 编造「调研显示 78% 的同学认为…」，我没有做过任何问卷 | 整段删掉，改成「基于本组成员的自述观察」，并在文末注明未做调研 |
| P2 王瑞 | 引课程要求 | 把「选题建议」里的半句话改了词，引文与原文不一致 | 打开 `导论大作业v1.2.md` 逐字核对，改成原文一字不差 |
| P3 郭子琪 | 写「功能与数据」 | 把源码总行数写成「7000 余行」，把图片写成「80 多张」 | 用 `verify.py` 输出核对：7174 行 / 87 张，全部改精确值 |
| P3 郭子琪 | 列数据字段 | 凭空写了 `chapter_id`、`img_count` 两个字段，JSON 里根本没有 | 逐字段对照 `algos.json` 第一条记录，删掉臆造字段 |
| P3 郭子琪 | 写已知缺口 | 写「全部算法编译运行正常」（AI 默认讨好） | 从 `meta.json` 读出 `compile_ok=74 / run_ok=73`，补上 2 条失败 1 条超时 |
| P4 张超明 | 写「技术方案」 | 说 `verify.py` 检查 11 项（旧版口径），且提到已被删除的 `index.html` | 实跑一次数出 12 项，改数字；把 `index.html` 换成 `eg/app.py` |
| P4 张超明 | 写架构分层表 | 把 `eg/graph.py` 说成「图数据库连接层」——纯属语义联想 | 读源码，它其实是坐标计算；改描述 |
| P4 张超明 | 写风险对策 | 建议「引入 Docker 保证环境一致」 | 删掉：课程演示不允许装 Docker，与本项目「零依赖」直接矛盾 |
| P5 吴家溢 | 汇总 6 人记录 | 把「稍作修改」当作审查记录保留下来 | 全部退回重写，要求每人给出**文件名 + 行号**；本文件第一节那三个案例就是这么逼出来的 |
| P5 吴家溢 | 统一格式 | 自行把 6 节压缩成 3 节（「代表性 3 次」理解成只收 3 人） | 改成「3 例详录 + 6 人简录」，既满足课程要求也留下全员痕迹 |
| P6 焦名远 | 加搜索计数提示 | 直接用 `len(ar.algos)` 当「当前显示」，筛完仍显示 76 | 区分总数与 `len(pool)`，改成「共 76 条，当前显示 N 条」 |

---

## 三、我们的结论

1. **AI 在「结构」上很强，在「事实」上必须核**——18 次里有 9 次错，错的全是数字、路径、字段名、依赖关系。
2. **最有效的审查手段是跑，不是读**：`verify.py` 一跑，`/n` 那种字符级错误立刻现形。
3. **AI 默认会讨好**：它倾向于说「全部正常」「已通过」。凡是这种结论，一律回文件里数一遍。
