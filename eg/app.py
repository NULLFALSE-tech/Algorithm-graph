# -*- coding: utf-8 -*-
"""程序入口：标准库 http.server 实现的本地 web 服务。

为什么不用 Flask：
    课程演示要在老师的机器上跑。Flask 是第三方包，装不上或校园网太慢
    都会让「python app.py」直接报错，演示分归零。标准库零依赖，
    Python 3.8 以上 clone 下来就能跑。

运行：
    python app.py                  启动服务，默认 http://127.0.0.1:8000
    python app.py --port 8080      换端口
    python app.py --export site    导出静态站点（不需要起服务）

这个文件只负责「HTTP 层」：读懂请求、交给 render 取字符串、把字节发回去。
业务逻辑一律不写在这里。
"""

from __future__ import print_function

import argparse
import mimetypes
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # 项目根目录
sys.path.insert(0, str(ROOT))           # 让 `import eg` 能找到包

from eg import render                    # noqa: E402
from eg.store import Archive             # noqa: E402

WEB_DIR = ROOT / "web"
IMG_DIR = ROOT / "data" / "imgs"

# 静态文件类型：SVG 必须显式声明，否则部分浏览器不渲染
MIME = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

ARCHIVE = None      # 全局只加载一次，进程内共享


def get_archive():
    global ARCHIVE
    if ARCHIVE is None:
        ARCHIVE = Archive(ROOT)
    return ARCHIVE


# ---------------------------------------------------------------- 安全用工具

def safe_path(base, rel):
    """把 URL 里的相对路径拼到 base 下，并挡住 ../ 越权读取。

    返回 None 表示这个路径不合法，调用方应当回 403。
    """
    base = Path(base).resolve()
    try:
        target = (base / rel).resolve()
    except (OSError, ValueError):
        return None
    if target != base and base not in target.parents:
        return None
    return target


# ---------------------------------------------------------------- HTTP 处理

class Handler(BaseHTTPRequestHandler):
    server_version = "AlgoGraph/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------- 发响应
    def send_bytes(self, status, body, ctype, cache=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_html(self, status, text):
        self.send_bytes(status, text.encode("utf-8"), "text/html; charset=utf-8")

    def send_json(self, status, text):
        self.send_bytes(status, text.encode("utf-8"), "application/json; charset=utf-8")

    # ---------------------------------------------------------- 请求入口
    def do_GET(self):
        self.dispatch()

    def do_HEAD(self):
        self.dispatch()

    def dispatch(self):
        parts = urlparse(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        try:
            self.route(path, query)
        except BrokenPipeError:
            pass
        except Exception as exc:                       # noqa: BLE001
            # 兜底：任何未预料的异常都变成 500 页，而不是让进程崩掉
            self.send_html(500, render.error_page(
                500, "服务端出错", "%s: %s" % (type(exc).__name__, exc)))

    def route(self, path, query):
        ar = get_archive()

        if path == "/":
            q = (query.get("q") or [""])[0].strip()
            ch = (query.get("ch") or [""])[0].strip()
            return self.send_html(200, render.index_page(ar, q, ch))

        if path in ("/all", "/all/"):
            q = (query.get("q") or [""])[0].strip()
            return self.send_html(200, render.all_page(ar, q))

        if path.startswith("/a/"):
            algo_id = path[3:].strip("/")
            algo = ar.get(algo_id)
            if not algo:
                return self.send_html(404, render.error_page(
                    404, "找不到这个算法", "地址里没有 <code>%s</code>，回首页看看。" % render.esc(algo_id)))
            return self.send_html(200, render.detail_page(ar, algo))

        if path == "/favicon.ico":
            return self.send_bytes(204, b"", "image/x-icon")

        # ---------------- JSON 接口：给别的程序取数据用
        if path == "/api/stats":
            return self.send_json(200, render.json_dumps(ar.stats()))

        if path == "/api/algos":
            q = (query.get("q") or [""])[0].strip()
            ch = (query.get("ch") or [""])[0].strip()
            rows = [render.algo_brief(a) for a in ar.search(q, ch)]
            return self.send_json(200, render.json_dumps(rows))

        if path.startswith("/api/algo/"):
            algo = ar.get(path[len("/api/algo/"):].strip("/"))
            if not algo:
                return self.send_json(404, render.json_dumps({"error": "not found"}))
            return self.send_json(200, render.json_dumps(render.algo_full(ar, algo)))

        # ---------------- 静态资源
        if path.startswith("/img/"):
            f = safe_path(IMG_DIR, path[len("/img/"):])
            return self.send_file(f)

        if path.startswith("/static/"):
            f = safe_path(WEB_DIR, path[len("/static/"):])
            return self.send_file(f)

        return self.send_html(404, render.error_page(
            404, "页面不存在", "没有 <code>%s</code> 这个地址。" % render.esc(path)))

    # ---------------------------------------------------------- 静态文件
    def send_file(self, f):
        if f is None:
            return self.send_html(403, render.error_page(403, "拒绝访问", "路径不合法。"))
        if not f.is_file():
            return self.send_html(404, render.error_page(404, "文件不存在", "检查一下路径。"))
        ctype = MIME.get(f.suffix.lower()) or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        # 图片和样式基本不变，让浏览器缓存一天，刷新更快
        self.send_bytes(200, f.read_bytes(), ctype, cache="public, max-age=86400")

    # ---------------------------------------------------------- 安静一点
    def log_message(self, fmt, *args):
        if getattr(self, "verbose", False):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


# ---------------------------------------------------------------- 静态导出

def relativize(html):
    """把绝对路径改成同层相对路径，让导出的站点双击就能看。"""
    html = html.replace('href="/static/style.css"', 'href="static/style.css"')
    html = html.replace('src="/img/', 'src="img/')
    html = html.replace('href="/img/', 'href="img/')
    html = html.replace('href="/all"', 'href="all.html"')
    html = html.replace('action="/all"', 'action="all.html"')
    html = html.replace('href="/?ch=', 'href="index.html?ch=')
    html = html.replace('action="/?ch=', 'action="index.html?ch=')
    html = html.replace('href="/"', 'href="index.html"')
    html = html.replace('action="/"', 'action="index.html"')
    # /a/xxx  ->  a-xxx.html（全部平铺在根目录，相对路径才统一）
    html = html.replace('href="/a/', 'href="a-')
    html = html.replace('.html"\n', '.html"\n')     # 占位，保持可读
    out = []
    i = 0
    while True:
        k = html.find('href="a-', i)
        if k < 0:
            out.append(html[i:])
            break
        out.append(html[i:k])
        end = html.find('"', k + 5)
        piece = html[k:end]
        if not piece.endswith(".html"):
            piece += ".html"
        out.append(piece)
        i = end
    return "".join(out)


def export_site(out_dir):
    """导出一份不需要 Python 环境的静态站点，供老师直接双击查看。"""
    ar = get_archive()
    out = Path(out_dir).resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)
    (out / "img").mkdir(parents=True)

    shutil.copyfile(WEB_DIR / "style.css", out / "static" / "style.css")

    # 只复制索引里确实用到的图片，不整棵目录拖进来
    copied = 0
    for item in ar.images:
        rel = item["path"].replace("\\", "/")
        src = IMG_DIR / rel
        if not src.is_file():
            continue
        dst = out / "img" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied += 1

    pages = [("index.html", render.index_page(ar, "", "", interactive=False)),
             ("all.html", render.all_page(ar, "", interactive=False))]
    for algo in ar.core_list():
        pages.append(("a-%s.html" % algo["id"], render.detail_page(ar, algo, interactive=False)))

    for name, html in pages:
        (out / name).write_text(relativize(html), encoding="utf-8")

    (out / "README.txt").write_text(
        "这是静态导出快照，双击 index.html 即可浏览，不需要安装任何东西。\n"
        "静态版没有搜索和章节筛选，需要这些功能请回到项目根目录运行：python app.py\n",
        encoding="utf-8")

    print("静态站点已导出：%s" % out)
    print("  页面 %d 个，图片 %d 张（索引里共 %d 张）" % (len(pages), copied, len(ar.images)))
    print("  打开 %s 即可查看。" % (out / "index.html"))
    return out


# ---------------------------------------------------------------- 启动

def pick_port(host, start, tries=10):
    for port in range(start, start + tries):
        try:
            srv = ThreadingHTTPServer((host, port), Handler)
            return srv
        except OSError:
            continue
    raise SystemExit("端口 %d 起连续 %d 个都被占用，用 --port 换一个。" % (start, tries))


def main(argv=None):
    ap = argparse.ArgumentParser(description="算法知识图谱 · 本地服务")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址，默认只对本机开放")
    ap.add_argument("--port", type=int, default=8000, help="端口，默认 8000")
    ap.add_argument("--export", metavar="目录", help="导出静态站点后退出，不起服务")
    ap.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    ap.add_argument("--verbose", action="store_true", help="打印每条请求日志")
    args = ap.parse_args(argv)

    if args.export:
        export_site(args.export)
        return 0

    ar = get_archive()
    st = ar.stats()
    httpd = pick_port(args.host, args.port)
    host, port = httpd.server_address[0], httpd.server_address[1]
    url = "http://%s:%d/" % (host, port)

    print("算法知识图谱 已启动")
    print("  算法 %d 条 / 精讲 %d 条 / 章节 %d 个 / 图片 %d 张"
          % (st["total"], st["core"], st["chapters"], st["images"]))
    print("  数据生成时间 %s" % (st["generated"] or "(未知)"))
    print("  地址 %s" % url)
    print("  停止：Ctrl+C")
    sys.stdout.flush()

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:                             # noqa: BLE001
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
