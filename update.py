# -*- coding: utf-8 -*-
"""科技前沿日报 —— 抓取各来源的 RSS，梳理（分类 / 去重聚合 / 排序）后生成页面数据。

只依赖 Python 标准库。常用命令：

    python update.py                  立即更新一次（生成 data/news.js，供 index.html 读取）
    python update.py --open           更新后用默认浏览器打开页面
    python update.py --schedule 08:00 注册 Windows 计划任务，每天定时自动更新
    python update.py --unschedule     移除计划任务
    python update.py --rebuild        不联网，用本地已有数据按当前 config.py 重新生成页面
    python update.py --debug          额外输出 logs/debug_report.txt（分类、聚合明细，调关键词时用）

来源、领域、关键词都在 config.py 里。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import html
import html.entities
import json
import logging
import logging.handlers
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
LOG_DIR = BASE / "logs"
STORE_PATH = DATA_DIR / "store.json"
BUNDLE_PATH = DATA_DIR / "news.js"
LOCK_PATH = DATA_DIR / ".update.lock"
PAGE_PATH = BASE / "index.html"
TASK_NAME = "TechFrontierDaily"

UTC = timezone.utc
CST = timezone(timedelta(hours=8))

FILTER_MIN_SCORE = 4      # 综合来源：关键词得分达到该值才收录
SWITCH_MARGIN = 3         # 专业来源：其它领域得分至少高出默认领域这么多才改判
CLUSTER_THRESHOLD = {"zh": 0.30, "en": 0.45}   # 标题相似度超过该值视为同一事件（按实测数据标定）
CLUSTER_MAX_HOURS = 60    # 同一事件的报道时间跨度上限

log = logging.getLogger("tech_frontier")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": ("application/rss+xml, application/atom+xml, application/xml;q=0.9, "
               "text/xml;q=0.8, */*;q=0.5"),
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


# ==========================================================================
# 关键词编译
# ==========================================================================
def _kw_pattern(kw: str) -> str:
    if kw.startswith("re:"):
        return kw[3:]
    esc = re.escape(kw)
    if any(ord(ch) > 127 for ch in kw):
        return esc                      # 含中文：直接按包含匹配
    body = f"(?-i:{esc})" if (kw.isupper() and len(kw) <= 6) else esc
    return rf"(?<![A-Za-z0-9]){body}(?:s|es|'s)?(?![A-Za-z0-9])"


def _compile(words) -> re.Pattern:
    parts = sorted({_kw_pattern(w) for w in words}, key=len, reverse=True)
    return re.compile("|".join(f"(?:{p})" for p in parts), re.I)


def _check_config(cfg) -> None:
    cats = [c for c, _ in cfg.CATEGORIES]
    problems = []
    ids = [s["id"] for s in cfg.SOURCES]
    problems += [f"来源 id 重复: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for s in cfg.SOURCES:
        if s.get("mode") == "all" and s.get("default") not in cats:
            problems.append(f"来源 {s['id']} 的 mode 是 all，但 default={s.get('default')!r} 不是已定义的领域")
    problems += [f"KEYWORDS 里的 {k!r} 不是已定义的领域" for k in cfg.KEYWORDS if k not in cats]
    if sorted(cfg.TIE_BREAK) != sorted(cats):
        problems.append("TIE_BREAK 必须恰好包含 CATEGORIES 里的全部领域")
    if problems:
        raise ValueError("；".join(problems))


def _startup_failure() -> None:
    """config.py 写错（语法、正则、领域名）时，定时任务没有控制台可看：把原因写进日志再退出。"""
    import traceback
    detail = traceback.format_exc()
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "update.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} ERROR config.py 加载失败，请检查最近的修改\n{detail}\n")
    except OSError:
        pass
    if sys.stderr is not None:
        sys.stderr.write("config.py 加载失败，请检查最近的修改：\n" + detail)
    raise SystemExit(1)


try:
    import config as C
    _check_config(C)
    SOURCE_BY_ID = {s["id"]: s for s in C.SOURCES}
    KW_RX = {cat: (_compile(spec["strong"]), _compile(spec["weak"])) for cat, spec in C.KEYWORDS.items()}
    EXCLUDE_RX = _compile(C.EXCLUDE_TITLE)
    EXCLUDE_CATEGORY_RX = re.compile("|".join(re.escape(c) for c in C.EXCLUDE_CATEGORY) or r"(?!)", re.I)
    BOOST_RX = _compile(C.BOOST)
    SUMMARY_STRIP_RX = [re.compile(p, re.I | re.S) for p in C.SUMMARY_STRIP]
except Exception:  # noqa: BLE001 - 任何配置错误都要留下可查的记录
    _startup_failure()


def _hits(rx: re.Pattern, text: str) -> set:
    out = set()
    for m in rx.finditer(text):
        word = m.group(0).lower()
        if len(word) > 3 and word.endswith("s") and word.isascii():
            word = word[:-1]
        out.add(word)
    return out


def keyword_scores(title: str, summary: str) -> dict:
    """返回 {领域: (得分, 是否够格, 标题是否命中强词)}。标题强词 4 分、弱词 2 分；摘要强词 2 分、弱词 1 分。

    “够格”= 得分达标 + 标题里至少命中一个词 + 标题或摘要里至少有一个强词，
    避免仅凭摘要里顺带一提、或几个泛泛的弱词就被归进某个领域。
    """
    scores = {}
    for cat, (strong, weak) in KW_RX.items():
        ts = _hits(strong, title)
        tw = _hits(weak, strong.sub(" ", title))
        ss = _hits(strong, summary) if summary else set()
        sw = _hits(weak, strong.sub(" ", summary)) if summary else set()
        score = 4 * min(len(ts), 3) + 2 * min(len(tw), 2) + 2 * min(len(ss), 3) + min(len(sw), 2)
        if score:
            solid = score >= FILTER_MIN_SCORE and bool(ts or tw) and bool(ts or ss)
            scores[cat] = (score, solid, bool(ts))
    return scores


def classify(title: str, summary: str, src: dict):
    """返回 (领域, 关键词得分)；不收录时领域为 None。"""
    if EXCLUDE_RX.search(title):
        return None, 0
    scores = keyword_scores(title, summary)
    best, best_score = None, 0
    for cat in C.TIE_BREAK:                      # 只在“够格”的领域里挑得分最高的
        score, solid, _ = scores.get(cat, (0, False, False))
        if solid and score > best_score:
            best, best_score = cat, score
    if src.get("mode") == "all":
        default = src.get("default")
        default_score, _, default_in_title = scores.get(default, (0, False, False))
        if default is None:
            return best, best_score
        # 专业来源：标题已点明本行，或别的领域优势不明显，就留在默认领域
        if best and best != default and not default_in_title and best_score >= default_score + SWITCH_MARGIN:
            return best, best_score
        return default, default_score
    if best is None:                             # 不收录；返回最高原始分，便于调试时看“差多少”
        return None, max((s[0] for s in scores.values()), default=0)
    return best, best_score


# ==========================================================================
# 抓取与解析
# ==========================================================================
def http_get(url: str) -> tuple[bytes, str | None]:
    req = urllib.request.Request(url, headers=HEADERS)
    deadline = time.monotonic() + C.FETCH_DEADLINE
    with urllib.request.urlopen(req, timeout=C.FETCH_TIMEOUT) as resp:
        chunks, size = [], 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > C.MAX_FEED_BYTES:
                raise ValueError("响应过大")
            if time.monotonic() > deadline:
                raise TimeoutError("下载超时")
        raw = b"".join(chunks)
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            raw = gzip.decompress(raw)
        elif "deflate" in enc:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        return raw, resp.headers.get_content_charset()


_XML_DECL_RX = re.compile(rb'^\s*<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']', re.I)
_INVALID_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
_NAMED_ENTITY_RX = re.compile(r"&([A-Za-z][A-Za-z0-9]{1,31});")


def decode_feed(raw: bytes, http_charset: str | None) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    m = _XML_DECL_RX.match(raw[:300])
    enc = (m.group(1).decode("ascii") if m else None) or http_charset or "utf-8"
    try:
        text = raw.decode(enc)
    except (LookupError, UnicodeDecodeError):
        text = raw.decode("utf-8", "replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)   # 已解码为 str，去掉编码声明
    text = _INVALID_XML_CHARS.sub("", text)

    def fix_entity(mm):
        name = mm.group(1)
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return mm.group(0)
        cp = html.entities.name2codepoint.get(name)
        return f"&#{cp};" if cp else mm.group(0)

    return _NAMED_ENTITY_RX.sub(fix_entity, text)


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _entry_from_element(el) -> dict:
    out = {"title": "", "links": [], "summary": "", "description": "", "content": "", "date": "",
           "updated": "", "cats": []}
    alt_links = []
    for ch in el:
        tag = _local(ch.tag)
        text = ("".join(ch.itertext()) if len(ch) else (ch.text or "")).strip()
        if tag == "title":
            out["title"] = out["title"] or text
        elif tag == "category":
            out["cats"].append(text or ch.attrib.get("term", ""))
        elif tag == "link":
            href = ch.attrib.get("href")
            if href:
                (out["links"] if ch.attrib.get("rel", "alternate") == "alternate" else alt_links).append(href)
            elif text:
                out["links"].append(text)
        elif tag in ("guid", "id"):
            if text.startswith(("http://", "https://")):
                alt_links.append(text)
        elif tag == "summary":
            out["summary"] = out["summary"] or text
        elif tag == "description":
            out["description"] = out["description"] or text
        elif tag in ("encoded", "content"):
            out["content"] = out["content"] or text
        elif tag in ("pubdate", "published", "date", "issued", "created"):
            out["date"] = out["date"] or text
        elif tag in ("updated", "modified"):
            out["updated"] = out["updated"] or text
    out["links"].extend(alt_links)
    return out


_ITEM_RX = re.compile(r"<(item|entry)\b[^>]*>(.*?)</\1\s*>", re.S | re.I)


def _lenient_entries(text: str) -> list:
    """XML 不规范时的兜底：用正则把条目抠出来。"""
    def field(block, *names):
        for name in names:
            m = re.search(rf"<(?:\w+:)?{name}\b[^>]*>(.*?)</(?:\w+:)?{name}\s*>", block, re.S | re.I)
            if m:
                val = m.group(1).strip()
                cd = re.match(r"<!\[CDATA\[(.*?)\]\]>$", val, re.S)
                return cd.group(1).strip() if cd else html.unescape(val)
        return ""

    entries = []
    for m in _ITEM_RX.finditer(text):
        block = m.group(2)
        links = []
        link = field(block, "link")
        if link:
            links.append(link)
        links.extend(re.findall(r'<link\b[^>]*href=["\']([^"\']+)["\']', block, re.I))
        guid = field(block, "guid", "id")
        if guid.startswith(("http://", "https://")):
            links.append(guid)
        cats = [re.sub(r"^<!\[CDATA\[|\]\]>$", "", c.strip())
                for c in re.findall(r"<category\b[^>]*>(.*?)</category\s*>", block, re.S | re.I)]
        entries.append({
            "title": field(block, "title"), "links": links,
            "summary": field(block, "summary"), "description": field(block, "description"),
            "content": field(block, "encoded", "content"),
            "date": field(block, "pubDate", "published", "date"), "updated": field(block, "updated"),
            "cats": cats,
        })
    return entries


def parse_feed(text: str) -> list:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return _lenient_entries(text)
    return [_entry_from_element(el) for el in root.iter() if _local(el.tag) in ("item", "entry")]


def fetch_source(src: dict) -> list:
    raw, charset = http_get(src["url"])
    entries = parse_feed(decode_feed(raw, charset))
    if not entries:
        raise ValueError("没有解析到条目（可能不是 RSS 或被拦截）")
    return entries


def fetch_many(sources: list) -> dict:
    """并发抓取，返回 {来源 id: (条目列表 | None, 错误信息 | None)}。"""
    results = {}
    with cf.ThreadPoolExecutor(max_workers=C.FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_source, s): s for s in sources}
        for fut in cf.as_completed(futures):
            src = futures[fut]
            try:
                results[src["id"]] = (fut.result(), None)
            except Exception as exc:  # noqa: BLE001 - 单个来源失败不能影响其它来源
                msg = f"{type(exc).__name__}: {exc}"
                results[src["id"]] = (None, re.sub(r"\s+", " ", msg)[:160])
    return results


# ==========================================================================
# 文本 / 链接 / 日期规范化
# ==========================================================================
_TAG_RX = re.compile(r"<[^>]*>")
_ENTITY_HINT_RX = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]{2,10});")


def strip_html(s: str, limit: int = 6000) -> str:
    if not s:
        return ""
    s = s[:limit]
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", " ", s)
    s = _TAG_RX.sub("", s)
    s = re.sub(r"<[^>]*$", "", s)            # 截断留下的半个标签
    s = html.unescape(s)
    if _ENTITY_HINT_RX.search(s):            # 二次转义的内容
        s = html.unescape(s)
    if "<" in s:
        s = _TAG_RX.sub("", s)
        s = re.sub(r"<[^>]*$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def display_width(ch: str) -> int:
    return 2 if ord(ch) > 0x2E7F else 1


def truncate_width(s: str, limit: int) -> str:
    width = 0
    for i, ch in enumerate(s):
        width += display_width(ch)
        if width > limit:
            return s[:i].rstrip(" ，,、;；:：") + "…"
    return s


def clean_title(raw: str) -> str:
    return strip_html(raw, 1000)[:220].strip()


def clean_summary(entry: dict, title: str) -> str:
    for key in ("summary", "description", "content"):
        s = strip_html(entry.get(key) or "")
        for rx in SUMMARY_STRIP_RX:
            s = rx.sub("", s)
        s = s.strip(" \u3000-—|·:：")
        if len(s) < 12:
            continue
        if s == title or s.startswith(title) and len(s) < len(title) + 12:
            continue
        return truncate_width(s, C.SUMMARY_WIDTH)
    return ""


_RSS_TRACKERS = {("f", "rss"), ("from", "rss"), ("source", "rss"), ("ref", "rss")}


def normalize_url(url: str):
    """返回 (可点击的链接, 去重用的键)；不是 http(s) 链接时返回 (None, None)。"""
    try:
        p = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None, None
    if p.scheme not in ("http", "https") or not p.netloc:
        return None, None
    pairs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs
            if not k.lower().startswith("utm_") and (k.lower(), v.lower()) not in _RSS_TRACKERS]
    query = p.query if len(kept) == len(pairs) else urllib.parse.urlencode(kept)
    href = urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, query, ""))
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    key = host + p.path.rstrip("/") + ("?" + query if query else "")
    return href, key


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_TZ_ABBR = {"z": 0, "ut": 0, "utc": 0, "gmt": 0, "est": -5, "edt": -4, "cdt": -5, "mst": -7, "mdt": -6,
            "pst": -8, "pdt": -7, "bst": 1, "cet": 1, "cest": 2, "jst": 9, "kst": 9, "hkt": 8}
_ISO_RX = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s]\s*(\d{1,2}):(\d{2})(?::(\d{2}))?(?:[.,]\d+)?)?"
                     r"\s*(Z|[+-]\d{2}(?::?\d{2})?|[A-Za-z]{2,5})?")
_RFC_RX = re.compile(r"(\d{1,2})\s+([A-Za-z]{3})[A-Za-z]*\.?,?\s+(\d{4})"
                     r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*([+-]\d{2}(?::?\d{2})?|[A-Za-z]{1,5})?")
_URL_DATE_RX = re.compile(r"(?<!\d)(20\d{2})[-/]?(0[1-9]|1[0-2])[-/]?(0[1-9]|[12]\d|3[01])(?!\d)")


def _parse_tz(token, lang: str):
    if not token:
        return None
    t = token.strip().lower()
    if t[0] in "+-":
        digits = t[1:].replace(":", "")
        hours, minutes = int(digits[:2]), int(digits[2:4] or 0)
        if hours > 14 or minutes > 59:
            return None
        delta = timedelta(hours=hours, minutes=minutes)
        return timezone(delta if t[0] == "+" else -delta)
    if t == "cst":                       # 中文来源里的 CST 指北京时间
        return CST if lang == "zh" else timezone(timedelta(hours=-6))
    if t in _TZ_ABBR:
        return timezone(timedelta(hours=_TZ_ABBR[t]))
    return None


def parse_date(text: str, lang: str):
    """解析 RSS 里五花八门的日期，返回 (UTC 时间, 是否只有日期)。失败返回 (None, False)。"""
    if not text:
        return None, False
    text = text.strip()
    default_tz = CST if lang == "zh" else UTC
    try:
        m = _ISO_RX.match(text)
        if m:
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
            if m[4] is None:
                return datetime(y, mo, d, 12, 0, tzinfo=default_tz).astimezone(UTC), True
            tz = _parse_tz(m[7], lang) or default_tz
            return datetime(y, mo, d, int(m[4]), int(m[5]), int(m[6] or 0), tzinfo=tz).astimezone(UTC), False
        m = _RFC_RX.search(text)
        if m and m[2].lower() in _MONTHS:
            y, mo, d = int(m[3]), _MONTHS[m[2].lower()], int(m[1])
            if m[4] is None:
                return datetime(y, mo, d, 12, 0, tzinfo=default_tz).astimezone(UTC), True
            tz = _parse_tz(m[7], lang) or default_tz
            return datetime(y, mo, d, int(m[4]), int(m[5]), int(m[6] or 0), tzinfo=tz).astimezone(UTC), False
    except (ValueError, OverflowError):
        pass
    return None, False


def date_from_url(url: str, lang: str):
    m = _URL_DATE_RX.search(urllib.parse.urlsplit(url).path)
    if not m:
        return None
    try:
        tz = CST if lang == "zh" else UTC
        return datetime(int(m[1]), int(m[2]), int(m[3]), 12, 0, tzinfo=tz).astimezone(UTC)
    except ValueError:
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def normalize_entry(src: dict, entry: dict, now: datetime):
    """把一条 RSS 条目整理成统一结构；不合格（无标题/无链接/过旧等）返回 None。"""
    title = clean_title(entry.get("title") or "")
    if len(title) < 4:
        return None
    href = key = None
    for link in entry.get("links") or []:
        href, key = normalize_url(link)
        if href:
            break
    if not href:
        return None
    if src.get("only_url") and not re.search(src["only_url"], href):
        return None
    if src.get("skip_url") and re.search(src["skip_url"], href):
        return None
    if any(c.strip() and EXCLUDE_CATEGORY_RX.fullmatch(c.strip()) for c in entry.get("cats") or []):
        return None                      # feed 自己标注的新闻稿 / 赞助内容 / 播客等

    lang = src["lang"]
    pub, date_only = parse_date(entry.get("date") or "", lang)
    if pub is None:
        pub, date_only = parse_date(entry.get("updated") or "", lang)
    if pub is None:
        pub, date_only = date_from_url(href, lang), True
    approx = False
    if pub is None:
        pub, approx = now, True
    elif pub > now + timedelta(minutes=10) or (date_only and pub > now):
        pub = now                        # 未来时间（时区写错或只有日期）一律按抓取时刻算
    if pub < now - timedelta(days=C.RETAIN_DAYS):
        return None

    summary = "" if src.get("no_summary") else clean_summary(entry, title)
    item = {
        "id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:12],
        "src": src["id"], "title": title, "url": href, "summary": summary, "pub": iso(pub),
    }
    if approx:
        item["approx"] = True
    return item


# ==========================================================================
# 本地数据（store.json）：跨天累积，页面才能展示“近 7 天”
# ==========================================================================
def load_store() -> dict:
    if STORE_PATH.exists():
        try:
            store = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(store.get("items"), dict):
                store.setdefault("sources", {})
                store.setdefault("runs", [])
                return store
        except (OSError, ValueError):
            backup = STORE_PATH.with_suffix(".broken.json")
            log.warning("store.json 损坏，已另存为 %s 并重新开始累积", backup.name)
            try:
                os.replace(STORE_PATH, backup)
            except OSError:
                pass
    return {"version": 1, "items": {}, "sources": {}, "runs": []}


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def title_key(src_id: str, title: str) -> str:
    return src_id + "|" + re.sub(r"[\W_]+", "", title.lower())


def merge_results(store: dict, results: dict, now: datetime, debug: dict | None) -> int:
    items = store["items"]
    seen_titles = {title_key(it["src"], it["title"]) for it in items.values()}
    added = 0
    for src in C.SOURCES:
        entries, _err = results.get(src["id"], (None, None))
        if entries is None:
            continue
        kept = 0
        for entry in entries:
            item = normalize_entry(src, entry, now)
            if item is None:
                continue
            cat, kw = classify(item["title"], item["summary"], src)
            if cat is None:
                if debug is not None:
                    debug["dropped"][src["id"]].append((kw, item["title"]))
                continue
            kept += 1
            old = items.get(item["id"])
            if old is not None:
                old["title"], old["summary"] = item["title"], item["summary"] or old.get("summary", "")
                if not old.get("approx") and item["pub"] < old["pub"]:
                    old["pub"] = item["pub"]
                continue
            tkey = title_key(item["src"], item["title"])
            if tkey in seen_titles:
                continue
            seen_titles.add(tkey)
            item["seen"] = iso(now)
            items[item["id"]] = item
            added += 1
        if debug is not None:
            debug["counts"][src["id"]] = (len(entries), kept)
    return added


def prune_store(store: dict, now: datetime) -> None:
    cutoff = iso(now - timedelta(days=C.RETAIN_DAYS))
    items = store["items"]
    for item_id in [i for i, it in items.items() if it["pub"] < cutoff or it["src"] not in SOURCE_BY_ID]:
        del items[item_id]


# ==========================================================================
# 聚合（同一事件的多家报道合并）与重要度
# ==========================================================================
_EN_STOP = set("""a an the and or but of to in on at for from by with without into over under about after before
as is are was were be been being it its this that these those their his her our your they them we you he she
not no new how why what when where who which will would can could may might should has have had do does did
says said say just more most than then also now up out off via vs amid per first one two s t re using use
used get gets make makes made here there all any some such only other between during against while its
introducing available announces announced unveils unveiled reveals revealed releases released update
updated report reportedly""".split())
_ZH_STOP_BIGRAMS = set("""消息 表示 发布 宣布 公司 我们 他们 可以 一个 这个 什么 如何 为何 正式 今日 今天 昨日
已经 进行 推出 实现 或将 称其 最新 首次 成功 全球 中国 美国 来了 背后 可能 没有 不是 还是 以及 因为 所以
亿元 万元 亿美 美元 目前 相关 方面 其中 技术 科技 企业 市场 行业 未来 时代 开始 完成 研究 团队
达成 战略 略合 合作 官宣 回应 曝光 网友 集团""".split())
_WORD_RX = re.compile(r"[a-z0-9]+(?:[.'’\-][a-z0-9]+)*")
_CJK_RX = re.compile(r"[\u4e00-\u9fff]+")


def title_tokens(title: str) -> set:
    t = title.lower()
    tokens = set()
    for w in _WORD_RX.findall(t):
        w = w.replace("’", "'")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) < 2 or w in _EN_STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        tokens.add(w)
    for run in _CJK_RX.findall(t):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in _ZH_STOP_BIGRAMS:
                tokens.add(bg)
    return tokens


def cluster_items(recs: list) -> list:
    """recs: [{'tok': set, 'lang', 'weight', 'pub_dt', ...}]，返回 [[代表条目, 其它成员...], ...]。"""
    clusters = []
    by_lang = defaultdict(list)
    for r in recs:
        by_lang[r["lang"]].append(r)
    max_gap = timedelta(hours=CLUSTER_MAX_HOURS)
    for lang, group in by_lang.items():
        threshold = CLUSTER_THRESHOLD.get(lang, 0.45)
        df = Counter()
        for r in group:
            df.update(r["tok"])
        n = len(group)
        idf = {t: math.log(1 + n / c) for t, c in df.items()}
        for r in group:
            r["norm"] = math.sqrt(sum(idf[t] ** 2 for t in r["tok"])) or 1.0
        # 权重高的来源先当“种子”，同权重下早发的优先
        group.sort(key=lambda r: (-r["weight"], r["pub_dt"]))
        local, index = [], defaultdict(list)
        for r in group:
            dots = Counter()
            for t in r["tok"]:
                w2 = idf[t] ** 2
                for ci in index.get(t, ()):
                    dots[ci] += w2
            best, best_sim = None, 0.0
            for ci, dot in dots.items():
                seed = local[ci][0]
                if abs(seed["pub_dt"] - r["pub_dt"]) > max_gap:
                    continue
                sim = dot / (seed["norm"] * r["norm"])
                if sim > best_sim:
                    best, best_sim = ci, sim
            if best is not None and best_sim >= threshold:
                r["sim"] = round(best_sim, 2)
                local[best].append(r)
            else:
                local.append([r])
                for t in r["tok"]:
                    index[t].append(len(local) - 1)
        clusters.extend(local)
    return clusters


def score_cluster(cluster: list) -> float:
    """重要度 = 来源权重 + 多家独立报道加分 + “首次/突破/发布”等用词加分 + 切题程度。"""
    lead = cluster[0]
    credit = {}
    for r in cluster[1:]:
        if r["src"] == lead["src"]:
            continue
        # 标题几乎一字不差的多半是转载，不算独立报道，只给 0.4 家的分量
        credit[r["src"]] = max(credit.get(r["src"], 0.0), 0.4 if r.get("sim", 0) >= 0.9 else 1.0)
    boost = len(_hits(BOOST_RX, lead["title"]))
    return round(max(r["weight"] for r in cluster)
                 + 0.9 * min(sum(credit.values()), 4)
                 + 0.3 * min(boost, 2)
                 + 0.025 * min(lead["kw"], 12), 2)


# ==========================================================================
# 生成页面数据 data/news.js
# ==========================================================================
def build_bundle(store: dict, now: datetime, debug: dict | None) -> dict:
    cutoff = now - timedelta(days=C.WINDOW_DAYS)
    recs = []
    for it in list(store["items"].values()):
        src = SOURCE_BY_ID.get(it["src"])
        cat, kw = classify(it["title"], it.get("summary", ""), src) if src else (None, 0)
        if cat is None:                 # 来源已从配置里删掉，或配置改了以后不再符合条件
            del store["items"][it["id"]]
            continue
        it["cat"] = cat
        pub_dt = from_iso(it["pub"])
        if pub_dt < cutoff:
            continue
        recs.append({"id": it["id"], "src": it["src"], "lang": src["lang"], "weight": src["weight"],
                     "title": it["title"], "url": it["url"], "summary": it.get("summary", ""),
                     "cat": cat, "kw": kw, "pub": it["pub"], "pub_dt": pub_dt,
                     "tok": title_tokens(it["title"])})

    clusters = cluster_items(recs)
    scored = sorted(((score_cluster(c), c) for c in clusters), key=lambda x: -x[0])

    local_tz = now.astimezone().tzinfo
    per_day_cat, per_day_src = Counter(), Counter()
    out_items = []
    for score, cluster in scored:
        lead = cluster[0]
        day = lead["pub_dt"].astimezone(local_tz).strftime("%Y-%m-%d")
        if per_day_cat[(day, lead["cat"])] >= C.MAX_PER_DAY_CATEGORY:
            continue
        if len(cluster) == 1 and per_day_src[(day, lead["src"])] >= C.MAX_PER_DAY_SOURCE:
            continue
        per_day_cat[(day, lead["cat"])] += 1
        per_day_src[(day, lead["src"])] += 1
        rec = {"id": lead["id"], "t": lead["title"], "u": lead["url"], "s": lead["src"],
               "c": lead["cat"], "d": lead["pub"], "w": score}
        if lead["summary"]:
            rec["x"] = lead["summary"]
        others, seen_src = [], {lead["src"]}
        for r in sorted(cluster[1:], key=lambda r: (-r["weight"], r["pub_dt"])):
            if r["src"] in seen_src:
                continue
            seen_src.add(r["src"])
            others.append({"t": r["title"], "u": r["url"], "s": r["src"]})
        if others:
            rec["n"] = len(others) + 1
            rec["m"] = others[:6]
        out_items.append(rec)
    out_items.sort(key=lambda r: r["d"], reverse=True)

    if debug is not None:
        debug["clusters"] = [(s, c) for s, c in scored if len(c) > 1]
        debug["top"] = scored[:40]

    sources = {}
    for src in C.SOURCES:
        status = store["sources"].get(src["id"], {})
        sources[src["id"]] = {"name": src["name"], "home": src["home"], "lang": src["lang"],
                              "ok": not status.get("error"), "lastOk": status.get("last_ok")}
    return {
        "generatedAt": iso(now),
        "windowDays": C.WINDOW_DAYS,
        "categories": [{"id": c, "name": n} for c, n in C.CATEGORIES],
        "sources": sources,
        "items": out_items,
    }


def write_bundle(bundle: dict) -> None:
    payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    atomic_write(BUNDLE_PATH, "window.TF_DATA = " + payload + ";\n")


def write_debug_report(debug: dict, results: dict) -> None:
    lines = ["# 来源抓取情况（解析条数 / 收录条数）"]
    for src in C.SOURCES:
        entries, err = results.get(src["id"], (None, "未抓取"))
        fetched, kept = debug["counts"].get(src["id"], (0, 0))
        lines.append(f"{src['id']:<16} {'OK ' if entries is not None else 'ERR'} {fetched:>4} / {kept:<4} {err or ''}")
    lines.append("\n# 重要度最高的 40 条")
    for score, c in debug.get("top", []):
        lines.append(f"{score:>5}  [{c[0]['cat']:<7}] ({len({r['src'] for r in c})}家) {c[0]['src']}: {c[0]['title']}")
    lines.append("\n# 多家报道聚合（请检查有没有把不同事件误并到一起）")
    for score, c in debug.get("clusters", []):
        lines.append(f"{score:>5}  [{c[0]['cat']}] {c[0]['src']}: {c[0]['title']}")
        for r in c[1:]:
            lines.append(f"         ~{r.get('sim')} {r['src']}: {r['title']}")
    lines.append("\n# 综合来源中被过滤掉的标题（括号内是关键词得分，接近 4 的可考虑补关键词）")
    for src_id, rows in debug["dropped"].items():
        lines.append(f"## {src_id}  共 {len(rows)} 条")
        for kw, title in sorted(rows, key=lambda x: -x[0])[:40]:
            lines.append(f"   ({kw}) {title}")
    atomic_write(LOG_DIR / "debug_report.txt", "\n".join(lines) + "\n")


# ==========================================================================
# 主流程
# ==========================================================================
class AlreadyRunning(Exception):
    pass


class RunLock:
    def __enter__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    if time.time() - LOCK_PATH.stat().st_mtime < 900:
                        raise AlreadyRunning() from None
                    LOCK_PATH.unlink()   # 超过 15 分钟的锁视为上次异常退出留下的
                except FileNotFoundError:
                    pass
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self
        raise AlreadyRunning()

    def __exit__(self, *exc):
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


def run_rebuild(debug_on: bool) -> int:
    """不联网：用本地已有数据按当前 config.py 重新分类、聚合并生成页面数据。"""
    store = load_store()
    last_ok = next((r["time"] for r in reversed(store["runs"]) if r.get("ok")), None)
    if not store["items"] or not last_ok:
        log.error("本地还没有数据，请先正常运行一次 python update.py")
        return 2
    debug = {"dropped": defaultdict(list), "counts": {}} if debug_on else None
    bundle = build_bundle(store, from_iso(last_ok), debug)   # 更新时间仍按上次联网抓取的时刻
    atomic_write(STORE_PATH, json.dumps(store, ensure_ascii=False, indent=1))
    write_bundle(bundle)
    if debug is not None:
        write_debug_report(debug, {})
    log.info("已按当前配置重新生成页面数据（未联网）：库内 %d 条，页面展示 %d 条",
             len(store["items"]), len(bundle["items"]))
    return 0


def run_update(scheduled: bool, debug_on: bool) -> int:
    started = time.monotonic()
    store = load_store()
    results = fetch_many(C.SOURCES)

    def failed():
        return [s for s in C.SOURCES if results[s["id"]][0] is None]

    if failed():                                  # 失败的来源马上再试一次
        time.sleep(2)
        results.update(fetch_many(failed()))
    rounds = 0
    while scheduled and rounds < 2 and len(failed()) > 0.75 * len(C.SOURCES):
        rounds += 1                               # 定时任务碰上刚开机没网：等一等再试
        log.info("大部分来源抓取失败，可能网络尚未就绪，120 秒后重试（第 %d 次）", rounds)
        time.sleep(120)
        results.update(fetch_many(failed()))

    now = datetime.now(UTC).replace(microsecond=0)
    ok_ids = [s["id"] for s in C.SOURCES if results[s["id"]][0] is not None]
    for src in C.SOURCES:
        status = store["sources"].setdefault(src["id"], {})
        entries, err = results[src["id"]]
        if entries is None:
            status["error"] = err
            status["fail_streak"] = status.get("fail_streak", 0) + 1
            log.warning("来源失败 %-16s %s", src["id"], err)
        else:
            status.update(error=None, fail_streak=0, last_ok=iso(now), last_count=len(entries))
    for stale in [k for k in store["sources"] if k not in SOURCE_BY_ID]:
        del store["sources"][stale]

    if not ok_ids:
        store["runs"] = (store["runs"] + [{"time": iso(now), "ok": 0, "failed": len(C.SOURCES)}])[-30:]
        atomic_write(STORE_PATH, json.dumps(store, ensure_ascii=False, indent=1))
        log.error("所有来源都抓取失败（网络不通？），页面数据保持不变")
        return 2

    debug = {"dropped": defaultdict(list), "counts": {}} if debug_on else None
    added = merge_results(store, results, now, debug)
    prune_store(store, now)
    bundle = build_bundle(store, now, debug)
    store["runs"] = (store["runs"] + [{"time": iso(now), "ok": len(ok_ids),
                                       "failed": len(C.SOURCES) - len(ok_ids), "added": added}])[-30:]
    atomic_write(STORE_PATH, json.dumps(store, ensure_ascii=False, indent=1))
    write_bundle(bundle)
    if debug is not None:
        write_debug_report(debug, results)
    log.info("更新完成：来源 %d/%d 成功，新增 %d 条，库内 %d 条，页面展示 %d 条，用时 %.1f 秒",
             len(ok_ids), len(C.SOURCES), added, len(store["items"]), len(bundle["items"]),
             time.monotonic() - started)
    return 0


# ==========================================================================
# Windows 计划任务
# ==========================================================================
def _powershell(script: str) -> subprocess.CompletedProcess:
    script = ("$ErrorActionPreference = 'Stop'\n"
              "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n" + script)
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _ps_quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def schedule_task(at: str) -> int:
    if os.name != "nt":
        print("计划任务仅支持 Windows；其它系统请用 cron 定时执行 update.py。")
        return 1
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", at):
        print("时间格式应为 HH:MM，例如 08:00")
        return 1
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")      # pythonw 不弹黑色命令行窗口
    runner = pythonw if pythonw.exists() else exe
    script = "\n".join([
        f"$action = New-ScheduledTaskAction -Execute {_ps_quote(runner)} "
        f"-Argument {_ps_quote(chr(34) + str(BASE / 'update.py') + chr(34) + ' --scheduled')} "
        f"-WorkingDirectory {_ps_quote(BASE)}",
        f"$trigger = New-ScheduledTaskTrigger -Daily -At {_ps_quote(at)}",
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew "
        "-ExecutionTimeLimit (New-TimeSpan -Minutes 20)",
        f"Register-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Action $action -Trigger $trigger "
        "-Settings $settings -Description 'Daily refresh of the Tech Frontier Daily page (update.py)' "
        "-Force | Out-Null",
        f"(Get-ScheduledTaskInfo -TaskName {_ps_quote(TASK_NAME)}).NextRunTime.ToString('yyyy-MM-dd HH:mm')",
    ])
    res = _powershell(script)
    if res.returncode != 0:
        print("注册计划任务失败：\n" + (res.stderr or res.stdout).strip())
        return 1
    print(f"已注册计划任务“{TASK_NAME}”：每天 {at} 自动更新（错过会在下次开机后补跑）。")
    print(f"下次运行：{res.stdout.strip()}    移除：python update.py --unschedule")
    return 0


def unschedule_task() -> int:
    res = _powershell(f"Unregister-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Confirm:$false")
    if res.returncode != 0:
        print("移除失败（可能本来就没有注册）：\n" + (res.stderr or res.stdout).strip()[:400])
        return 1
    print(f"已移除计划任务“{TASK_NAME}”。")
    return 0


# ==========================================================================
def setup_logging(quiet: bool) -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "update.log", maxBytes=400_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    if not quiet and sys.stderr is not None:      # pythonw 下没有控制台
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(console)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="科技前沿日报：抓取并生成页面数据")
    ap.add_argument("--open", action="store_true", help="更新后打开页面")
    ap.add_argument("--schedule", metavar="HH:MM", help="注册每日定时更新的 Windows 计划任务")
    ap.add_argument("--unschedule", action="store_true", help="移除计划任务")
    ap.add_argument("--scheduled", action="store_true", help="（供计划任务调用）静默运行，网络未就绪时等待重试")
    ap.add_argument("--rebuild", action="store_true",
                    help="不联网，只用本地已有数据按当前 config.py 重新生成页面（改完关键词后用）")
    ap.add_argument("--debug", action="store_true", help="输出 logs/debug_report.txt")
    args = ap.parse_args(argv)

    if args.schedule:
        return schedule_task(args.schedule)
    if args.unschedule:
        return unschedule_task()

    setup_logging(quiet=args.scheduled)
    try:
        with RunLock():
            if args.rebuild:
                code = run_rebuild(debug_on=args.debug)
            else:
                code = run_update(scheduled=args.scheduled, debug_on=args.debug)
    except AlreadyRunning:
        log.warning("已有一个更新正在进行，本次跳过")
        return 3
    except Exception:  # noqa: BLE001 - 定时任务没有控制台，异常必须落到日志里
        log.exception("更新过程出现未处理的异常")
        return 1
    if args.open and PAGE_PATH.exists():
        webbrowser.open(PAGE_PATH.as_uri())
    return code


if __name__ == "__main__":
    sys.exit(main())
