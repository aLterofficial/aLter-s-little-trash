"""import_faces.py — 把一堆表情图片自动打标、导入幻梦的表情库

背景
----
仓库未附带 `huanmeng/data/faces/` 素材（原作者说明为"部分私有模块未包含"），
而本机 QQ 的表情缓存里其实存着大量图片 —— 但文件名是**纯数字**（0.png / 1.png…）。

偏偏 `face_lib` 是**靠文件名**生成关键词的（见 modules/face_lib.py:_extract_keywords），
所以数字文件名等于没有关键词，直接拷进去 LLM 也永远用不上。

本脚本用视觉模型逐张识别画面情绪，从 face_lib 的 48 个**规范词**里挑一个，
再复制成 `data/faces/<情绪词>_<编号>.<扩展名>` —— 这样 LLM 提示词里的词表和
磁盘上的素材就能对上号。

用法
----
    python import_faces.py                     # 默认 dry-run：只识别、不写文件
    python import_faces.py --limit 40          # dry-run，只看前 40 张
    python import_faces.py --apply --limit 40  # 真的导入 40 张
    python import_faces.py --src "D:\\some\\dir" --apply
    python import_faces.py --list              # 只打印规范词表

导入完成后到 QQ 里发 `/~reload`（或重启幻梦）即可生效，
日志会出现 `表情库加载: N 关键词, M 文件`。
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import shutil
import sys
from pathlib import Path

HUANMENG = Path(r"D:\QQBot\huanmeng")
FACES_DIR = HUANMENG / "data" / "faces"
DEFAULT_SRC = Path.home() / "Documents" / "Tencent Files" / "<BOT_QQ>" / "nt_qq" / "nt_data" / "Emoji"

EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


# ── 复用 relay_test.py 的配置读法（跟随 bot_config.toml 的 provider 切换）──
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


def canonical_keywords() -> list[str]:
    """从 face_lib 的 _TAG_CN 取规范词（元组第一个词是主词），保证与提示词词表一致。"""
    sys.path.insert(0, str(HUANMENG))
    import os
    os.chdir(HUANMENG)
    from modules import face_lib  # noqa: E402
    return [v[0] for v in face_lib._TAG_CN.values()]


def build_prompt(words: list[str]) -> str:
    return (
        "下面这张是聊天里用的表情包/贴图。\n"
        "请从下列词中选出**一个**最贴切描述它画面情绪或动作的词：\n"
        + "、".join(words)
        + "\n\n只输出那一个词本身，不要标点、不要解释、不要换行。"
    )


def match_keyword(text: str, words: list[str]) -> str | None:
    """在模型回答里找出第一个命中的规范词（按出现位置，其次按词表顺序）。"""
    t = (text or "").strip()
    if not t:
        return None
    best, best_pos = None, 10 ** 9
    for w in words:
        p = t.find(w)
        if p >= 0 and p < best_pos:
            best, best_pos = w, p
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="表情图片自动打标导入幻梦表情库")
    ap.add_argument("--src", default=str(DEFAULT_SRC), help="源图片目录")
    ap.add_argument("--limit", type=int, default=40, help="最多处理多少张（默认 40）")
    ap.add_argument("--apply", action="store_true", help="真的复制文件（默认只 dry-run）")
    ap.add_argument("--list", action="store_true", help="只打印规范词表后退出")
    ap.add_argument("--min-bytes", type=int, default=2000, help="跳过小于该字节数的图（默认 2000）")
    args = ap.parse_args()

    words = canonical_keywords()
    if args.list:
        print("规范词（%d 个）：" % len(words))
        print("  " + "、".join(words))
        return 0

    # 让输出在 GBK 控制台下也不炸（与 §4.7.6 同一个坑）
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    src = Path(args.src)
    if not src.is_dir():
        print(f"源目录不存在: {src}")
        return 1

    provider, name = load_bot_model("picture")
    url, key = load_env_config(provider)
    if not (url and key):
        print(f".env 里没有 {provider}_URL / {provider}_KEY")
        return 1

    # QQ 的表情缓存是 Ori/（原图）+ Thumb/（缩略图）成对存放，文件名却相同
    # （0.png 在两边各一份）—— 不过滤会导入一堆同图重复 + 低清缩略图。
    all_files = [f for f in sorted(src.rglob("*")) if f.suffix.lower() in EXTS and f.stat().st_size >= args.min_bytes]
    files = [f for f in all_files if "thumb" not in str(f).lower()]

    # 再按内容 MD5 去重（不同目录可能存同一张图）
    import hashlib
    seen: set[str] = set()
    uniq: list[Path] = []
    for f in files:
        try:
            h = hashlib.md5(f.read_bytes()).hexdigest()
        except Exception:
            continue
        if h in seen:
            continue
        seen.add(h)
        uniq.append(f)

    print(f"源目录 : {src}")
    print(f"候选图 : {len(uniq)} 张（≥{args.min_bytes} 字节；已滤除 "
          f"{len(all_files) - len(files)} 张缩略图、{len(files) - len(uniq)} 张重复图）")
    files = uniq
    print(f"模型   : {name} @ {provider}")
    print(f"模式   : {'APPLY（真写文件）' if args.apply else 'DRY-RUN（只看结果）'}")
    print(f"目标   : {FACES_DIR}")
    print("-" * 70)

    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=url, timeout=60.0)
    prompt = build_prompt(words)

    if args.apply:
        FACES_DIR.mkdir(parents=True, exist_ok=True)

    done = 0
    hit = 0
    tally: dict[str, int] = {}
    for f in files:
        if done >= args.limit:
            break
        done += 1
        try:
            raw = f.read_bytes()
            mime = mimetypes.guess_type(f.name)[0] or "image/png"
            if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                continue
            if f.suffix.lower() == ".gif":
                mime = "image/gif"
            data_uri = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
            resp = client.chat.completions.create(
                model=name,
                max_tokens=200,
                temperature=0,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]}],
                # ★ 必须关思考，否则内容全塞进 reasoning_content、content 为空
                #   （与 services/image_api.py 同一个坑，见 SESSION-LOG §4.7.9）
                extra_body={"thinking": {"type": "disabled"}},
            )
            answer = resp.choices[0].message.content or ""
        except Exception as e:
            print(f"  [!] {f.name}: {e}")
            continue

        kw = match_keyword(answer, words)
        if not kw:
            print(f"  [—] {f.name}: 未命中规范词（模型答：{answer.strip()[:30]!r}）")
            continue

        hit += 1
        tally[kw] = tally.get(kw, 0) + 1
        target = FACES_DIR / f"{kw}_{tally[kw]:03d}{f.suffix.lower()}"
        flag = "→ " + target.name if args.apply else "→ (dry-run) " + target.name
        print(f"  [{done:>3}] {f.name:<14} {kw:<6} {flag}")
        if args.apply:
            shutil.copy2(f, target)

    print("-" * 70)
    print(f"处理 {done} 张，命中规范词 {hit} 张")
    if tally:
        print("分布: " + "、".join(f"{k}×{v}" for k, v in sorted(tally.items(), key=lambda x: -x[1])))
    if not args.apply:
        print("\n这是 DRY-RUN，没有写任何文件。确认结果后加 --apply 真正导入。")
    else:
        print(f"\n已导入到 {FACES_DIR}")
        print("到 QQ 里发 /~reload 或重启幻梦即可生效（日志会显示『表情库加载: N 关键词, M 文件』）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
