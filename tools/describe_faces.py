"""describe_faces.py — 用视觉模型给 data/faces/ 的素材重新生成「画面简述」

为什么需要
----------
`modules/face_lib.py` 的 `_FACE_DESC` 是一张「情绪词 → 画面简述」表（48 条），
它跟着词表一起进 system 提示词，让 LLM 把情绪词和真实画面对上号、选图不盲猜。

但那张表是照**原作者那批素材**逐张校对写的。一旦换成自己导入的素材
（见 `import_faces.py`），它就开始"骗" LLM：词表说「得意 = 抬下巴嘚瑟」，
而你的 `得意_01.png` 其实是别的画面。

本脚本按**实际图片**重新生成描述，写入 `data/faces/_descriptions.json`；
`face_lib.face_keywords_hint()` 会优先使用它，`_FACE_DESC` 退化为默认值。

用法
----
    python describe_faces.py                    # dry-run：只打印，不写文件
    python describe_faces.py --apply            # 写入 _descriptions.json
    python describe_faces.py --sample 5         # 每个词最多取 5 张图一起看

导入新素材后重跑一次即可。⚠️ 每张图一次视觉调用，会消耗中转站额度。
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import sys
from collections import defaultdict
from pathlib import Path

HUANMENG = Path(r"D:\QQBot\huanmeng")
FACES_DIR = HUANMENG / "data" / "faces"
DESC_FILE = FACES_DIR / "_descriptions.json"
EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def load_env_config(provider: str) -> tuple[str, str]:
    env_path = HUANMENG / "config" / ".env"
    url = key = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().upper(), v.strip().strip('"').strip("'")
            if k == f"{provider}_URL":
                url = v
            elif k == f"{provider}_KEY":
                key = v
    return url, key


def load_bot_model(which: str) -> tuple[str, str]:
    try:
        import toml
        cfg = toml.load(HUANMENG / "config" / "bot_config.toml")
        sec = cfg.get("model", {}).get(which, {})
        return sec.get("provider", "DEEPSEEK").upper(), sec.get("name", "deepseek-flash")
    except Exception as e:
        print(f"  (读 bot_config.toml 失败，回退: {e})")
        return "DEEPSEEK", "deepseek-flash"


def group_by_keyword() -> dict[str, list[Path]]:
    """把 data/faces/ 的图片按「情绪词」分组。

    ★ 必须用 face_lib 自己的 `_tags_from_stem()` 来提取关键词，不能自己按
      文件名规则瞎猜 —— 库对中文名取的是**末 2 个汉字**（打哈欠_001 → 哈欠、
      打招呼_001 → 招呼、抱东西_002 → 东西），按 "_" 前缀切会得到"打哈欠"
      这种对不上的 key，描述就白生成了（实测踩过）。
    """
    sys.path.insert(0, str(HUANMENG))
    import os
    os.chdir(HUANMENG)
    from modules import face_lib  # noqa: E402

    g: dict[str, list[Path]] = defaultdict(list)
    if not FACES_DIR.is_dir():
        return g
    for f in sorted(FACES_DIR.iterdir()):
        if f.suffix.lower() not in EXTS:
            continue
        for kw in face_lib._tags_from_stem(f.stem):
            g[kw].append(f)
    return g


_CLEAN = re.compile(r'[\s"\'“”‘’。，、！？!?,.;；:：()（）\[\]【】]+')


def clean_desc(text: str) -> str:
    """把模型输出压成一行短描述。"""
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    first = _CLEAN.sub("", first)
    return first[:12]


def build_prompt(kw: str, n: int) -> str:
    if n == 1:
        head = f"这是聊天表情包素材，它归属的情绪词是「{kw}」。"
    else:
        head = f"下面是聊天表情包素材（{n} 张），它们归属的情绪词是「{kw}」。"
    return (
        head + "\n"
        "请用**不超过 8 个字**概括画面的**视觉特征**（表情 / 姿势 / 道具 / 配色）。\n"
        "要求：\n"
        "1. 只输出**一段**描述，绝对不要逐张分别描述再拼接；\n"
        f"2. 不要出现「{kw}」这两个字；\n"
        "3. 不要标点、不要解释、不要换行。\n"
        "示例：眯眼笑　瘪嘴要哭　鼓脸瞪眼　举牌比心"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="给表情素材生成画面简述")
    ap.add_argument("--apply", action="store_true", help="写入 _descriptions.json（默认只打印）")
    ap.add_argument("--sample", type=int, default=1,
                    help="每个词取几张图一起看（默认 1；>1 时模型容易逐张描述再拼接，不推荐）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    groups = group_by_keyword()
    if not groups:
        print(f"{FACES_DIR} 里没有图片")
        return 1

    provider, name = load_bot_model("picture")
    url, key = load_env_config(provider)
    if not (url and key):
        print(f".env 里没有 {provider}_URL / {provider}_KEY")
        return 1

    print(f"素材目录: {FACES_DIR}")
    print(f"关键词  : {len(groups)} 个，共 {sum(len(v) for v in groups.values())} 张")
    print(f"模型    : {name} @ {provider}")
    print(f"模式    : {'APPLY' if args.apply else 'DRY-RUN'}")
    print("-" * 70)

    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=url, timeout=90.0)

    result: dict[str, str] = {}
    for kw, files in groups.items():
        picks = files[: max(1, args.sample)]
        content: list[dict] = [{"type": "text", "text": build_prompt(kw, len(picks))}]
        for f in picks:
            mime = mimetypes.guess_type(f.name)[0] or "image/png"
            b64 = base64.b64encode(f.read_bytes()).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        try:
            resp = client.chat.completions.create(
                model=name, max_tokens=120, temperature=0,
                messages=[{"role": "user", "content": content}],
                # ★ 必须关思考，否则 content 为空（同 image_api.py 的坑，见 SESSION-LOG §4.7.9）
                extra_body={"thinking": {"type": "disabled"}},
            )
            desc = clean_desc(resp.choices[0].message.content or "")
        except Exception as e:
            print(f"  [!] {kw}: {e}")
            continue
        if not desc:
            print(f"  [—] {kw}: 模型没给出可用描述")
            continue
        result[kw] = desc
        warn = "  ⚠️ 偏长，疑似拼接" if len(desc) > 9 else ""
        print(f"  {kw:<6} ×{len(files):<3} → {desc}{warn}")

    print("-" * 70)
    print(f"生成 {len(result)} 条描述")
    if args.apply:
        existing: dict[str, str] = {}
        if DESC_FILE.is_file():
            try:
                existing = json.loads(DESC_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        # 合并：本次生成失败的关键词保留旧值；同时**剔除已不存在于素材里的 key**
        # （否则改名/删图后会残留一堆对不上的僵尸条目）
        merged = {k: v for k, v in {**existing, **result}.items() if k in groups}
        DESC_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        dropped = len(existing) + len(result) - len(merged)
        print(f"已写入 {DESC_FILE}（{len(merged)} 条，剔除 {max(0, dropped)} 条失效 key）")
        print("重启幻梦后生效（face_lib 只加载一次）。")
    else:
        print("\nDRY-RUN，没有写文件。确认后加 --apply。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
