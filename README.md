# PR Watcher

[中文](#中文) · [English](#english)

盯着 GitHub 仓库的 PR 和 issue,每次检查发一份汇报:**这次新提交了哪些** + **还有哪些没处理**;没有新提交时也会报一声"无新提交"。
不做分析、不克隆仓库、不生成报告,只用 GitHub 的只读接口。

Watches GitHub repos for new pull requests and issues and notifies you (Windows toast + email, optional ServerChan).
Every check reports what is new plus what is still open, and says "无新提交" when there is nothing new. No cloning, no checkout, no reports — read-only API access only.

---

## 中文

### 需要什么

Windows + Python 3 + `requests`(`pip install requests`)。
**PR-Watcher 当前主要面向 Windows 平台。** 需要 Windows 10/11 + Python 3 + `requests`(`pip install requests`)。

弹窗走 Windows 通知、单实例用 `msvcrt` 文件锁、启停和开机自启用 `.bat` / `.vbs` / 计划任务 —— 这些都是专门为 Windows 做的,不打算为别的系统做兼容。

### 快速开始

```
1. 装 Python 3 和 requests
2. 复制 config.example.json 成 config.json,填上仓库和邮箱
3. (私有仓库才需要)把 token 存到 secrets/github-token.txt
4. 双击 PRWatcher.exe
```

看到 `watcher.log` 里出现下面这行就说明在跑了:

```
[2026-09-14 20:01:46] PR Watcher 启动: 1 个仓库 · 每天 10:00 / 18:00 / 22:00 检查
[2026-09-14 20:01:46] 下次检查: 09-14 22:00
```

默认是**固定时刻**模式:每天 10:00、18:00、22:00 各查一次,启动后不会立刻查(保证通知只落在这几个点上)。
想马上看一轮就 `python pr_watcher.py --once`。把 `dailyTimes` 写成 `[]` 或删掉,就退回 `pollMinutes` 周期模式(启动时立刻查一轮,之后按间隔循环)。

### 每个文件是干什么的

| 文件 | 作用 | 要改吗 |
|---|---|---|
| `config.json` | 全部配置:仓库、token 路径、通知、周期 | **要改**(从 `config.example.json` 复制) |
| `secrets/github-token.txt` | GitHub token | 看情况,见下 |
| `state.json` | 已提醒过的编号,自动生成 | 不用改;删掉 = 把所有 open 条目重新当成新条目报一次 |
| `pr_watcher.py` | 主程序 | 一般不用改 |
| `PRWatcher.exe` | 双击启动器,后台无窗口 | 不用改 |
| `launcher.cs` | 启动器源码 | 改了用 csc 重编:`csc /nologo /target:winexe /r:System.Windows.Forms.dll /out:PRWatcher.exe launcher.cs` |
| `start-hidden.vbs` | 开机自启用(无窗口启动) | 不用改;保持纯 ASCII + CRLF |
| `stop-watcher.bat` | 停止 | 不用改 |
| `install-task.bat` | 注册成计划任务自启,可选 | 管理员运行 |
| `watcher.log` | 运行日志,每轮一行小结 | 看 |
| `launcher.log` | 启动器日志 | 双击没反应时看这个 |
| `config.example.json` | 配置样板,不含任何密钥 | 不用改 |

程序不写别的目录,只在自身文件夹里维护 `state.json` 和 `watcher.log`。
所有路径都相对脚本位置推导,整个文件夹复制到任何位置、任何机器都能跑。

### token:可以不填

| 情况 | 限额 | 说明 |
|---|---|---|
| 不填 token | 60 次/小时 | 匿名访问,**只能读公开仓库**。一轮检查用 2 次请求,单仓库 6 小时一轮完全够 |
| 填了 token | 5000 次/小时 | 私有仓库必须填。经典 token 勾 `repo` 权限即可,一个 token 能覆盖多个仓库 |

匿名读私有仓库会在日志里看到明确提示:

```
[你的仓库] 读取 PR 失败: Not Found —— 匿名访问只能读公开仓库;若这是私有仓库,请在 secrets/github-token.txt 里填一个 token
```

填 token 的方式:把 token 粘进 `secrets/github-token.txt`,一行,不要引号不要空格。

### config.json 每一项

```json
{
  "dailyTimes": ["10:00", "18:00", "22:00"],
  "pollMinutes": 360,
  "tokenFile": "secrets/github-token.txt",
  "watchIssues": true,
  "notifyUpdates": false,
  "notifyWhenQuiet": true,
  "notify": {
    "windows": true,
    "mail": { "smtp": "smtp.qq.com", "port": 465, "user": "you@qq.com", "code": "SMTP授权码", "to": "you@qq.com" },
    "serverchan": { "sendKey": "" }
  },
  "repos": [
    { "owner": "OWNER", "repo": "REPO", "enabled": true, "includePending": true }
  ]
}
```

| 字段 | 默认 | 作用 | 怎么改 |
|---|---|---|---|
| `dailyTimes` | `["10:00","18:00","22:00"]` | **固定检查时刻**,一天里这些点各查一次 | 想几点提醒就写几点,可加可减。设了就忽略 `pollMinutes`;写成 `[]` 或删掉则退回周期模式 |
| `pollMinutes` | 360 | 周期模式的轮询间隔,分钟 | 只在没有 `dailyTimes` 时生效 |
| `tokenFile` | `secrets/github-token.txt` | token 文件位置 | 相对本目录或绝对路径,只读第一行;文件不存在或为空 = 匿名访问 |
| `watchIssues` | true | 是否也盯 issue | `false` = 只盯 PR |
| `notifyUpdates` | false | 已有 PR 又提交了新版本 / issue 有新动态时是否再提醒 | `true` 打开,可能比较吵 |
| `notifyWhenQuiet` | true | 没有新提交时是否也发一份"无新提交"汇报 | `false` = 只在有新条目或有待处理时才发 |
| `notify.windows` | true | Windows 系统通知 | `false` 关掉 |
| `notify.mail.smtp` / `port` | smtp.qq.com / 465 | 发信服务器 | 换服务商时改;不需要邮件就整段留空 |
| `notify.mail.user` / `to` | — | 发件 / 收件地址 | 一般填一样 |
| `notify.mail.code` | — | SMTP **授权码** | 不是登录密码。QQ 邮箱要去设置里开启 SMTP 才能拿到 |
| `notify.serverchan.sendKey` | "" | Server酱微信推送 | 留空 = 关闭 |
| `repos[].owner` / `repo` | — | 组织/用户 和 仓库名 | 必填,可写多个 |
| `repos[].enabled` | true | 是否监控 | `false` = 静音这个仓库 |
| `repos[].watchIssues` | global | Watch issues for this repo | Per-repo override |
| `repos[].notifyUpdates` | global | Update notifications for this repo | Per-repo override |
| `repos[].includePending` | true | 该仓库的汇报里是否附「仍未处理」清单 | `false` = 只报新增(旧名字 `dailyReminder` 含义相同) |
| `repos[].tokenFile` | 继承全局 | 该仓库单独的 token | 跨账号时用 |

配置是每轮重新读的,改完存盘即生效,不用重启。
读取容错:UTF-8 / UTF-8 带 BOM / GBK / UTF-16 都能读;JSON 语法错会在日志里报明确原因,不会抛异常堆栈。

### 多个仓库

`repos` 是数组,想加多少加多少。每个仓库独立记状态(`state.json` 里按 `owner/repo` 分开),各自发一份汇报。

```json
"repos": [
  { "owner": "radiant-abyss", "repo": "HITCS_RadiantAbyss", "enabled": true },
  { "owner": "psf", "repo": "requests", "watchIssues": false, "includePending": true },
  { "owner": "someone", "repo": "another", "enabled": false, "tokenFile": "secrets/other-token.txt" }
]
```

| 每仓库可单独设 | 作用 |
|---|---|
| `enabled` | `false` = 不检查这个仓库 |
| `watchIssues` | 这个仓库只盯 PR,还是 PR + issue |
| `notifyUpdates` | 这个仓库的"更新"算不算新动态 |
| `includePending` | 这个仓库的汇报里要不要附「仍未处理」 |
| `tokenFile` | 跨账号时给这个仓库单独指定 token |

汇报是**按仓库分开**的:3 个仓库 × 每天 3 次 = 最多 9 封邮件/天。一轮检查每个仓库花 1–2 次 API 请求(只盯 PR 是 1 次,带 issue 是 2 次),带 token 时 5000 次/小时够用。
只想跑其中一个:`python pr_watcher.py --once --repo owner/repo`。

### 常用操作

| 目的 | 怎么做 |
|---|---|
| 开始 | 双击 `PRWatcher.exe`(后台无窗口;固定时刻模式等下一个检查时刻,周期模式才立即查一轮) |
| 停止 | 双击 `stop-watcher.bat`,最多一分钟退出 |
| 开机自启 | 把 `start-hidden.vbs` 的**快捷方式**丢进 `shell:startup`,或用管理员跑 `install-task.bat` |
| 查一轮就退出 | `python pr_watcher.py --once` |
| 自检(不联网) | `python pr_watcher.py --selftest` |
| 只查某个仓库 | `python pr_watcher.py --repo owner/repo` |
| 只看会发什么、不真发 | `python pr_watcher.py --dry-run`(把汇报内容打进日志) |
| 测通知能不能收到 | `python pr_watcher.py --test-notify`(会真发一封邮件) |
| 前台观察 | `python pr_watcher.py` |
| 加仓库 | `repos` 里加一行 `{ "owner": "...", "repo": "..." }` |
| 改检查时刻 | 改 `dailyTimes`,例如 `["08:30","13:00","21:00"]` |
| 汇报里不要待处理清单 | 该仓库项 `"includePending": false` |
| 改成周期模式 | 把 `dailyTimes` 写成 `[]`,再设 `pollMinutes` |
| 重新提醒所有条目 | 删 `state.json` |
| 搬到别的机器 | 拷整个文件夹 → `pip install requests` → 改 `config.json` → 双击 exe |

### 汇报内容

**每次检查都发一份汇报**,里面有两块:本次新增/更新,以及仍未处理的条目。

```
[HITCS_RadiantAbyss] 1 条新动态(1 PR) · 2 个待处理(2 PR)

本次新增(1):
- #7 [PR] 修改第三章 <草稿> & 补充公式 · @someone

仍未处理(2):
- #4 [PR] Add hello world! to name.txt · @someone(已 18 天)
- #3 [PR] Second round test · @someone(已 19 天)
```

没有新条目时也会发,标题和正文都会写明"无新提交":

```
[HITCS_RadiantAbyss] 无新提交 · 2 个待处理(2 PR)

本次新增:无新提交

仍未处理(2):
- #4 ...
```

一个仓库什么都没有(没有 open 条目、也没有新增)时是 `[仓库] 无新提交 · 无待处理`。
不想要这种"没事也报一声",就把 `notifyWhenQuiet` 设成 `false`,那样只在真有新条目或有待处理时才发。

只有一条新增且没有待处理时,标题直接写 `[仓库] 新 PR #7: 标题`。
正文最多列 10 条,多余的只报数量。弹窗标题是标题里的那串摘要,正文是第一条的标题 + 作者。

「仍未处理」= **之前就报过、现在还开着的**那些;本轮新增/更新的条目只在上面那块出现,不会重复列一遍(它们从下一份汇报开始进入「仍未处理」)。

判重方式:按 `PR/issue 编号` 记在 `state.json`,同一个编号只算一次"新";已经报过的条目之后每次会出现在「仍未处理」里,直到被合并或关闭。
开了 `notifyUpdates` 后,PR 有新提交(head commit 变化)或 issue 有新动态会再算一次"更新"。
关掉 `watchIssues` 期间已记录的 issue 会保留,重新打开不会重发一遍。
不想要「仍未处理」这块,就把该仓库的 `includePending` 设成 `false`(旧写法 `dailyReminder` 等价)。

### 提交到 git

`.gitignore` 已经排好,下面这些不要进版本库:

| 不该提交 | 为什么 |
|---|---|
| `secrets/` | GitHub token |
| `config.json` | 里面有 SMTP 授权码和仓库清单 |
| `state.json` | 已提醒记录,每台机器不一样 |
| `watcher.log`、`launcher.log` | 日志 |
| `watcher.pid`、`watcher.lock`、`watcher.stop` | 运行时的锁和标记 |
| `__pycache__/` | Python 缓存 |

可以提交的:`pr_watcher.py`、`PRWatcher.exe`、`launcher.cs`、`start-hidden.vbs`、`stop-watcher.bat`、`install-task.bat`、`config.example.json`、`.gitignore`、`README.md`。

### 出问题先看哪里

先看 `watcher.log`,正常每轮都有一行小结:

```
[2026-09-14 20:01:46] [你的仓库] 检查完成: 2 PR · 0 issue
```

| 日志 / 现象 | 原因 | 处理 |
|---|---|---|
| 双击 exe 没反应 | 启动失败 | 看 `launcher.log`,弹窗也会说明;通常是没装 Python 或没装 requests |
| `[配置错误] config.json 无法解析` | JSON 语法错 | 多余逗号、注释、中文引号都会导致;改完 `--selftest` 复查 |
| `API 失败: Not Found` | 仓库名错,或者匿名读私有仓库 | 核对 owner/repo;私有仓库补 token |
| `API 失败: 401` | token 过期或被撤销 | 重新生成一个 |
| 收不到邮件 | 授权码或 SMTP 没开 | `code` 必须是授权码不是登录密码 |
| `Windows 通知失败` | 系统弹窗被策略禁用 | 邮件通道不受影响 |
| 停不下来 | 标记没生效 | 再跑一次 `stop-watcher.bat` 等一分钟;仍不行就删 `watcher.lock` 并结束 `pythonw.exe` |

### 边界

- 只用 `GET` 读 GitHub:`/pulls` 和 `/issues`。不评论、不合并、不改状态,不向 GitHub 写任何东西
- 不克隆仓库、不检出代码、不下载 PR 里的文件、不执行任何内容
- token 只存在本地文本文件里,不进代码、不进日志
- 单类最多读 300 条 open 条目(3 页),超出只统计前 300
- 没有额外的失败重试:某轮接口失败会记进日志,下一轮再来

---

## English

### Requirements

**PR-Watcher is designed for Windows.** You need Windows 10/11, Python 3 and `requests` (`pip install requests`).

Toasts go through Windows notifications, the single-instance lock uses `msvcrt`, and start/stop/autostart are
`.bat` / `.vbs` / Task Scheduler. These are deliberate Windows choices; no other platform is targeted.

### Quick start

```
1. Install Python 3 and requests
2. Copy config.example.json to config.json and fill in your repo and mailbox
3. Only needed for private repos: put a token into secrets/github-token.txt
4. Double-click PRWatcher.exe
```

You know it is running when `watcher.log` shows lines like these:

```
[2026-09-14 20:01:46] PR Watcher 启动: 1 个仓库 · 每天 10:00 / 18:00 / 22:00 检查
[2026-09-14 20:01:46] 下次检查: 09-14 22:00
```

By default it runs on a **fixed schedule**: every day at 10:00, 18:00 and 22:00. It does not check at startup,
so notifications only land on those times. For an immediate check run `python pr_watcher.py --once`.
Set `dailyTimes` to `[]` or remove it to fall back to interval mode (`pollMinutes`): one check at startup,
then one every N minutes.

### What each file does

| File | Purpose | Do I edit it? |
|---|---|---|
| `config.json` | All settings: repos, token path, notifications, interval | **Yes** (copy it from `config.example.json`) |
| `secrets/github-token.txt` | GitHub token | Depends — see below |
| `state.json` | Already-notified numbers, auto-generated | No. Delete it to have every open item counted as new again |
| `pr_watcher.py` | The program | Usually no |
| `PRWatcher.exe` | Double-click launcher, runs hidden | No |
| `launcher.cs` | Launcher source | Rebuild with csc: `csc /nologo /target:winexe /r:System.Windows.Forms.dll /out:PRWatcher.exe launcher.cs` |
| `start-hidden.vbs` | Hidden launch, used for autostart | No. Keep it plain ASCII + CRLF |
| `stop-watcher.bat` | Stop it | No |
| `install-task.bat` | Optional: register a logon scheduled task | Run as Administrator |
| `watcher.log` | Runtime log, one summary line per round | Read |
| `launcher.log` | Launcher log | Read this first if double-clicking does nothing |
| `config.example.json` | Config template with no secrets | No |

It writes nothing outside its own folder — only `state.json` and `watcher.log`.
Every path is derived from the script location, so the whole folder can be copied anywhere, to any machine.

### The token is optional

| Case | Rate limit | Notes |
|---|---|---|
| No token | 60 req/hour | Anonymous access, **public repos only**. One round costs 2 requests, so a 6-hour interval is plenty |
| With a token | 5000 req/hour | Required for private repos. A classic token with `repo` scope covers multiple repos |

Reading a private repo anonymously logs a clear hint:

```
[your-repo] 读取 PR 失败: Not Found —— 匿名访问只能读公开仓库;若这是私有仓库,请在 secrets/github-token.txt 里填一个 token
```

To use a token, paste it into `secrets/github-token.txt` — one line, no quotes, no spaces.

### config.json reference

```json
{
  "dailyTimes": ["10:00", "18:00", "22:00"],
  "pollMinutes": 360,
  "tokenFile": "secrets/github-token.txt",
  "watchIssues": true,
  "notifyUpdates": false,
  "notifyWhenQuiet": true,
  "notify": {
    "windows": true,
    "mail": { "smtp": "smtp.qq.com", "port": 465, "user": "you@qq.com", "code": "app-password", "to": "you@qq.com" },
    "serverchan": { "sendKey": "" }
  },
  "repos": [
    { "owner": "OWNER", "repo": "REPO", "enabled": true, "includePending": true }
  ]
}
```

| Field | Default | Meaning | How to change |
|---|---|---|---|
| `dailyTimes` | `["10:00","18:00","22:00"]` | **Fixed check times** — one check at each of these times every day | Add or remove times as you like. When set, `pollMinutes` is ignored; set it to `[]` or delete it to go back to interval mode |
| `pollMinutes` | 360 | Poll interval in minutes, interval mode only | Used only when `dailyTimes` is absent |
| `tokenFile` | `secrets/github-token.txt` | Where the token lives | Relative to this folder or absolute; only the first line is read. Missing or empty file = anonymous |
| `watchIssues` | true | Also watch issues | `false` = pull requests only |
| `notifyUpdates` | false | Re-notify when a known PR gets new commits or an issue gets new activity | Set `true` if you want it (can get noisy) |
| `notifyWhenQuiet` | true | Also send the "无新提交" report when nothing is new | `false` = only send when there is something new or still open |
| `notify.windows` | true | Windows toast | `false` to disable |
| `notify.mail.smtp` / `port` | smtp.qq.com / 465 | SMTP server | Change for another provider; leave the whole block empty for no email |
| `notify.mail.user` / `to` | — | Sender / recipient | Usually the same address |
| `notify.mail.code` | — | SMTP **app password** | Not your login password. QQ Mail requires enabling SMTP first |
| `notify.serverchan.sendKey` | "" | ServerChan (WeChat) push | Empty = disabled |
| `repos[].owner` / `repo` | — | Owner and repo name | Required; add as many entries as you like |
| `repos[].enabled` | true | Watch this repo | `false` = mute it |
| `repos[].watchIssues` | global | Watch issues for this repo | Per-repo override |
| `repos[].notifyUpdates` | global | Update notifications for this repo | Per-repo override |
| `repos[].includePending` | true | Include the "still open" list in this repo's report | `false` = new items only (the old name `dailyReminder` works the same way) |
| `repos[].tokenFile` | global | Separate token for this repo | For repos under another account |

The config is re-read every round, so edits apply immediately — no restart needed.
Encoding is forgiving (UTF-8, UTF-8 with BOM, GBK, UTF-16). Broken JSON is reported with a clear
reason in the log instead of a stack trace.

### Multiple repos

`repos` is an array — add as many as you like. Each repo keeps its own state (separate `owner/repo` keys
in `state.json`) and gets its own report.

```json
"repos": [
  { "owner": "radiant-abyss", "repo": "HITCS_RadiantAbyss", "enabled": true },
  { "owner": "psf", "repo": "requests", "watchIssues": false, "includePending": true },
  { "owner": "someone", "repo": "another", "enabled": false, "tokenFile": "secrets/other-token.txt" }
]
```

| Per-repo override | Effect |
|---|---|
| `enabled` | `false` = skip this repo entirely |
| `watchIssues` | Watch PRs only, or PRs + issues, for this repo |
| `notifyUpdates` | Whether updates count as new activity for this repo |
| `includePending` | Whether this repo's report carries the "still open" block |
| `tokenFile` | Separate token for this repo (different accounts) |

Reports are **per repo**: 3 repos × 3 checks a day = up to 9 emails a day. A check costs 1–2 API requests
per repo (1 for PRs only, 2 with issues), so a 5000/hour token is plenty. To run just one:
`python pr_watcher.py --once --repo owner/repo`.

### Common operations

| Goal | How |
|---|---|
| Start | Double-click `PRWatcher.exe` (runs hidden; fixed-schedule mode waits for the next check time, interval mode checks once right away) |
| Stop | Double-click `stop-watcher.bat`; it exits within a minute |
| Autostart | Drop a **shortcut** to `start-hidden.vbs` into `shell:startup`, or run `install-task.bat` as Administrator |
| Single check, then exit | `python pr_watcher.py --once` (sends a report) |
| Offline self-test | `python pr_watcher.py --selftest` |
| Check one repo only | `python pr_watcher.py --repo owner/repo` |
| Preview a report without sending | `python pr_watcher.py --dry-run` (logs the report text) |
| Test notifications | `python pr_watcher.py --test-notify` (sends a real email) |
| Watch it in the foreground | `python pr_watcher.py` |
| Add a repo | Add a line to `repos`: `{ "owner": "...", "repo": "..." }` |
| Change check times | Edit `dailyTimes`, e.g. `["08:30","13:00","21:00"]` |
| Drop the "still open" block | Set `"includePending": false` on that repo |
| Switch to interval mode | Set `dailyTimes` to `[]` and configure `pollMinutes` |
| Re-alert everything | Delete `state.json` |
| Move to another machine | Copy the folder → `pip install requests` → edit `config.json` → double-click the exe |

### What a report looks like

**Every check sends one report**, with two blocks: what is new or updated, and what is still open.

```
[HITCS_RadiantAbyss] 1 条新动态(1 PR) · 2 个待处理(2 PR)

本次新增(1):
- #7 [PR] 修改第三章 <草稿> & 补充公式 · @someone

仍未处理(2):
- #4 [PR] Add hello world! to name.txt · @someone(已 18 天)
- #3 [PR] Second round test · @someone(已 19 天)
```

When nothing is new it still sends one, saying so in both the subject and the body:

```
[HITCS_RadiantAbyss] 无新提交 · 2 个待处理(2 PR)

本次新增:无新提交

仍未处理(2):
- #4 ...
```

A repo with nothing at all (no open items, nothing new) reports `[repo] 无新提交 · 无待处理`.
Set `notifyWhenQuiet` to `false` if you would rather only hear about it when there is something to act on.

With a single new item and nothing pending the subject is `[repo] 新 PR #7: <title>`. Up to 10 entries are
listed; the rest are counted. The toast shows the same summary as its title and the first entry as its body.

The "still open" block lists items that were **already reported before and are still open**. Anything new or
updated in this round appears only in the block above — it is never listed twice, and it moves into
"still open" starting with the next report.

De-duplication is by `PR/issue number`, stored in `state.json`. A number counts as "new" only once; after that
it keeps showing up in the "still open" block until it is merged or closed. With `notifyUpdates` enabled, a PR
with new commits (changed head SHA) or an issue with new activity counts as an update too. Issue history is kept
while `watchIssues` is off, so turning it back on does not re-send everything. To drop the "still open" block
for a repo, set `includePending` to `false` (the old key `dailyReminder` behaves the same).

### Committing to git

`.gitignore` is already set up. Do not commit:

| Don't commit | Why |
|---|---|
| `secrets/` | GitHub token |
| `config.json` | Contains your SMTP app password and repo list |
| `state.json` | Per-machine notification history |
| `watcher.log`, `launcher.log` | Logs |
| `watcher.pid`, `watcher.lock`, `watcher.stop` | Runtime lock and flags |
| `__pycache__/` | Python cache |

Safe to commit: `pr_watcher.py`, `PRWatcher.exe`, `launcher.cs`, `start-hidden.vbs`, `stop-watcher.bat`,
`install-task.bat`, `config.example.json`, `.gitignore`, `README.md`.

### Troubleshooting

Start with `watcher.log`. A healthy round looks like this:

```
[2026-09-14 20:01:46] [your-repo] 检查完成: 2 PR · 0 issue
```

| Symptom | Cause | Fix |
|---|---|---|
| Double-clicking the exe does nothing | Launch failed | Check `launcher.log`; a dialog also explains it. Usually Python or `requests` is missing |
| `[配置错误] config.json 无法解析` | JSON syntax error | Trailing commas, comments and curly quotes all break it; re-run `--selftest` after fixing |
| `API 失败: Not Found` | Wrong repo name, or anonymous access to a private repo | Check owner/repo; add a token for private repos |
| `API 失败: 401` | Token expired or revoked | Generate a new one |
| No email arrives | App password or SMTP disabled | `code` must be the app password, not the login password |
| `Windows 通知失败` | System toasts blocked by policy | Email still works |
| It will not stop | Stop flag not seen | Run `stop-watcher.bat` again and wait a minute; otherwise delete `watcher.lock` and end `pythonw.exe` |

### Scope and limits

- Read-only: only `GET /pulls` and `GET /issues`. No comments, no merges, no state changes, nothing written to GitHub
- No clone, no checkout, no downloading PR files, no executing anything from a PR
- The token stays in a local text file; it never appears in code or logs
- At most 300 open items per type (3 pages); beyond that only the first 300 are counted
- No extra retries: a failed round is logged and the next round tries again
