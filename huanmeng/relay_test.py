"""relay_test.py — 中转站（OpenAI 兼容）可用性自检

幻梦不是普通的「发一句话收一句话」的机器人，它重度依赖 **Function Calling**
（76 条指令、工具调用全靠 tools 参数）。很多便宜的中转站只做了 chat 转发，
tools 参数会被忽略或直接报错，导致机器人看起来"能回话但指令全失效"。

这个脚本按重要性逐项探测，跑完就知道这家中转站能不能用：
  1. 基础对话        —— 不通则一切都免谈
  2. Function Calling —— 幻梦的指令/工具系统依赖它（最关键）
  3. JSON 输出        —— 判断/摘要等模块用到
  4. 流式输出        —— 发送器分批推送依赖
  5. 模型列表        —— 确认模型名拼写

用法:
    python relay_test.py                # 读 config/.env 里 provider=DEEPSEEK 的配置
    python relay_test.py <URL> <KEY> <模型名>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_env_config(provider: str) -> tuple[str, str]:
    """从 config/.env 读取 {PROVIDER}_URL / {PROVIDER}_KEY（自动去掉引号）"""
    env_path = ROOT / "config" / ".env"
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


def load_bot_model(which: str = "replyer_1") -> tuple[str, str]:
    """从 config/bot_config.toml 读取指定模型槽位的 (provider, name)。

    这样脚本自动跟随 bot_config.toml 的切换（官方 DEEPSEEK / 中转站 RELAY 等），
    不会再出现"配置已切到 RELAY、脚本却还去读 DEEPSEEK_KEY"的错配。
    """
    try:
        import toml
        cfg = toml.load(ROOT / "config" / "bot_config.toml")
        sec = cfg.get("model", {}).get(which, {})
        return sec.get("provider", "DEEPSEEK").upper(), sec.get("name", "deepseek-flash")
    except Exception as e:
        print(f"  (读取 bot_config.toml 失败，回退默认值: {e})")
        return "DEEPSEEK", "deepseek-flash"


def main() -> int:
    if len(sys.argv) >= 4:
        base_url, api_key, model = sys.argv[1], sys.argv[2], sys.argv[3]
        provider = "(命令行传入)"
    else:
        provider, model = load_bot_model("replyer_1")
        base_url, api_key = load_env_config(provider)

    print("=" * 68)
    print("中转站 / API 可用性自检")
    print("=" * 68)
    print(f"  provider : {provider}   (取自 bot_config.toml [model.replyer_1])")
    print(f"  base_url : {base_url or '(未配置)'}")
    print(f"  model    : {model}")
    print(f"  api_key  : {(api_key[:8] + '...' + api_key[-4:]) if len(api_key) > 14 else '(未配置或过短)'}")
    print()

    if not base_url or not api_key:
        print("✗ config/.env 里没读到 URL/KEY，请先填写，或按用法传入三个参数")
        return 2
    if "REPLACE_ME" in api_key:
        print("✗ api_key 还是占位符 sk-REPLACE_ME，请填真实 Key")
        return 2

    try:
        from openai import OpenAI
    except ImportError:
        print("✗ 未安装 openai 包，请在 venv 里执行: pip install openai")
        return 2

    # base_url 原样使用（与 services/llm.py:994 行为一致），不补 /v1
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)
    results: dict[str, str] = {}

    # ---- 1) 基础对话 ----
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "只回复两个字：你好"}],
            max_tokens=20,
        )
        text = (r.choices[0].message.content or "").strip()
        results["基础对话"] = f"OK  -> {text!r}"
    except Exception as e:
        results["基础对话"] = f"FAIL -> {type(e).__name__}: {str(e)[:150]}"

    # 基础对话不通就不用往下测了
    if results["基础对话"].startswith("FAIL"):
        for k in ("Function Calling", "JSON 输出", "流式输出", "模型列表"):
            results[k] = "SKIP (基础对话已失败)"
        _report(results)
        return 1

    # ---- 2) Function Calling（幻梦的核心依赖）----
    weather_tool = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名"}},
                "required": ["city"],
            },
        },
    }]
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "上海今天天气怎么样？用工具查"}],
            tools=weather_tool,
            tool_choice="auto",
            max_tokens=120,
        )
        calls = r.choices[0].message.tool_calls
        if calls:
            fn = calls[0].function
            results["Function Calling"] = f"OK  -> 调用了 {fn.name}({fn.arguments})"
        else:
            results["Function Calling"] = "WARN -> 未发起工具调用（tools 可能被中转站忽略，指令系统会失效）"
    except Exception as e:
        results["Function Calling"] = f"FAIL -> {type(e).__name__}: {str(e)[:150]}"

    # ---- 2b) 思考模式开关是否被中转站透传 ----
    # 关键：DeepSeek 思考模型默认开启思考，且推理与正文共享 max_tokens。
    # 幻梦对"判断类短调用"主动传 thinking=disabled 来避免推理吃光预算。
    # 若中转站丢弃该参数，短调用会返回空 content，表现为"机器人偶尔不回话"。
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "只回复两个字：你好"}],
            max_tokens=20,
            extra_body={"thinking": {"type": "disabled"}},
        )
        txt = (r.choices[0].message.content or "").strip()
        if txt:
            results["思考开关透传"] = f"OK  -> thinking=disabled 生效, content={txt!r}"
        else:
            results["思考开关透传"] = ("WARN -> content 为空，中转站可能丢弃了 thinking 参数；"
                                     "幻梦的短判断调用会返回空值")
    except Exception as e:
        results["思考开关透传"] = f"WARN -> {type(e).__name__}: {str(e)[:120]}"

    # ---- 2c) 带 tools 的多轮调用 + reasoning_content 回传 ----
    # DeepSeek 规定：携带 tools 的请求，后续轮次必须回传 reasoning_content，否则 400。
    # 幻梦的 FC 循环最多 6 轮，services/llm.py:1847 已实现回传，这里验证中转站是否配合。
    try:
        msgs = [{"role": "user", "content": "上海今天天气怎么样？用工具查"}]
        r1 = client.chat.completions.create(
            model=model, messages=msgs, tools=weather_tool, tool_choice="auto",
            max_tokens=300, extra_body={"thinking": {"type": "enabled"}},
        )
        m1 = r1.choices[0].message
        # 用 model_dump 保留 reasoning_content 等扩展字段
        try:
            msgs.append(m1.model_dump(exclude_none=True))
        except Exception:
            msgs.append({"role": "assistant", "content": m1.content,
                         "reasoning_content": getattr(m1, "reasoning_content", None),
                         "tool_calls": m1.tool_calls})
        if m1.tool_calls:
            msgs.append({"role": "tool", "tool_call_id": m1.tool_calls[0].id,
                         "content": "晴，25℃"})
        r2 = client.chat.completions.create(
            model=model, messages=msgs, tools=weather_tool,
            max_tokens=300, extra_body={"thinking": {"type": "enabled"}},
        )
        out = (r2.choices[0].message.content or "").strip()
        results["多轮FC+思考"] = f"OK  -> 第二轮未报 400, 回复={out[:30]!r}"
    except Exception as e:
        results["多轮FC+思考"] = f"FAIL -> {type(e).__name__}: {str(e)[:150]}"

    # ---- 3) JSON 输出 ----
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": '输出 JSON：{"ok": true, "n": 3}'}],
            response_format={"type": "json_object"},
            max_tokens=50,
        )
        txt = (r.choices[0].message.content or "").strip()
        json.loads(txt)
        results["JSON 输出"] = f"OK  -> {txt[:60]}"
    except Exception as e:
        results["JSON 输出"] = f"WARN -> {type(e).__name__}: {str(e)[:120]}"

    # ---- 4) 流式输出 ----
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "数到三"}],
            stream=True,
            max_tokens=30,
        )
        chunks = sum(1 for _ in stream)
        results["流式输出"] = f"OK  -> 收到 {chunks} 个 chunk"
    except Exception as e:
        results["流式输出"] = f"FAIL -> {type(e).__name__}: {str(e)[:150]}"

    # ---- 5) 模型列表 ----
    try:
        models = client.models.list()
        ids = [m.id for m in models.data]
        hit = "（含配置的模型名）" if model in ids else "（注意：配置的模型名不在列表里！）"
        results["模型列表"] = f"OK  -> {len(ids)} 个: {', '.join(ids[:8])}{hit}"
    except Exception as e:
        results["模型列表"] = f"WARN -> {type(e).__name__}: {str(e)[:120]}"

    _report(results)
    return 0 if results["Function Calling"].startswith("OK") else 1


def _report(results: dict[str, str]) -> None:
    print("-" * 68)
    for k, v in results.items():
        mark = "✓" if v.startswith("OK") else ("!" if v.startswith(("WARN", "SKIP")) else "✗")
        print(f"  {mark} {k:<18} {v}")
    print("-" * 68)
    fc = results.get("Function Calling", "")
    if fc.startswith("OK"):
        print("结论：这家接口可用于幻梦，Function Calling 正常。")
    elif fc.startswith("WARN"):
        print("结论：基础对话可用，但不支持工具调用 —— 机器人能闲聊，")
        print("      /~help、/~weather 等依赖工具的指令会失效。建议换支持 tools 的中转站。")
    else:
        print("结论：不适合幻梦，Function Calling 不可用。")


if __name__ == "__main__":
    raise SystemExit(main())
