// loadNapCat.template.js — NapCat 引导脚本模板（由 start-napcat.bat 复制为 loadNapCat.js）
//
// 作用一：把 process.argv 里 "-q" 后面的 token 改成真实机器人账号，实现自动快速登录。
//
//   背景：NapCat 用 process.argv 判断是否快速登录，并取 "-q"/"--qq" 后面的那个 token 当账号
//   （napcat.mjs:  a.findIndex(u => u === "-q" || u === "--qq")，然后取 a[c+1]）。
//   而 NapCatWinBootMain.exe 只会把「唯一一个额外参数」包装成 "-q <参数>" 转发给 QQ.exe，
//   那个位置被我们用来传 --user-data-dir（隔离 QQ 数据目录，必须保留，否则你的个人 QQ 与
//   机器人 QQ 抢同一 profile，会导致扫码后 worker 进程崩溃）。
//   于是 QQ.exe 的命令行成了： --enable-logging -q --user-data-dir=D:\QQBot\QQProfile
//   NapCat 就把 "--user-data-dir=..." 当成了账号名 → 快速登录必然失败 → 每次都要扫码。
//
//   所以这里不去「追加」参数（追加到末尾没用，findIndex 只认第一个），
//   而是直接把第一个 -q 后面的 token 覆盖成真实账号。
//
// 作用二：以正确的 file:/// URL 加载 napcat.mjs。
//
// ⚠️ 三个必须遵守的约束（都实际踩过坑）：
//   1) 不要用 require()。该执行上下文里 require 不可用，用了 napcat.mjs 根本不会被加载，
//      表现为 NapCat 毫无日志、WebUI(6099) 不监听、静默失败。
//   2) 路径必须是硬编码绝对路径（正斜杠）。移动 D:\QQBot\NapCat 目录后需同步改下面那行。
//   3) 必须用「覆盖」而不是「追加」-q 的账号，见上。
const ACCOUNT = '<BOT_QQ>';
const FLAGS = ['-q', '--qq'];
const idx = process.argv.findIndex((a) => FLAGS.includes(a));
if (idx !== -1) {
  process.argv[idx + 1] = ACCOUNT;   // 覆盖掉被误当成账号的 "--user-data-dir=..."
} else {
  process.argv.push('-q', ACCOUNT);  // 命令行里没有 -q 时才追加
}

(async () => { await import("file:///D:/QQBot/NapCat/napcat.mjs"); })();
