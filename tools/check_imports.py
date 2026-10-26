"""静态扫描幻梦仓库的导入，找出：
1. 引用了但不存在的本地模块（README 说「部分私有模块未包含」）
2. 用到但 requirements.txt 没写的第三方包
仅用标准库，可用系统 Python 直接跑。
"""
import ast
import sys
from pathlib import Path

ROOT = Path(r"D:\QQBot\huanmeng")
STDLIB = set(sys.stdlib_module_names)
LOCAL_TOP = {p.name for p in ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists() or p.is_dir()}
LOCAL_TOP |= {p.stem for p in ROOT.glob("*.py")}

# requirements.txt 里声明的包（导入名可能不同，做映射）
REQ_ALIAS = {
    "websockets": "websockets", "openai": "openai", "httpx": "httpx",
    "toml": "toml", "dotenv": "python-dotenv", "ddgs": "ddgs",
    "markdown": "markdown", "playwright": "playwright",
}

missing_local = {}   # 模块 -> 引用它的文件
third_party = {}     # 包名 -> 引用它的文件

for py in ROOT.rglob("*.py"):
    rel = py.relative_to(ROOT)
    if any(part in {".venv", "__pycache__", "node_modules"} for part in rel.parts):
        continue
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError as e:
        print(f"[语法错误] {rel}: {e}")
        continue

    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:      # 相对导入，跳过
                continue
            if node.module:
                mods = [node.module]
        for m in mods:
            top = m.split(".")[0]
            if top in STDLIB or top in REQ_ALIAS:
                continue
            # 本地模块？
            cand = ROOT / Path(*m.split("."))
            exists = (cand.with_suffix(".py")).exists() or (cand / "__init__.py").exists()
            if top in LOCAL_TOP or exists:
                if not exists:
                    missing_local.setdefault(m, set()).add(str(rel))
            else:
                third_party.setdefault(top, set()).add(str(rel))

print("=" * 70)
print("【1】引用但不存在的本地模块（会导致 ImportError）")
print("=" * 70)
if not missing_local:
    print("  无 —— 本地模块引用完整")
else:
    for m, files in sorted(missing_local.items()):
        print(f"  {m}")
        for f in sorted(files)[:4]:
            print(f"      ← {f}")

print()
print("=" * 70)
print("【2】用到但 requirements.txt 未声明的第三方包")
print("=" * 70)
if not third_party:
    print("  无")
else:
    for m, files in sorted(third_party.items(), key=lambda kv: -len(kv[1])):
        print(f"  {m:<18} 被 {len(files)} 个文件引用   例: {sorted(files)[0]}")
