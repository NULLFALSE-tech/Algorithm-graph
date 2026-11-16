"""项目入口：和 `python -m eg.app` 完全等价。

为什么单独放一个 app.py：
1. 课程要求「拿到源码后一条命令就能跑」，组员不必记 `-m` 模块写法；
2. README、演示视频、需求文档里统一写 `python app.py`，只有一种说法；
3. 双击/右键「在终端中打开」后直接回车即可，不必先 cd 到子目录。
"""

import sys
from pathlib import Path

# 允许直接以脚本方式运行（此时项目根目录不在 sys.path 里）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eg.app import main  # noqa: E402  (必须在 sys.path 调整之后导入)

if __name__ == "__main__":
    sys.exit(main())
