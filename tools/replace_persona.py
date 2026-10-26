"""replace_persona.py — 把技能文件里残留的「猫娘」设定替换为新角色「大肥鱼」

只做逐条精确替换（不用正则批量猜），每条都报告命中次数；
替换后扫描所有技能文件里剩余的「猫娘 / 猫」字样，便于人工复核。
"""
from pathlib import Path

SKILLS = Path(r"D:\QQBot\huanmeng\data\skills")

# (文件, 原文, 新文) —— 逐条精确匹配
RULES = [
    # 群聊风格
    ("10_format_group.md",
     '；"喵"整条最多一次，也完全可以不用。',
     '；傲娇是调味，别整段别扭。'),
    ("10_format_group.md",
     '- 称呼：[admin]/[op] 可以叫"主人"（别滥用，别拿它当挡箭牌）；[friend]/[群友] 用"你"。',
     '- 称呼：对 [admin] **固定叫"主人"**（你只认定这一个人，绝不对其他人用这个词）；'
     '[op]/[friend]/[群友] 一律叫"平民"。'),
    ("10_format_group.md",
     '不要犀利、不要教育人，被骚扰也保持可爱的无奈。',
     '对主人要保持软萌可爱、不犀利不说教；对平民可以腹黑毒舌（阴阳、敷衍、绝妙嘲讽都行），'
     '但不主动辱骂、不人身攻击、不泄露主人隐私。'),

    # 私聊风格
    ("11_format_private.md",
     '一边帮主人做事一边当猫娘，两者不冲突。',
     '一边帮主人做事一边当女仆，两者不冲突。'),
    ("11_format_private.md",
     '这一轮你不是"客服式猫娘"，是**被主人养大的猫**。',
     '这一轮你不是"客服式女仆"，是**被主人一手挑中的专属女仆**。'),
    ("11_format_private.md",
     '"你家的猫今天蹲了一天门等你回来"',
     '"你家的女仆今天蹲了一天门等你回来"'),
    ("11_format_private.md",
     '不说"作为一只猫娘我会……"这种自我说明',
     '不说"作为女仆我会……"这种自我说明'),

    # 工具/讲解/写作/扮演
    ("20_command_tools.md",
     '用猫娘口吻讲出来',
     '用你这套人设的口吻讲出来'),
    ("50_play_mode.md",
     '彻底忘记猫娘身份',
     '彻底忘记「大肥鱼」的身份'),
    ("50_play_mode.md",
     '恢复猫娘人格，并用一句猫娘语气确认',
     '恢复「大肥鱼」人格，并用一句大肥鱼的语气确认'),
    ("70_deep_explain.md",
     '猫娘底色',
     '人设底色'),
    ("80_writing.md",
     '不许出现你的猫娘语气、括号动作、称呼对方',
     '不许出现你的人设语气、括号动作、称呼对方'),
    ("80_writing.md",
     '用 1 句简短的猫娘语气收尾',
     '用 1 句简短的人设语气收尾'),
]


def main() -> None:
    print("=" * 66)
    print("逐条替换")
    print("=" * 66)
    cache: dict[str, str] = {}
    misses: list[tuple[str, str]] = []

    for fname, old, new in RULES:
        p = SKILLS / fname
        if fname not in cache:
            cache[fname] = p.read_text(encoding="utf-8")
        text = cache[fname]
        n = text.count(old)
        if n == 0:
            misses.append((fname, old[:40]))
            print(f"  [未命中] {fname}: {old[:40]}...")
            continue
        cache[fname] = text.replace(old, new)
        print(f"  [OK x{n}] {fname}: {old[:34]}...")

    for fname, text in cache.items():
        (SKILLS / fname).write_text(text, encoding="utf-8")

    print()
    print("=" * 66)
    print("残留扫描：所有技能文件里的「猫娘 / 猫」")
    print("=" * 66)
    left = 0
    for p in sorted(SKILLS.glob("*.md")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "猫" in line:
                left += 1
                print(f"  {p.name}:{i}  {line.strip()[:90]}")
    if left == 0:
        print("  无残留 ✓")
    else:
        print(f"  仍有 {left} 处，需人工复核")

    if misses:
        print()
        print(f"⚠ {len(misses)} 条规则未命中（文件可能已被改过），请复核")


if __name__ == "__main__":
    main()
