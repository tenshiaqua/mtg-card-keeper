"""
MTG Top8 数据抓取模块
从 mtgtop8.com 抓取 Standard、Modern、Pauper 赛制的比赛上位卡组数据。

mtgtop8 没有官方 JSON API，本模块通过解析 HTML 页面获取数据。
页面结构（基于实际探索）:
  - 赛制列表页: /format?f={ST|MO|PAU}  →  <tr class="hover_tr"> 含 event 链接与日期
  - 比赛详情页: /event?e={event_id}    →  <a href="?e=..&d=..&f=.."> 卡组链接
  - 卡组详情页: /event?e={id}&d={deck} →  <div class="deck_line"> 卡牌行, <div class="O14"> 分类标题
"""

import re
import time
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Optional

# 赛制代码映射
FORMAT_CODES = {
    "standard": "ST",
    "modern": "MO",
    "pauper": "PAU",
}

# 基本地列表（需要排除）—— 用名称过滤，同时 Scryfall 的 is_basic_land 字段也会二次过滤
BASIC_LANDS = {
    "Plains", "Island", "Swamp", "Mountain", "Forest",
    "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
    "Snow-Covered Swamp", "Snow-Covered Mountain", "Snow-Covered Forest",
}

BASE_URL = "https://www.mtgtop8.com"
REQUEST_DELAY = 1.0  # 对 mtgtop8 的请求间隔（秒），礼貌抓取
_last_request_time = 0.0


def _rate_limit():
    """请求速率限制"""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_time = time.time()


def _http_get(url: str, timeout: int = 30) -> Optional[str]:
    """HTTP GET 请求，返回 HTML 文本"""
    _rate_limit()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MTG-Analysis/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {url}")
        return None
    except Exception as e:
        print(f"  请求失败 {url}: {e}")
        return None


def _html_unescape(s: str) -> str:
    """简单的 HTML 实体反转义"""
    return (s.replace("&amp;", "&")
             .replace("&quot;", '"')
             .replace("&#39;", "'")
             .replace("&nbsp;", " ")
             .replace("&lt;", "<")
             .replace("&gt;", ">"))


# ============================================================
# 解析函数（正则）—— 比 HTMLParser 更稳健地处理 mtgtop8 的不规范 HTML
# ============================================================

# 真实 HTML: 属性无引号, href=event?e=89267&f=ST, 用 & 而非 &amp;
# 比赛列表行: <tr class=hover_tr> ... <a href=event?e=89267&f=ST>名称</a> ... 05/08/26 ... </tr>
_EVENT_ROW_RE = re.compile(r'<tr class=hover_tr>(.*?)</tr>', re.DOTALL)
_EVENT_LINK_RE = re.compile(r'<a href=event\?e=(\d+)[^>]*>([^<]+)</a>')
_DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{2})')


def parse_format_events(html: str, months_back: int = None,
                         start_date: datetime = None, end_date: datetime = None) -> list[dict]:
    """
    解析赛制列表页，返回指定日期范围内的比赛列表。

    三种过滤模式（优先级从高到低）：
      1. start_date + end_date: 精确日期范围
      2. months_back: 最近 N 个月
      3. 默认: 最近 3 个月

    Returns:
        [{"event_id", "event_name", "date"("YYYY-MM-DD"), "is_online"}, ...]
    """
    now = datetime.now()
    if start_date is not None and end_date is not None:
        cutoff = start_date
        upper = end_date
    elif months_back is not None:
        cutoff = now - timedelta(days=months_back * 30 + 5)
        upper = now
    else:
        cutoff = now - timedelta(days=3 * 30 + 5)
        upper = now

    events = []
    seen_ids = set()

    for m in _EVENT_ROW_RE.finditer(html):
        row = m.group(1)
        link = _EVENT_LINK_RE.search(row)
        if not link:
            continue
        event_id = link.group(1)
        event_name = _html_unescape(link.group(2)).strip()
        if event_id in seen_ids:
            continue

        date_match = _DATE_RE.search(row)
        date_str = date_match.group(1) if date_match else ""
        try:
            event_date = datetime.strptime(date_str, "%d/%m/%y")
        except ValueError:
            event_date = now  # 日期缺失时按最近处理

        if event_date < cutoff or event_date > upper:
            continue

        is_online = "mtgo" in row.lower()
        seen_ids.add(event_id)
        events.append({
            "event_id": event_id,
            "event_name": event_name,
            "date": event_date.strftime("%Y-%m-%d"),
            "is_online": is_online,
        })

    return events


# 真实 HTML: <a href=?e=89267&d=877472&f=ST>Jeskai Tablet</a>  (href 无引号; 缩略图链接后紧跟 <img> 被 [^<]+ 排除; 箭头 <a class=arrow href=...> 因 <a 后非 href 被排除)
_DECK_LINK_RE = re.compile(r'<a href=\?e=\d+&d=(\d+)[^>]*>([^<]+)</a>')
# 真实 HTML: <a class=player href=search?player=Aaron+Friedrich>Aaron Friedrich</a>  (class=player 空格 href; class=player_big 不匹配)
_PLAYER_LINK_RE = re.compile(r'<a class=player href=search\?player=([^>]+)>([^<]+)</a>')


def parse_event_decks(html: str) -> list[dict]:
    """
    解析比赛详情页，返回卡组列表（名次为上位卡组）。

    Returns:
        [{"deck_id", "deck_name", "player"}, ...]
    """
    decks = []
    # 卡组名链接与玩家链接按出现顺序一一对应
    deck_matches = _DECK_LINK_RE.findall(html)
    player_matches = _PLAYER_LINK_RE.findall(html)

    # 去重 deck 链接（同一卡组的名称链接可能只出现一次，但保险起见按 deck_id 去重保留顺序）
    seen_deck_ids = set()
    clean_decks = []
    for did, name in deck_matches:
        name = _html_unescape(name).strip()
        if not name:
            continue
        if did in seen_deck_ids:
            continue
        seen_deck_ids.add(did)
        clean_decks.append((did, name))

    for i, (did, name) in enumerate(clean_decks):
        player = ""
        if i < len(player_matches):
            player = _html_unescape(player_matches[i][1]).strip()
        decks.append({"deck_id": did, "deck_name": name, "player": player})

    return decks


# 真实 HTML: 分类标题 <div class=O14>23 LANDS</div> 或 <div class=O14 style="margin-top:5px;">6 CREATURES</div>
# (class 无引号; 可能带 style 属性; O14 也用于价格但那是 span 不是 div)
_SECTION_RE = re.compile(r'<div class=O14[^>]*>([^<]+)</div>')
# 真实 HTML 卡牌行: <div id=mdsos257 class="deck_line hover_tr" onclick="...">4 <span class=L14>卡名</span></div>
# id 无引号, class 有引号(含空格), span class=L14 无引号
_CARD_LINE_RE = re.compile(
    r'<div id=(md|sb)\w+[^>]*?class="deck_line[^"]*"[^>]*>\s*(\d+)\s*<span class=L14>([^<]+)</span>',
    re.DOTALL,
)
# 同时匹配标题和卡牌行，按文档顺序处理
_TOKEN_RE = re.compile(
    r'<div class=O14[^>]*>([^<]+)</div>'
    r'|<div id=(md|sb)\w+[^>]*?class="deck_line[^"]*"[^>]*>\s*(\d+)\s*<span class=L14>([^<]+)</span>',
    re.DOTALL,
)


def parse_deck_cards(html: str) -> dict:
    """
    解析卡组详情页，返回主牌与备牌卡牌列表。

    Returns:
        {"maindeck": [{"qty", "name", "section"}, ...],
         "sideboard": [{"qty", "name"}, ...]}
    """
    maindeck = []
    sideboard = []
    in_sideboard = False
    current_section = "Other"

    for m in _TOKEN_RE.finditer(html):
        section_title = m.group(1)
        side_flag = m.group(2)
        qty = m.group(3)
        card_name = m.group(4)

        if section_title is not None:
            # 分类标题
            title = section_title.strip().upper()
            if "SIDEBOARD" in title:
                in_sideboard = True
                current_section = "SIDEBOARD"
            elif "LAND" in title:
                current_section = "Land"
            elif "CREATURE" in title:
                current_section = "Creature"
            elif "INSTANT" in title or "SORC" in title:
                current_section = "Spell"
            elif "OTHER" in title or "SPELL" in title:
                current_section = "Other"
            continue

        if qty is None:
            continue
        name = _html_unescape(card_name).strip()
        n = int(qty)
        if not name or n <= 0:
            continue

        # 优先用行内 id 前缀判断主备牌（sb=备牌），标题作为兜底
        is_sb = (side_flag == "sb") or in_sideboard
        if is_sb:
            sideboard.append({"qty": n, "name": name})
        else:
            maindeck.append({"qty": n, "name": name, "section": current_section})

    return {"maindeck": maindeck, "sideboard": sideboard}


# ============================================================
# 抓取函数
# ============================================================

def scrape_format_events(format_code: str, max_pages: int = 8,
                         months_back: int = None,
                         start_date: datetime = None,
                         end_date: datetime = None) -> list[dict]:
    """抓取指定赛制指定日期范围内的比赛列表（自动翻页直到超出时间范围）"""
    now = datetime.now()
    if start_date is not None and end_date is not None:
        cutoff = start_date
        upper = end_date
        range_label = f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}"
    elif months_back is not None:
        cutoff = now - timedelta(days=months_back * 30 + 5)
        upper = now
        range_label = f"{months_back} 个月"
    else:
        cutoff = now - timedelta(days=3 * 30 + 5)
        upper = now
        range_label = "3 个月"

    events = []
    for page in range(1, max_pages + 1):
        if page == 1:
            url = f"{BASE_URL}/format?f={format_code}"
        else:
            url = f"{BASE_URL}/format?f={format_code}&meta=50&cp={page}"

        print(f"  抓取比赛列表 第{page}页 ...")
        html = _http_get(url)
        if not html:
            break

        # 获取本页所有比赛（不按日期过滤），用于判断翻页方向
        all_page_events = parse_format_events(html, start_date=None, end_date=None, months_back=None)
        if not all_page_events:
            print(f"  第{page}页无比赛，停止翻页")
            break

        # 按日期范围过滤
        page_events = [ev for ev in all_page_events
                       if _event_in_range(ev, cutoff, upper)]

        if page_events:
            events.extend(page_events)
            print(f"  第{page}页: {len(page_events)} 个比赛（符合日期范围）")

        # 检查本页所有比赛是否全部早于 cutoff（太旧了，可以停止）
        all_too_old = True
        for ev in all_page_events:
            d = _parse_event_date(ev)
            if d is None or d >= cutoff:
                all_too_old = False
                break

        if all_too_old:
            print(f"  第{page}页比赛均早于 {cutoff.strftime('%Y-%m-%d')}，停止翻页")
            break

        # 没有下一页链接则停止
        if f"cp={page + 1}" not in html:
            break

    # 去重
    seen = set()
    unique = []
    for ev in events:
        if ev["event_id"] not in seen:
            seen.add(ev["event_id"])
            unique.append(ev)
    print(f"  共 {len(unique)} 个不重复比赛（{range_label}）")
    return unique


def _event_in_range(ev: dict, cutoff: datetime, upper: datetime) -> bool:
    """检查比赛日期是否在指定范围内"""
    d = _parse_event_date(ev)
    if d is None:
        return True  # 日期解析失败，视为在范围内
    return cutoff <= d <= upper


def _parse_event_date(ev: dict) -> datetime | None:
    """解析比赛日期"""
    try:
        return datetime.strptime(ev["date"], "%Y-%m-%d")
    except (ValueError, KeyError):
        return None


def scrape_event_decks(format_code: str, event_id: str) -> list[dict]:
    """抓取指定比赛的上位卡组列表"""
    url = f"{BASE_URL}/event?e={event_id}&f={format_code}"
    html = _http_get(url)
    if not html:
        return []
    return parse_event_decks(html)


def scrape_deck_cards(format_code: str, event_id: str, deck_id: str) -> dict:
    """抓取指定卡组的卡牌列表"""
    url = f"{BASE_URL}/event?e={event_id}&d={deck_id}&f={format_code}"
    html = _http_get(url)
    if not html:
        return {"maindeck": [], "sideboard": []}
    return parse_deck_cards(html)


# ============================================================
# 主抓取流程 + 增量更新
# ============================================================

def scrape_all_cards(formats: list[str] = None, months_back: int = None,
                     weeks: float = None,
                     start_date: datetime = None, end_date: datetime = None,
                     max_pages: int = 8, with_sideboard: bool = True,
                     done_events: set = None, done_decks: set = None) -> dict:
    """
    主抓取函数：抓取所有赛制的上位卡组用到的单卡。

    日期范围参数（优先级从高到低）：
      - start_date + end_date: 精确日期范围
      - weeks: 最近 N 周
      - months_back: 最近 N 个月
      - 默认: 最近 3 个月

    Args:
        formats: 赛制列表，默认 ["standard", "modern", "pauper"]
        months_back: 回溯月份数（与 weeks 互斥）
        weeks: 回溯周数（与 months_back 互斥）
        start_date: 起始日期（与 end_date 配合使用）
        end_date: 结束日期（与 start_date 配合使用）
        max_pages: 每个赛制最大翻页数
        with_sideboard: 是否统计备牌
        done_events: 已抓取过的 event_id 集合（增量更新用）
        done_decks: 已抓取过的 deck_id 集合（增量更新用）

    Returns:
        {format_name: {"events": [...], "card_counts": {name: count}, "total_decks", "total_events"}}
    """
    if formats is None:
        formats = ["standard", "modern", "pauper"]
    if done_events is None:
        done_events = set()
    if done_decks is None:
        done_decks = set()

    # 解析日期范围
    if start_date is not None and end_date is not None:
        pass  # 使用精确日期范围
    elif weeks is not None:
        end_date = datetime.now()
        start_date = end_date - timedelta(weeks=weeks)
    elif months_back is not None:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30 + 5)
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=3 * 30 + 5)

    results = {}

    for fmt in formats:
        code = FORMAT_CODES.get(fmt)
        if not code:
            print(f"未知赛制: {fmt}")
            continue

        print(f"\n{'=' * 60}")
        print(f"开始抓取 {fmt.upper()} 赛制 (代码: {code})")
        print(f"日期范围: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
        print(f"{'=' * 60}")

        # 1. 比赛列表
        print("  [1/3] 获取比赛列表...")
        events = scrape_format_events(code, max_pages=max_pages,
                                       start_date=start_date, end_date=end_date)

        # 2. 每个比赛的卡组
        print(f"  [2/3] 获取 {len(events)} 个比赛的卡组...")
        all_decks = []
        new_event_count = 0
        for i, ev in enumerate(events):
            if ev["event_id"] in done_events:
                # 已抓过该比赛，可跳过卡组列表抓取（但仍记录）
                continue
            new_event_count += 1
            if (i + 1) % 10 == 0:
                print(f"    进度: {i + 1}/{len(events)}")
            decks = scrape_event_decks(code, ev["event_id"])
            for d in decks:
                d["event_id"] = ev["event_id"]
                d["event_name"] = ev["event_name"]
                d["event_date"] = ev["date"]
            all_decks.extend(decks)
        print(f"    新比赛 {new_event_count} 个，待抓卡组 {len(all_decks)} 个")

        # 3. 每个卡组的卡牌
        print(f"  [3/3] 获取卡牌详情...")
        card_counts = {}  # name -> 总张数（主牌+备牌合并，备牌单独标识）
        skipped_decks = 0
        for i, deck in enumerate(all_decks):
            deck_key = deck["deck_id"]
            if deck_key in done_decks:
                skipped_decks += 1
                continue
            if (i + 1) % 25 == 0:
                print(f"    进度: {i + 1}/{len(all_decks)}")
            cards = scrape_deck_cards(code, deck["event_id"], deck["deck_id"])

            for c in cards["maindeck"]:
                name = c["name"]
                if name in BASIC_LANDS:
                    continue
                card_counts[name] = card_counts.get(name, 0) + c["qty"]
            if with_sideboard:
                for c in cards["sideboard"]:
                    name = c["name"]
                    if name in BASIC_LANDS:
                        continue
                    # 备牌数量单独累计，键加 [SB] 后缀
                    sb_key = f"{name} [SB]"
                    card_counts[sb_key] = card_counts.get(sb_key, 0) + c["qty"]

            done_decks.add(deck_key)
        if skipped_decks:
            print(f"    跳过已抓取卡组 {skipped_decks} 个")

        # 标记所有比赛为已抓取
        for ev in events:
            done_events.add(ev["event_id"])

        results[fmt] = {
            "events": events,
            "card_counts": card_counts,
            "total_decks": len(all_decks),
            "total_events": len(events),
        }
        print(f"    完成！共 {len(card_counts)} 种不同卡牌条目")

    return results


# ============================================================
# 数据持久化
# ============================================================

def save_raw_data(data: dict, filepath: str):
    """保存原始数据为 JSON"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"原始数据已保存: {filepath}")


def load_raw_data(filepath: str) -> dict:
    """加载原始数据"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_progress(filepath: str) -> tuple[set, set]:
    """加载增量更新进度（已抓取的 event_id / deck_id）"""
    if not os.path.exists(filepath):
        return set(), set()
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("done_events", [])), set(data.get("done_decks", []))


def save_progress(filepath: str, done_events: set, done_decks: set):
    """保存增量更新进度"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "done_events": sorted(done_events),
            "done_decks": sorted(done_decks),
            "updated_at": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)
