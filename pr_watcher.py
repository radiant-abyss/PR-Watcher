#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PR Watcher v3 — 只提醒,不分析
================================
盯着配置里的仓库:有人提 PR / 开 issue 就发通知(Windows 通知 + 邮件 + 可选 Server酱)。
不克隆仓库、不检出代码、不生成分析报告;未处理的 PR / issue 每天汇总提醒一次。

与安装目录解耦:所有路径都相对本脚本所在目录,整个文件夹拷到任何机器都能直接跑。

目录结构(自包含):
  <install>/
    pr_watcher.py       主程序
    PRWatcher.exe       双击启动器
    config.json         配置:仓库、token、通知、周期
    secrets/            token
    state.json          已提醒过的 PR / issue,以及每日提醒日期
    watcher.log         运行日志(每轮一行小结)

用法:
  python pr_watcher.py              常驻循环
  python pr_watcher.py --once       检查一轮后退出
  python pr_watcher.py --selftest   离线自检
  python pr_watcher.py --test-notify 发送测试通知
  python pr_watcher.py --repo a/b   只检查指定仓库

安全边界:只用 GET 读 GitHub API;不写 GitHub、不评论、不合并;不下载也不执行 PR 里的任何代码。
"""

import argparse
import html as html_mod
import json
import os
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("缺少 requests 库,请先执行: pip install requests")
    sys.exit(1)

# ---------- 路径(全部相对脚本目录,便携) ----------
BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
STATE_PATH = BASE / "state.json"
LOG_PATH = BASE / "watcher.log"
LOCK_PATH = BASE / "watcher.lock"
PID_PATH = BASE / "watcher.pid"
STOP_PATH = BASE / "watcher.stop"

MAX_LISTED = 10          # 一条通知里最多列几个条目,多出来的只报数量


# ---------- 工具 ----------
def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_text(path: Path):
    """宽容读取:UTF-8 / UTF-8 带 BOM / GBK / UTF-16 都能读。"""
    try:
        raw = Path(path).read_bytes()
    except Exception:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def load_json(path: Path, default=None):
    txt = read_text(path)
    if txt is None:
        return default
    try:
        return json.loads(txt)
    except Exception:
        return default


def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def resolve_path(p: str) -> Path:
    """相对路径按脚本目录解析;绝对路径原样使用。"""
    if not p:
        return BASE
    path = Path(p)
    return path if path.is_absolute() else (BASE / path)


# ---------- 配置 ----------
DEFAULT_CONFIG = {
    "dailyTimes": ["10:00", "18:00", "22:00"],
    "pollMinutes": 360,
    "tokenFile": "secrets/github-token.txt",
    "watchIssues": True,
    "notifyUpdates": False,
    "notify": {
        "windows": True,
        "mail": {"smtp": "smtp.qq.com", "port": 465, "user": "", "code": "", "to": ""},
        "serverchan": {"sendKey": ""},
    },
    "repos": [
        {"owner": "OWNER", "repo": "REPO", "enabled": True}
    ],
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        write_text(CONFIG_PATH, json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2))
        raise RuntimeError(f"已生成配置模板 {CONFIG_PATH},请填写 repos 后重试")
    cfg = load_json(CONFIG_PATH, None)
    if not isinstance(cfg, dict):
        raise RuntimeError(f"config.json 无法解析(检查 JSON 语法/编码): {CONFIG_PATH}")
    cfg.setdefault("pollMinutes", 360)
    cfg.setdefault("tokenFile", "secrets/github-token.txt")
    cfg.setdefault("watchIssues", True)
    cfg.setdefault("notifyUpdates", False)
    notify = cfg.setdefault("notify", {})
    if not isinstance(notify, dict):
        cfg["notify"] = {}
        notify = cfg["notify"]
    notify.setdefault("windows", True)
    cfg["repos"] = [x for x in cfg.get("repos", []) if isinstance(x, dict) and x.get("owner") and x.get("repo")]
    if not cfg["repos"]:
        raise RuntimeError(f"config.json 里 repos 为空,请至少填写一个 "
                           f'{{"owner": "...", "repo": "..."}} 后重试: {CONFIG_PATH}')
    return cfg


def load_token(cfg: dict, r: dict) -> str:
    token_file = r.get("tokenFile") or cfg.get("tokenFile", "")
    if not token_file:
        return ""
    raw = read_text(resolve_path(str(token_file)))
    if not raw:
        return ""
    lines = raw.splitlines()
    return lines[0].strip() if lines else ""


# ---------- GitHub(只读) ----------
def gh_api(token: str, path: str, timeout=30):
    """token 为空 = 匿名访问(GitHub 允许匿名读公开仓库,限额 60 次/小时)。"""
    url = f"https://api.github.com{path}"
    headers = {"User-Agent": "pr-watcher", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except Exception as e:
        return None, str(e)
    try:
        data = resp.json()
    except Exception:
        return None, f"HTTP {resp.status_code} 非 JSON 响应"
    if resp.status_code >= 400:
        msg = data.get("message", f"HTTP {resp.status_code}") if isinstance(data, dict) else f"HTTP {resp.status_code}"
        return None, msg
    return data, None


def gh_list(token: str, path: str, max_pages=3):
    """分页读取开放列表(每页 100 条,最多 3 页 = 300 条)。"""
    out = []
    for page in range(1, max_pages + 1):
        sep = "&" if "?" in path else "?"
        data, err = gh_api(token, f"{path}{sep}per_page=100&page={page}")
        if data is None:
            return None, err
        if not isinstance(data, list):
            return None, "响应格式异常"
        out.extend(data)
        if len(data) < 100:
            break
    return out, None


def fetch_open_items(token: str, owner: str, repo: str, watch_issues: bool):
    """返回 (items, err)。item 只保留通知要用的几个字段,不带 GitHub 原始对象。"""
    items = []
    pulls, err = gh_list(token, f"/repos/{owner}/{repo}/pulls?state=open&sort=created&direction=desc")
    if pulls is None:
        return None, f"读取 PR 失败: {err}"
    for p in pulls:
        items.append({
            "type": "pr",
            "number": p.get("number"),
            "title": str(p.get("title") or ""),
            "author": str(((p.get("user") or {}).get("login")) or "?"),
            "url": str(p.get("html_url") or ""),
            "createdAt": str(p.get("created_at") or ""),
            "updatedAt": str(p.get("updated_at") or ""),
            "headSha": str((p.get("head") or {}).get("sha") or ""),
        })
    if watch_issues:
        issues, err = gh_list(token, f"/repos/{owner}/{repo}/issues?state=open&sort=created&direction=desc")
        if issues is None:
            return None, f"读取 issue 失败: {err}"
        for i in issues:
            if "pull_request" in i:          # issues 接口会把 PR 一起返回,排掉
                continue
            items.append({
                "type": "issue",
                "number": i.get("number"),
                "title": str(i.get("title") or ""),
                "author": str(((i.get("user") or {}).get("login")) or "?"),
                "url": str(i.get("html_url") or ""),
                "createdAt": str(i.get("created_at") or ""),
                "updatedAt": str(i.get("updated_at") or ""),
                "headSha": "",
            })
    return items, None


# ---------- 状态 ----------
def load_state() -> dict:
    st = load_json(STATE_PATH, {})
    return st if isinstance(st, dict) else {}


def save_state(state: dict):
    write_text(STATE_PATH, json.dumps(state, ensure_ascii=False, indent=2))


def repo_state(state: dict, key: str) -> dict:
    rs = state.get(key)
    if not isinstance(rs, dict):
        rs = {}
        state[key] = rs
    rs.setdefault("items", {})
    rs.setdefault("remindDate", "")
    # v2 → v3 迁移:老的 seen 里记的都是 PR 编号,补进 items,避免重复提醒
    old_seen = rs.pop("seen", None)
    if isinstance(old_seen, dict):
        for num in old_seen.keys():
            rs["items"].setdefault(f"pr#{num}", {"type": "pr", "number": int(num), "migrated": True})
    rs.pop("reports", None)
    return rs


# ---------- 通知 ----------
def notify_windows(title: str, body: str):
    script = (
        "$ErrorActionPreference='SilentlyContinue'\n"
        "$ProgressPreference='SilentlyContinue'\n"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null\n"
        "$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)\n"
        "$txts = $tpl.GetElementsByTagName('text')\n"
        "$txts.Item(0).AppendChild($tpl.CreateTextNode($env:NT_TITLE)) | Out-Null\n"
        "$txts.Item(1).AppendChild($tpl.CreateTextNode($env:NT_BODY)) | Out-Null\n"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)\n"
        "([Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('PR Watcher')).Show($toast)\n"
    )
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           env=dict(os.environ, NT_TITLE=title, NT_BODY=body),
                           capture_output=True, timeout=25)
        if p.returncode != 0:
            err = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            log(f"Windows 通知失败(弹窗没出来): {err[-1][:120] if err else '退出码 ' + str(p.returncode)}")
    except Exception as e:
        log(f"Windows 通知异常: {e}")


def notify_mail(cfg: dict, title: str, html: str):
    mail = (cfg.get("notify") or {}).get("mail")
    if not isinstance(mail, dict):
        return
    user, pwd, to = str(mail.get("user", "")), str(mail.get("code", "")), str(mail.get("to", ""))
    if not (user and pwd and to):
        return
    smtp = str(mail.get("smtp", "smtp.qq.com") or "smtp.qq.com")
    try:
        port = int(mail.get("port", 465))
    except Exception:
        port = 465
    try:
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = Header(title, "utf-8")
        msg["From"] = user
        msg["To"] = to
        s = smtplib.SMTP_SSL(smtp, port, timeout=25)
        try:
            s.login(user, pwd)
            s.sendmail(user, [to], msg.as_string())
        finally:
            try:
                s.quit()
            except Exception:
                pass
        log(f"邮件已发送到 {to}")
    except Exception as e:
        log(f"邮件发送失败: {e}")


def notify_serverchan(cfg: dict, title: str, body: str):
    sc = (cfg.get("notify") or {}).get("serverchan")
    key = str((sc or {}).get("sendKey", "") or "") if isinstance(sc, dict) else ""
    if not key:
        return
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": title, "desp": body}, timeout=15)
        if r.status_code != 200:
            log(f"Server酱推送失败: HTTP {r.status_code}")
    except Exception as e:
        log(f"Server酱推送异常: {e}")


def dispatch(cfg: dict, title: str, body: str, html: str, toast_title: str = "", toast_body: str = ""):
    notify = cfg.get("notify") or {}
    if notify.get("windows", True):
        notify_windows(toast_title or title, toast_body or body)
    notify_mail(cfg, title, html)
    notify_serverchan(cfg, title, html)


def kind_label(it: dict) -> str:
    return "PR" if it["type"] == "pr" else "Issue"


def one_line(it: dict) -> str:
    return f"#{it['number']} [{kind_label(it)}] {it['title']} · @{it['author']}"


def notify_report(cfg: dict, r: dict, fresh: list, updated: list, pending: list,
                  show_pending: bool = True, dry: bool = False) -> bool:
    """一份汇报 = 本次新增 / 本次更新 + 仍未处理。默认每次检查都发,无新提交也会写明「无新提交」。"""
    total_new = len(fresh) + len(updated)
    quiet_ok = bool(r.get("notifyWhenQuiet", cfg.get("notifyWhenQuiet", True)))
    if not (total_new or pending) and not quiet_ok:
        return False

    def stat(items: list) -> str:
        prs = sum(1 for x in items if x["type"] == "pr")
        iss = len(items) - prs
        bits = [f"{prs} PR" if prs else "", f"{iss} issue" if iss else ""]
        return " + ".join(b for b in bits if b)

    only_item = (fresh + updated)[0] if total_new == 1 else None
    if only_item is not None and not pending:
        title = f"[{r['repo']}] {'新' if fresh else '更新'} {kind_label(only_item)} #{only_item['number']}: {only_item['title'][:40]}"
        toast_title = f"{r['repo']}: {'新' if fresh else '更新'} {kind_label(only_item)} #{only_item['number']}"
        toast_body = f"{only_item['title'][:60]} · @{only_item['author']}"
    else:
        bits = [f"{total_new} 条新动态({stat(fresh + updated)})" if total_new else "无新提交"]
        if show_pending:
            bits.append(f"{len(pending)} 个待处理({stat(pending)})" if pending else "无待处理")
        short = " · ".join(bits)
        title = f"[{r['repo']}] {short}"
        toast_title = f"{r['repo']}: {short}"
        pool = fresh + updated + pending
        toast_body = (one_line(pool[0])[:70] + " 等" if len(pool) > 1 else
                      (one_line(pool[0])[:70] if pool else "本次没有新提交,也没有待处理条目"))

    # 纯文本版(Server酱 / 弹窗兜底)
    blocks = []
    blocks.append("本次新增(%d):\n" % len(fresh) + section_text(fresh) if fresh else "本次新增:无新提交")
    if updated:
        blocks.append("本次更新(%d):\n" % len(updated) + section_text(updated))
    if show_pending:
        blocks.append("仍未处理(%d):\n" % len(pending) + section_text(pending, with_days=True)
                      if pending else "仍未处理:无")
    body = "\n\n".join(blocks)

    # 邮件 HTML 版
    parts = []
    parts.append(f"<h3>本次新增({len(fresh)})</h3>\n<ul>\n{section_html(fresh)}\n</ul>" if fresh
                 else "<h3>本次新增</h3>\n<p>无新提交</p>")
    if updated:
        parts.append(f"<h3>本次更新({len(updated)})</h3>\n<ul>\n{section_html(updated)}\n</ul>")
    if show_pending:
        parts.append(f"<h3>仍未处理({len(pending)})</h3>\n<ul>\n{section_html(pending, with_days=True)}\n</ul>"
                     if pending else "<h3>仍未处理</h3>\n<p>无</p>")
    html = (f"<h2>{r['owner']}/{r['repo']}</h2>\n" + "\n".join(parts))

    if dry:
        log(f"(dry-run) {title}")
        for line in body.splitlines():
            log(f"(dry-run)   {line}")
        return False
    dispatch(cfg, title, body, html, toast_title, toast_body)
    log(f"已发送汇报: {title}")
    return True


def section_text(items: list, with_days: bool = False) -> str:
    shown = items[:MAX_LISTED]
    lines = [f"- {one_line(x)}" + (f"(已 {x['days']} 天)" if with_days else "") for x in shown]
    if len(items) > len(shown):
        lines.append(f"…另有 {len(items) - len(shown)} 条")
    return "\n".join(lines)


def section_html(items: list, with_days: bool = False) -> str:
    shown = items[:MAX_LISTED]
    lis = "\n".join(
        f'<li><b>{kind_label(x)} #{x["number"]}</b> {html_mod.escape(x["title"])} — '
        f'@{html_mod.escape(x["author"])}' + (f" · 已 {x['days']} 天" if with_days else "") +
        f' · <a href="{x["url"]}">打开</a></li>'
        for x in shown)
    if len(items) > len(shown):
        lis += f"\n<li>…另有 {len(items) - len(shown)} 条</li>"
    return lis


# ---------- 单仓库一轮 ----------
def days_since(iso: str) -> int:
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
        return max((datetime.now().date() - d).days, 0)
    except Exception:
        return 0


def check_repo(cfg: dict, r: dict, state: dict, dry: bool = False) -> str:
    """返回错误信息(成功返回空串)。"""
    owner, repo, name = r["owner"], r["repo"], r["repo"]
    token = load_token(cfg, r)          # 为空就走匿名访问(公开仓库足够用)
    rs = repo_state(state, f"{owner}/{repo}")
    watch_issues = bool(r.get("watchIssues", cfg.get("watchIssues", True)))
    notify_updates = bool(r.get("notifyUpdates", cfg.get("notifyUpdates", False)))
    # 汇报里是否附上"仍未处理"清单(旧字段名 dailyReminder 等价)
    include_pending = bool(r.get("includePending", r.get("dailyReminder", cfg.get("includePending", True))))

    items, err = fetch_open_items(token, owner, repo, watch_issues)
    if items is None:
        if not token and "Not Found" in str(err):
            return (f"{err} —— 匿名访问只能读公开仓库;若这是私有仓库,请在 "
                    f"{r.get('tokenFile') or cfg.get('tokenFile')} 里填一个 token")
        return err

    fresh, updated, current = [], [], {}
    for it in items:
        if not isinstance(it.get("number"), int):
            continue
        key = f"{it['type']}#{it['number']}"
        current[key] = it
        old = rs["items"].get(key)
        if not isinstance(old, dict):
            fresh.append(it)
        elif notify_updates and old.get("migrated") is not True:
            if it["type"] == "pr":
                changed = bool(it["headSha"]) and it["headSha"] != old.get("headSha")
            else:
                changed = bool(it["updatedAt"]) and it["updatedAt"] != old.get("updatedAt")
            if changed:
                updated.append(it)

    fresh.sort(key=lambda x: x["number"], reverse=True)
    updated.sort(key=lambda x: x["number"], reverse=True)

    # 状态里只留还开着的条目;关掉/合并掉的自动清掉(再打开会重新提醒一次)
    # 注意:本轮没检查的类型(比如关掉 issue 监控)要原样保留,否则再打开会当成新条目重发一遍
    keep = {} if watch_issues else {k: v for k, v in rs["items"].items() if k.startswith("issue#")}
    rs["items"] = {**keep,
                   **{k: {"type": v["type"], "number": v["number"], "title": v["title"],
                          "author": v["author"], "url": v["url"], "createdAt": v["createdAt"],
                          "updatedAt": v["updatedAt"], "headSha": v["headSha"]}
                      for k, v in current.items()}}
    rs.pop("remindDate", None)          # v3.1 起不再需要"今天提醒过没有"的标记

    pending = []
    if include_pending:
        # 「仍未处理」= 之前就报过、现在还开着的;本轮新增/更新的已经在上面单列,不重复出现
        new_keys = {f"{x['type']}#{x['number']}" for x in fresh + updated}
        pending = sorted(({**v, "days": days_since(v["createdAt"])}
                          for k, v in current.items() if k not in new_keys),
                         key=lambda x: x["days"], reverse=True)

    sent = notify_report(cfg, r, fresh, updated, pending, show_pending=include_pending, dry=dry)
    if not dry:
        save_state(state)               # dry-run 只读不改状态

    prs = sum(1 for v in current.values() if v["type"] == "pr")
    iss = len(current) - prs
    parts = [f"{prs} PR", f"{iss} issue"]
    if fresh:
        parts.append(f"新增 {len(fresh)}")
    if updated:
        parts.append(f"更新 {len(updated)}")
    parts.append("dry-run 未发送" if dry else ("已发汇报" if sent else "未发汇报(无新提交也关掉了)"))
    log(f"[{name}] 检查完成: " + " · ".join(parts))
    return ""


def check_all(cfg: dict, only: str = "", dry: bool = False):
    state = load_state()
    ran = 0
    for r in cfg["repos"]:
        if r.get("enabled", True) is False:
            log(f"[{r['repo']}] 已禁用,跳过")
            continue
        if only and f"{r['owner']}/{r['repo']}" != only:
            continue
        ran += 1
        try:
            err = check_repo(cfg, r, state, dry=dry)
            if err:
                log(f"[{r['repo']}] {err}")
        except Exception as e:
            log(f"[{r['repo']}] 异常: {e}")
    if not ran:
        log("没有需要检查的仓库(检查 config.json 的 repos / enabled / --repo 参数)")


# ---------- 单实例 / 生命周期 ----------
def acquire_single_instance() -> bool:
    """以文件锁为准(进程退出/崩溃时 OS 自动释放,不会因 PID 复用误判)。"""
    import msvcrt
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        return False


def release_single_instance():
    try:
        PID_PATH.unlink(missing_ok=True)
        LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


# ---------- 子命令 ----------
def selftest():
    print("== PR Watcher v3 自检(不联网) ==")
    print(f"安装目录: {BASE}")
    try:
        cfg = load_config()
    except Exception as e:
        print(f"[FAIL] 配置: {e}")
        return
    times = parse_times(cfg)
    if times:
        print(f"[OK] 配置: {repo_summary(cfg)} · 每天 {fmt_times(times)} 检查(固定时刻)")
    else:
        print(f"[OK] 配置: {repo_summary(cfg)} · 每 {cfg['pollMinutes']} 分钟(周期模式,未设 dailyTimes)")
    print(f"     issue 监控={'开' if cfg.get('watchIssues', True) else '关'} · "
          f"更新提醒={'开' if cfg.get('notifyUpdates') else '关'} · "
          f"汇报含待处理={'开' if cfg.get('includePending', True) else '关'}")
    notify = cfg.get("notify") or {}
    mail = notify.get("mail") or {}
    print(f"[{'OK' if notify.get('windows', True) else 'OFF'}] Windows 通知")
    print(f"[{'OK' if mail.get('user') and mail.get('code') else 'WARN'}] 邮件: {mail.get('to') or '(未配置)'}")
    if (notify.get("serverchan") or {}).get("sendKey"):
        print("[OK] Server酱")
    st = load_state()
    for r in cfg["repos"]:
        token = load_token(cfg, r)
        rs = st.get(f"{r['owner']}/{r['repo']}") or {}
        n = len(rs.get("items") or {})
        inc = bool(r.get("includePending", r.get("dailyReminder", cfg.get("includePending", True))))
        print(f"  - {r['owner']}/{r['repo']}: "
              f"token={'有' if token else '无 → 匿名访问(仅公开仓库,60 次/小时)'} · "
              f"范围={'PR+Issue' if r.get('watchIssues', cfg.get('watchIssues', True)) else '仅 PR'} · "
              f"汇报含待处理={'是' if inc else '否'} · 已记录 {n} 条")
    print("[OK] 自检完成。`--once` 查一轮并汇报;`--dry-run` 只看不发;`--test-notify` 测通道;不带参数常驻。")


def when_text(cfg: dict) -> str:
    """给人看的"什么时候检查":有 dailyTimes 就是固定时刻,否则是周期。"""
    times = parse_times(cfg)
    return f"检查时刻: {fmt_times(times)}" if times else f"周期: 每 {cfg['pollMinutes']} 分钟"


def test_notify(cfg: dict):
    repos = ", ".join(x["repo"] for x in cfg["repos"])
    when = when_text(cfg)
    quiet = "无新提交也发" if cfg.get("notifyWhenQuiet", True) else "无新提交不发"
    scope = "PR + Issue" if cfg.get("watchIssues", True) else "仅 PR"
    title = "PR Watcher 测试通知"
    body = f"通知通道正常 · 监控: {repos} · {when}"
    html = (f"<h3>通知通道正常</h3><p>PR Watcher v3 已就绪</p>"
            f"<ul><li>监控仓库: {html_mod.escape(repos)}({repo_summary(cfg)})</li>"
            f"<li>{when}</li>"
            f"<li>范围: {scope}</li>"
            f"<li>汇报: {quiet}</li></ul>")
    dispatch(cfg, title, body, html)
    log("测试通知已发送(Windows 通知 + 邮件 + 可选 Server酱)")


def repo_summary(cfg: dict) -> str:
    """仓库个数直接来自 config.json 的 repos 数组;有禁用项时把启用数也写上。"""
    total = len(cfg["repos"])
    enabled = sum(1 for r in cfg["repos"] if r.get("enabled", True) is not False)
    return f"{total} 个仓库" + (f"(启用 {enabled})" if enabled != total else "")


def parse_times(cfg: dict) -> list:
    """配置里的 dailyTimes,例如 ["10:00","18:00","22:00"] → [(10,0),(18,0),(22,0)]。
    为空/没写 = 退回 pollMinutes 周期模式。"""
    raw = cfg.get("dailyTimes")
    out = []
    if isinstance(raw, list):
        for x in raw:
            try:
                hh, mm = str(x).strip().split(":")
                h, m = int(hh), int(mm)
            except Exception:
                continue
            if 0 <= h <= 23 and 0 <= m <= 59 and (h, m) not in out:
                out.append((h, m))
    return sorted(out)


def fmt_times(times: list) -> str:
    return " / ".join(f"{h:02d}:{m:02d}" for h, m in times)


def next_run_at(times: list, now: datetime) -> datetime:
    """今天还没到的下一个时刻;都过完了就取明天的第一个。"""
    for h, m in times:
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t > now:
            return t
    h, m = times[0]
    return now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=1)


def wait_until(target: datetime) -> bool:
    """睡到 target。返回 False 表示期间收到了停止标记(该退出了)。
    按 60 秒一段睡,所以停止响应最多一分钟;机器休眠唤醒后会立刻补跑一次。"""
    while True:
        if STOP_PATH.exists():
            log("收到停止标记,正在退出")
            return False
        now = datetime.now()
        if now >= target:
            return True
        time.sleep(min(60, max(1, (target - now).total_seconds())))


def wait_seconds(total: int) -> bool:
    waited = 0
    while waited < total:
        if STOP_PATH.exists():
            log("收到停止标记,正在退出")
            return False
        time.sleep(min(60, total - waited))
        waited += 60
    return True


def main():
    ap = argparse.ArgumentParser(description="GitHub PR / Issue 提醒器(只提醒,不分析)")
    ap.add_argument("--once", action="store_true", help="检查所有仓库一轮后退出")
    ap.add_argument("--dry-run", action="store_true", help="只检查并打印汇报内容,不发任何通知")
    ap.add_argument("--selftest", action="store_true", help="离线自检")
    ap.add_argument("--test-notify", action="store_true", help="发送测试通知")
    ap.add_argument("--repo", default="", help="只处理指定仓库(owner/repo)")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    try:
        cfg = load_config()
    except Exception as e:
        log(f"[配置错误] {e}")
        try:
            print(f"\n提示: 可直接编辑 {CONFIG_PATH}\n     再运行 python pr_watcher.py --selftest 验证")
        except Exception:
            pass
        sys.exit(1)

    if args.test_notify:
        test_notify(cfg)
        return
    if args.once or args.dry_run:
        check_all(cfg, args.repo, dry=args.dry_run)
        log("单轮检查结束(--%s)" % ("dry-run" if args.dry_run else "once"))
        return

    if not acquire_single_instance():
        log("已在运行(重复启动被忽略)")
        return
    try:
        STOP_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    times = parse_times(cfg)
    if times:
        log(f"PR Watcher 启动: {repo_summary(cfg)} · 每天 {fmt_times(times)} 检查"
            f"{' · 含 issue' if cfg.get('watchIssues', True) else ' · 仅 PR'}")
    else:
        log(f"PR Watcher 启动: {len(cfg['repos'])} 个仓库 · 每 {cfg['pollMinutes']} 分钟"
            f"{' · 含 issue' if cfg.get('watchIssues', True) else ' · 仅 PR'}")
    first = True
    try:
        while True:
            try:
                cfg = load_config()          # 每轮重新读配置:改完存盘即生效,不用重启
            except Exception as e:
                log(f"[配置错误] {e}(本轮沿用上一次的配置)")
            times = parse_times(cfg)

            if times:
                # 固定时刻模式:等到下一个时刻再检查(启动时不立刻查,保证通知只落在这些点)
                target = next_run_at(times, datetime.now())
                log(f"下次检查: {target.strftime('%m-%d %H:%M')}")
                if not wait_until(target):
                    return
            elif not first:
                # 周期模式:每 pollMinutes 分钟一轮
                if not wait_seconds(max(60, int(cfg["pollMinutes"]) * 60)):
                    return
            first = False

            try:
                check_all(cfg, args.repo)
            except Exception as e:
                log(f"循环异常: {e}")
    finally:
        release_single_instance()


if __name__ == "__main__":
    main()
