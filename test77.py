import discord
from discord.ext import commands, tasks
import aiohttp
from thefuzz import process
import json
import asyncio
import sqlite3
import os
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix='!', intents=intents)

KST = timezone(timedelta(hours=9))
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# ==========================================
# [디스코드 봇 환경 설정]
# ==========================================
ADMIN_ROLE_ID = 1421923985137864864 
NEWBIE_JOIN_ROLE_ID = 1508382595455647854 

TICKET_CATEGORIES = {
    "ato": {"id": 1509619272501166080, "name": "아토락시온 파티 찾기"},
    "shrine": {"id": 1517138768845344779, "name": "검은사당 파티 찾기"},
    "blood": {"id": 1517138990476562473, "name": "피의제단 파티 찾기"},
    "join": {"id": 1509621761111621662, "name": "서버 가입 상담"},
    "qna": {"id": 1517139292432891924, "name": "문의 및 건의"},
    "comp": {"id": 1517139292432891924, "name": "불편사항 제보"},
    "error": {"id": 1517139292432891924, "name": "오제보 및 젠타임 오류"},
    "anon": {"id": 1517139393951830117, "name": "익명 제보함"}
}

def format_dt(dt):
    return f"{dt.year}년 {dt.month:02d}월 {dt.day:02d}일 {WEEKDAYS[dt.weekday()]} {dt.hour:02d}시 {dt.minute:02d}분"

def make_codeblock(text):
    return f"```\n{text}\n```"

# ==========================================
# [데이터베이스 연동 및 초기화]
# ==========================================
def init_db():
    conn = sqlite3.connect('bdo_data.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS pearl_history (item_id INTEGER, timestamp DATETIME, total_trades INTEGER, stock INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS rift_history (user_id INTEGER, boss_name TEXT, kill_time DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS welcome_settings (guild_id INTEGER PRIMARY KEY, title TEXT, description TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS item_cache (item_id INTEGER, sid INTEGER, price INTEGER, stock INTEGER, count INTEGER, last_updated DATETIME, PRIMARY KEY (item_id, sid))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS status_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, user_id INTEGER, content TEXT, timestamp DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS boss_alert_channels (guild_id INTEGER PRIMARY KEY, channel_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS boss_alert_users (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS status_alert_users (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS boss_alert_settings (user_id INTEGER, time_str TEXT, PRIMARY KEY (user_id, time_str))''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# [데이터베이스 데이터]
# ==========================================
CAPHRAS_DB = {"녹색무기": {"고": {0:(0,0,0), 1:(4,4,1), 2:(7,11,2), 3:(9,20,3), 4:(14,34,4), 5:(20,54,4), 6:(22,76,4), 7:(23,99,4), 8:(24,123,5), 9:(25,148,5), 10:(26,174,5), 11:(25,199,5), 12:(26,225,6), 13:(27,252,6), 14:(28,280,6), 15:(29,309,6), 16:(30,339,7), 17:(31,370,7), 18:(32,402,7), 19:(33,435,7), 20:(59,494,8)}, "유": {0:(0,0,0), 1:(36,36,1), 2:(60,96,2), 3:(96,192,3), 4:(168,360,4), 5:(226,586,4), 6:(227,813,4), 7:(228,1041,4), 8:(229,1270,5), 9:(230,1500,5), 10:(231,1731,5), 11:(225,1956,5), 12:(226,2182,6), 13:(227,2409,6), 14:(228,2637,6), 15:(229,2866,6), 16:(230,3096,7), 17:(231,3327,7), 18:(232,3559,7), 19:(233,3792,7), 20:(459,4251,8)}, "동": {0:(0,0,0), 1:(297,297,1), 2:(495,792,2), 3:(792,1584,3), 4:(1386,2970,4), 5:(1860,4830,4), 6:(1875,6705,4), 7:(1890,8595,4), 8:(1905,10500,5), 9:(1920,12420,5), 10:(1935,14355,5)}}, "보조무기": {"고": {0:(0,0,0), 1:(2,2,1), 2:(4,6,2), 3:(5,11,3), 4:(7,18,4), 5:(10,28,4), 6:(11,39,4), 7:(12,51,4), 8:(12,63,5), 9:(13,76,5), 10:(13,89,5), 11:(13,102,5), 12:(13,115,6), 13:(14,129,6), 14:(14,143,6), 15:(15,158,6), 16:(15,173,7), 17:(16,189,7), 18:(16,205,7), 19:(17,222,7), 20:(30,252,8)}}, "방어구": {"고": {0:(0,0,0), 1:(3,3,1), 2:(5,8,1), 3:(7,15,1), 4:(10,25,2), 5:(15,40,2), 6:(16,56,2), 7:(17,73,3), 8:(18,91,3), 9:(20,111,4), 10:(19,130,4), 11:(19,149,4), 12:(19,168,5), 13:(20,188,5), 14:(21,209,5), 15:(21,230,6), 16:(22,252,6), 17:(23,275,6), 18:(24,299,7), 19:(25,324,7), 20:(44,368,8)}, "유": {0:(0,0,0), 1:(27,27,1), 2:(45,72,1), 3:(72,144,1), 4:(126,270,2), 5:(170,440,2), 6:(171,611,2), 7:(172,783,3), 8:(172,955,3), 9:(173,1128,4), 10:(174,1302,4), 11:(169,1471,4), 12:(170,1641,5), 13:(170,1811,5), 14:(171,1982,5), 15:(172,2154,6), 16:(173,2327,6), 17:(174,2501,6), 18:(174,2675,7), 19:(175,2850,7), 20:(345,3195,8)}, "동": {0:(0,0,0), 1:(223,223,1), 2:(371,594,1), 3:(594,1188,1), 4:(1040,2228,2), 5:(1395,3623,2), 6:(1406,5029,2), 7:(1418,6447,3), 8:(1429,7876,3), 9:(1440,9316,4), 10:(1451,10767,4)}}}
AP_BRACKETS = [(100, 5), (140, 10), (170, 15), (184, 20), (209, 30), (235, 40), (245, 48), (249, 57), (253, 69), (257, 83), (261, 101), (265, 122), (269, 137), (273, 142), (277, 148), (281, 154), (285, 160), (289, 167), (293, 174), (297, 181), (301, 188), (305, 196), (309, 200), (316, 203), (321, 205), (328, 208), (332, 211), (337, 214), (342, 217), (347, 220), (352, 223), (358, 225), (364, 227), (369, 230), (375, 233), (381, 236), (386, 239), (392, 242), (397, 245)]
DP_BRACKETS = [(203, 1), (211, 2), (218, 3), (226, 4), (233, 5), (241, 6), (248, 7), (256, 8), (263, 9), (271, 10), (278, 11), (286, 12), (293, 13), (301, 14), (308, 15), (315, 16), (322, 17), (329, 18), (335, 19), (341, 20), (347, 21), (353, 22), (359, 23), (365, 24), (371, 25), (377, 26), (383, 27), (389, 28), (395, 29), (401, 30)]
BOSS_DB = {"월": [("02:00", "크자카, 불가살"), ("06:00", "카란다"), ("10:00", "크자카, 불가살"), ("13:00", "카란다"), ("15:00", "쿠툼"), ("19:00", "크자카, 불가살"), ("22:00", "카란다")], "화": [("00:15", "벨"), ("08:00", "쿠툼"), ("10:00", "누베르, 우투리"), ("13:00", "크자카"), ("15:00", "오핀"), ("19:00", "누베르, 우투리"), ("22:00", "쿠툼"), ("23:00", "가모스")], "수": [("02:00", "누베르, 우투리"), ("06:00", "크자카"), ("10:00", "오핀, 금돼지왕"), ("13:00", "카란다"), ("15:00", "누베르"), ("19:00", "오핀, 금돼지왕"), ("22:00", "크자카")], "목": [("08:00", "오핀"), ("10:00", "카란다, 금돼지왕"), ("13:00", "쿠툼"), ("15:00", "크자카"), ("19:00", "카란다, 금돼지왕"), ("22:00", "카란다")], "금": [("02:00", "오핀, 금돼지왕"), ("06:00", "카란다"), ("10:00", "쿠툼"), ("13:00", "크자카"), ("15:00", "카란다"), ("19:00", "쿠툼"), ("22:00", "오핀, 금돼지왕"), ("23:00", "벨")], "토": [("00:15", "가모스"), ("02:00", "카란다, 금돼지왕"), ("06:00", "쿠툼"), ("08:00", "누베르"), ("10:00", "크자카, 불가살"), ("13:00", "카란다"), ("15:00", "오핀, 금돼지왕"), ("19:00", "크자카, 불가살"), ("22:00", "카란다, 금돼지왕")], "일": [("02:00", "쿠툼"), ("06:00", "크자카"), ("10:00", "누베르, 우투리"), ("13:00", "쿠툼"), ("15:00", "카란다, 금돼지왕"), ("19:00", "누베르, 우투리"), ("22:00", "쿠툼")]}
SOVEREIGN_DB = {1: {"name": "장(I)", "cron": 320}, 2: {"name": "광(II)", "cron": 560}, 3: {"name": "고(III)", "cron": 780}, 4: {"name": "유(IV)", "cron": 970}, 5: {"name": "동(V)", "cron": 1350}, 6: {"name": "운(VI)", "cron": 1550}, 7: {"name": "우(VII)", "cron": 2250}, 8: {"name": "풍(VIII)", "cron": 2760}, 9: {"name": "단(IX)", "cron": 3920}, 10: {"name": "환(X)", "cron": 5450}}
DARK_RIFT_DB = {"빨간코": {"난이도": "어려움", "위치": "서부 경비 캠프 북쪽"}, "유적새": {"난이도": "보통", "위치": "브리 나무 유적지"}, "비겁한 베그": {"난이도": "어려움", "위치": "세렌디아 북부 평원"}, "우둔한 나무 정령": {"난이도": "어려움", "위치": "은둔의 숲"}, "페리드": {"난이도": "매우 어려움", "위치": "오마르 용암 동굴"}, "아히브의 그리폰": {"난이도": "매우 어려움", "위치": "나반 초원"}, "로닌": {"난이도": "매우 어려움", "위치": "이빨요정 산림"}, "푸투룸": {"난이도": "매우 어려움", "위치": "발렌시아 사막 지역"}}
DEKIA_DB = [{"name": "장 라이텐의 동력석", "id": 11630, "sid": 1, "light": 165}, {"name": "장 오우거의 반지", "id": 11607, "sid": 1, "light": 165}, {"name": "광 라이텐의 동력석", "id": 11630, "sid": 2, "light": 450}, {"name": "광 오우거의 반지", "id": 11607, "sid": 2, "light": 450}, {"name": "광 깨어난 달의 목걸이", "id": 11663, "sid": 2, "light": 450}, {"name": "장 깨어난 달의 목걸이", "id": 11663, "sid": 1, "light": 165}, {"name": "장 투로의 허리띠", "id": 12257, "sid": 1, "light": 165}, {"name": "장 툰그라드 귀걸이", "id": 11828, "sid": 1, "light": 165}, {"name": "고 라이텐의 동력석", "id": 11630, "sid": 3, "light": 1275}, {"name": "고 오우거의 반지", "id": 11607, "sid": 3, "light": 1275}, {"name": "장 바아의 새벽", "id": 11875, "sid": 1, "light": 165}, {"name": "광 툰그라드 귀걸이", "id": 11828, "sid": 2, "light": 450}, {"name": "장 검은 침식의 귀걸이", "id": 11853, "sid": 1, "light": 165}, {"name": "고 툰그라드 귀걸이", "id": 11828, "sid": 3, "light": 1275}, {"name": "장 툰그라드 목걸이", "id": 11629, "sid": 1, "light": 165}]
BLESS_DB = [{"name": "거대 멧돼지 머리 박제", "id": 6603, "residue": 3}, {"name": "회색 늑대 머리 박제", "id": 6614, "residue": 3}, {"name": "큰뿔사슴 머리 박제", "id": 6605, "residue": 3}, {"name": "곰 머리 박제", "id": 6602, "residue": 3}, {"name": "족제비 박제", "id": 6608, "residue": 3}, {"name": "여우 머리 박제", "id": 6601, "residue": 3}, {"name": "발렌시아 산양 머리 박제", "id": 6616, "residue": 3}, {"name": "서리 늑대 전신 박제", "id": 6632, "residue": 3}, {"name": "깃털 늑대 머리 박제", "id": 6618, "residue": 3}, {"name": "늑대 머리 박제", "id": 6604, "residue": 3}, {"name": "거대 사자 머리 박제", "id": 6617, "residue": 3}, {"name": "발렌시아 암사자 머리 박제", "id": 6629, "residue": 3}, {"name": "풀 코뿔소 머리 박제", "id": 6620, "residue": 3}, {"name": "멧돼지 머리 박제", "id": 6649, "residue": 75}, {"name": "예민한 곰 머리 박제", "id": 6648, "residue": 75}]
PEARL_OUTFIT_DB = [{"name": "[레인저] 실비아 세트", "id": 740263}, {"name": "[발키리] 세라핌 세트", "id": 740176}, {"name": "[란] 유혈비 세트", "id": 740441}, {"name": "[매구] 연향 세트", "id": 740754}, {"name": "[위치] 라브리프 세트", "id": 740209}, {"name": "[매화] 화선곡 세트", "id": 740330}, {"name": "[격투가] 황야의 결투 세트", "id": 740431}, {"name": "[우사] 은하 세트", "id": 740742}, {"name": "[도사] 호선 세트", "id": 740889}, {"name": "[다크나이트] 씬 테르나 세트", "id": 740400}, {"name": "[닌자] 나루사와 세트", "id": 740381}, {"name": "[쿠노이치] 아요 세트", "id": 740368}, {"name": "[가디언] 이닉스트라 세트", "id": 740529}, {"name": "[레인저] 고타렌사 세트", "id": 740032}, {"name": "[금수랑] 다루 세트", "id": 740124}]
FALLBACK_PRICES = {721003: (3000000, 0, 5291811), 44195: (4000000, 15, 9210452), 16001: (300000, 2410, 481951), 16002: (250000, 5210, 851042), 4998: (6000000, 0, 451025), 4997: (2000000, 114, 824015), 768: (4500000, 0, 14205), 773: (8500000, 0, 2451), 9681: (5200000, 410, 15024), 11630: (120000000, 12, 14510), 11607: (115000000, 8, 24510), 6603: (62000000, 10, 0), 6614: (105000000, 46, 0), 6605: (112000000, 70, 0), 6602: (125000000, 22, 0), 6608: (131000000, 103, 0), 6601: (165000000, 114, 0), 6616: (185000000, 106, 0), 6632: (220000000, 907, 0), 6618: (245000000, 75, 0), 6604: (275000000, 19, 0), 6617: (282000000, 251, 0), 6629: (295000000, 374, 0), 6649: (8550000000, 1127, 0), 6648: (8550000000, 437, 0), 6620: (430000000, 3077, 0)}
SNIPE_ITEMS_GROUPS = [["검은 결정 파편", "검은 결정", "응축된 마력의 검은 결정", "뾰족한 흑결정 조각"], ["아침의 숨결", "돼지 고기", "돼지 피", "돼지 가죽"], ["흉포한 야수의 내단", "카프라스의 돌", "척살의 결정", "숲의 결정"]]
SNIPE_ITEM_IDS = {"검은 결정 파편": 4901, "검은 결정": 4902, "응축된 마력의 검은 결정": 4903, "뾰족한 흑결정 조각": 4998, "아침의 숨결": 810014, "돼지 고기": 7901, "돼지 피": 7904, "돼지 가죽": 7905, "흉포한 야수의 내단": 9780, "카프라스의 돌": 721003, "척살의 결정": 820039, "숲의 결정": 820040}

ITEM_LIST = {}

# ==========================================
# [API 통신 및 핵심 엔진]
# ==========================================
def save_to_cache(item_id, sid, price, stock, count):
    try:
        item_id, sid, price, stock, count = int(item_id), int(sid), int(price), int(stock), int(count)
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT OR REPLACE INTO item_cache (item_id, sid, price, stock, count, last_updated) VALUES (?, ?, ?, ?, ?, ?)", (item_id, sid, price, stock, count, now_str))
        conn.commit(); conn.close()
    except: pass

async def get_fallback_value(item_id, sid=0):
    try:
        item_id, sid = int(item_id), int(sid)
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute("SELECT price, stock, count FROM item_cache WHERE item_id=? AND sid=?", (item_id, sid))
        row = c.fetchone()
        conn.close()
        if row and row[0] is not None and int(row[0]) > 0: return int(row[0]), int(row[1]), int(row[2])
    except Exception: pass 
    return FALLBACK_PRICES.get(item_id, (0,0,0))

PA_BASE_URL = "https://trade.kr.playblackdesert.com"
PA_HEADERS = {"User-Agent": "BlackDesert", "Content-Type": "application/json", "Accept": "application/json"}

def parse_pa_resultmsg(result_msg):
    """
    PA 원본 GetWorldMarketSubList 응답(resultMsg)을 파싱.
    각 항목 형식: itemId-minEnhance-maxEnhance-basePrice-currentStock-totalTrades-priceMin-priceMax-lastSalePrice-lastSaleTime
    (PA 공식 문서 기준: index 4=Current stock, index 5=Total trades)
    항목들은 '|'로 구분됨. 마지막에 빈 문자열이 남을 수 있어 필터링.
    """
    entries = []
    if not result_msg:
        return entries
    for chunk in result_msg.split('|'):
        if not chunk:
            continue
        parts = chunk.split('-')
        if len(parts) < 6:
            continue
        try:
            entries.append({
                "item_id": int(parts[0]),
                "min_enhance": int(parts[1]),
                "max_enhance": int(parts[2]),
                "base_price": int(parts[3]),
                "current_stock": int(parts[4]),
                "total_trades": int(parts[5]),
                "last_sale_price": int(parts[8]) if len(parts) > 8 else 0,
            })
        except (ValueError, IndexError):
            continue
    return entries

async def fetch_pa_sublist(item_id):
    """PA 원본 API로 특정 item_id의 강화단계별(sid) 가격 리스트를 가져온다."""
    url = f"{PA_BASE_URL}/Trademarket/GetWorldMarketSubList"
    payload = {"keyType": 0, "mainKey": item_id}
    async with aiohttp.ClientSession(headers=PA_HEADERS) as session:
        async with session.post(url, json=payload, timeout=8) as response:
            if response.status != 200:
                raise RuntimeError(f"PA API status {response.status}")
            data = await response.json()
            if data.get("resultCode") != 0:
                raise RuntimeError(f"PA API resultCode {data.get('resultCode')}: {data.get('resultMsg')}")
            return parse_pa_resultmsg(data.get("resultMsg", ""))

async def get_market_price(item_id, sid=0):
    try: item_id, sid = int(item_id), int(sid)
    except: return 0, 0, 0
    try:
        entries = await fetch_pa_sublist(item_id)
        if not entries:
            return await get_fallback_value(item_id, sid)

        # 1) min_enhance(=sid)와 정확히 일치하는 항목 탐색
        for e in entries:
            if e["min_enhance"] == sid:
                p, s, t = e["base_price"], e["current_stock"], e["total_trades"]
                if p > 0:
                    save_to_cache(item_id, sid, p, s, t)
                    return p, s, t
                break  # sid는 맞는데 가격이 0이면 fallback으로

        # 2) sid=0 요청인데 정확히 일치하는 항목이 없었던 경우, 첫 항목을 기본값으로 사용
        if sid == 0:
            e = entries[0]
            p, s, t = e["base_price"], e["current_stock"], e["total_trades"]
            if p > 0:
                save_to_cache(item_id, sid, p, s, t)
                return p, s, t

        return await get_fallback_value(item_id, sid)
    except Exception as e:
        print(f"⚠️ get_market_price 실패 (item_id={item_id}, sid={sid}): {type(e).__name__}: {e}")
        return await get_fallback_value(item_id, sid)

def format_kr(num):
    res = []
    eok, man, rest = num // 100000000, (num % 100000000) // 10000, num % 10000
    if eok > 0: res.append(f"{eok}억")
    if man > 0: res.append(f"{man}만")
    if rest > 0:
        th, h, t, o = rest // 1000, (rest % 1000) // 100, (rest % 100) // 10, rest % 10
        if th > 0: res.append(f"{th}천")
        if h > 0: res.append(f"{h}백")
        if t > 0: res.append(f"{t}십")
        if o > 0: res.append(f"{o}")
    return " ".join(res) if res else str(num)

def calculate_devour(start, target):
    current, faint_count = start, 0
    while current < target:
        if current < 113: current += 13
        elif current < 120: current += 11
        elif current < 130: current += 10
        elif current < 140: current += 9
        elif current < 150: current += 8
        elif current < 160: current += 7
        elif current < 180: current += 6
        elif current < 200: current += 5
        elif current < 220: current += 4
        elif current < 260: current += 3
        else: current += 2
        faint_count += 1
        if current >= 300: current = 300; break
    return faint_count, current, faint_count * 500000000

def get_bracket_info(value, brackets, is_dp=False):
    current_bonus, next_req, next_bonus = 0, None, None
    for i, (req, bonus) in enumerate(brackets):
        if value >= req:
            current_bonus = bonus
            if i + 1 < len(brackets): next_req, next_bonus = brackets[i+1][0], brackets[i+1][1]
            else: next_req, next_bonus = None, None
        else:
            if current_bonus == 0 and i == 0: next_req, next_bonus = brackets[0][0], brackets[0][1]
            break
    unit = "%" if is_dp else ""
    t_name = "피해감소" if is_dp else "공격력"
    if current_bonus == 0 and next_req: return f"현재 보너스 없음\n▶ 다음 구간(**{next_req}**)까지: **{next_req - value}** 필요 (보너스 {next_bonus}{unit})"
    elif next_req: return f"현재 보너스 {t_name}: **+{current_bonus}{unit}**\n▶ 다음 구간(**{next_req}**)까지: **{next_req - value}** 필요 (보너스 +{next_bonus}{unit})"
    else: return f"현재 보너스 {t_name}: **+{current_bonus}{unit}**\n▶ (최고 보너스 구간 도달)"

def get_bdo_time():
    """
    검은사막 공식 낮/밤 시간 비율 반영:
      - 낮(인게임 07:00~22:00, 15시간) : 현실 200분(3시간20분) 동안 진행 -> 배속 4.5배
      - 밤(인게임 22:00~07:00, 9시간)  : 현실 40분 동안 진행          -> 배속 13.5배
      - 하루 전체 = 현실 240분(4시간) 주기로 반복
    기준점(BASE_DT)은 실측 검증된 시각: 2026-06-27 17:19:33 KST = 인게임 07:00
    (검증: KST 18:10 -> 인게임 10:47, 실측값과 일치)
    """
    BASE_DT = datetime(2026, 6, 27, 17, 19, 33, tzinfo=KST)
    now = datetime.now(KST)
    elapsed_min = (now - BASE_DT).total_seconds() / 60.0
    real_min_in_cycle = elapsed_min % 240
    if real_min_in_cycle < 0:
        real_min_in_cycle += 240

    if real_min_in_cycle < 200:  # 낮 구간
        game_min_since_7am = real_min_in_cycle * 4.5
        is_night = False
        remain_m = 200 - real_min_in_cycle
    else:  # 밤 구간
        game_min_since_7am = 900 + (real_min_in_cycle - 200) * 13.5
        is_night = True
        remain_m = 240 - real_min_in_cycle

    total_game_min = (7 * 60 + game_min_since_7am) % 1440
    hour = int(total_game_min // 60)
    minute = int(total_game_min % 60)
    return f"{hour:02d}:{minute:02d}", "밤" if is_night else "낮", int(round(remain_m))

# ==========================================
# 📈 [아이템 평균가 조회 드롭다운 시스템]
# ==========================================
class AvgPriceSelectView(discord.ui.View):
    def __init__(self, options, raw_input):
        super().__init__(timeout=None)
        self.select = discord.ui.Select(placeholder=f"아이템을 선택해주세요.", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        val = self.select.values[0]
        item_id, sid = map(int, val.split('_'))
        b_name = next(opt.label for opt in self.select.options if opt.value == val)
        
        await interaction.response.defer(ephemeral=True)
        price, stock, _ = await get_market_price(item_id, sid)
        
        embed = discord.Embed(title="아이템 평균가 조회", color=0x3498db)
        if price > 0:
            embed.description = f"**선택한 아이템:** `{b_name}`\n\n**가격:** **{price:,}** 은화 ({format_kr(price)})\n**매물:** {stock:,}개"
        else:
            embed.description = f"**선택한 아이템:** `{b_name}`\n\n현재 매물이 없거나 가격 정보를 불러올 수 없습니다."
        
        await interaction.edit_original_response(embed=embed, view=self)

class AvgPriceModal(discord.ui.Modal, title='아이템 평균가 조회'):
    item_input = discord.ui.TextInput(label='아이템 이름 (비슷하게 쳐도 됩니다)', placeholder='예: 프리오네, 기억의 파편, 7210', required=True, max_length=30)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw_input = self.item_input.value.strip()
        
        if not ITEM_LIST: 
            await interaction.followup.send("데이터베이스 로드 중입니다. 잠시 후 다시 시도해주세요.", ephemeral=True); return
            
        matches = []
        if raw_input.isdigit():
            item_id = int(raw_input)
            b_name = next((n for n, i in ITEM_LIST.items() if i == item_id), str(item_id))
            matches.append((b_name, item_id))
        else:
            for name, iid in ITEM_LIST.items():
                if raw_input.replace(" ", "") in name.replace(" ", ""):
                    matches.append((name, iid))
            if not matches:
                bests = process.extractBests(raw_input, ITEM_LIST.keys(), limit=5)
                for b_name, score in bests:
                    if score >= 50: matches.append((b_name, ITEM_LIST[b_name]))
        
        if not matches:
            await interaction.followup.send(f"'{raw_input}'을(를) 찾을 수 없습니다.", ephemeral=True); return
            
        matches = matches[:3] 
        
        async def fetch_item(iid):
            try:
                return await fetch_pa_sublist(iid)
            except Exception as e:
                print(f"⚠️ PA API 호출 실패 (item_id={iid}): {type(e).__name__}: {e}")
                return None

        tasks = [fetch_item(iid) for _, iid in matches]
        results = await asyncio.gather(*tasks)
        
        def get_enhance_prefix(sid, b_name):
            if sid == 0: return ""
            if 16 <= sid <= 20: return {16:"장 ", 17:"광 ", 18:"고 ", 19:"유 ", 20:"동 "}[sid]
            acc_keys = ["반지", "목걸이", "귀걸이", "허리띠", "군왕", "프리오네", "카라자드", "데보레카", "유물"]
            if any(k in b_name for k in acc_keys) and 1 <= sid <= 10:
                return {1:"장 ", 2:"광 ", 3:"고 ", 4:"유 ", 5:"동 ", 6:"운 ", 7:"우 ", 8:"풍 ", 9:"단 ", 10:"환 "}.get(sid, f"+{sid} ")
            return f"+{sid} "

        options = []
        for (b_name, b_id), entries in zip(matches, results):
            if not entries: continue

            entries_sorted = sorted(entries, key=lambda e: e["min_enhance"])
            for e in entries_sorted:
                sid = e["min_enhance"]
                prefix = get_enhance_prefix(sid, b_name)
                opt_label = f"{prefix}{b_name}".strip()
                if len(options) < 25:
                    options.append(discord.SelectOption(label=opt_label[:100], value=f"{b_id}_{sid}"))
                    
        if not options:
            await interaction.followup.send("매물 데이터를 찾을 수 없습니다.", ephemeral=True); return
            
        view = AvgPriceSelectView(options, raw_input)
        embed = discord.Embed(title="아이템 평균가 조회", description="조회할 아이템을 선택해주세요.", color=0x2b2d31)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# ==========================================
# 🛠️ [편의기능 Modals (본인만 보기)]
# ==========================================
class CaphrasModal(discord.ui.Modal, title='카프라스 돌파 계산기'):
    equip_type = discord.ui.TextInput(label='장비 종류 (녹색무기/보조무기/방어구)', placeholder='방어구', required=True)
    grade = discord.ui.TextInput(label='강화 등급 (고/유/동)', placeholder='동', required=True, max_length=1)
    start_lvl = discord.ui.TextInput(label='현재 카프 단계 (0~19)', placeholder='0', required=True, max_length=2)
    target_lvl = discord.ui.TextInput(label='목표 카프 단계 (1~20)', placeholder='10', required=True, max_length=2)
    async def on_submit(self, interaction: discord.Interaction):
        eq, gr = self.equip_type.value.strip(), self.grade.value.strip()
        try: start, target = int(self.start_lvl.value), int(self.target_lvl.value)
        except ValueError: await interaction.response.send_message("단계는 숫자만 입력!", ephemeral=True); return
        if eq not in CAPHRAS_DB or gr not in CAPHRAS_DB[eq]: await interaction.response.send_message("장비 종류/등급 오류", ephemeral=True); return
        db = CAPHRAS_DB[eq][gr]
        if start not in db or target not in db or start >= target: await interaction.response.send_message("단계 범위 오류", ephemeral=True); return
        req_stones = db[target][1] - db[start][1]
        embed = discord.Embed(color=0x2ecc71, title="카프라스 돌파 계산 결과")
        embed.description = f"**장비:** {gr} {eq}\n**단계:** {start} ➡️ {target}단계 (스탯 +{db[target][2] - db[start][2]})\n\n**필요 카프라스:** **{req_stones:,}개**\n**예상 은화:** **{req_stones * 2000000:,} 은화**"
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ApDpModal(discord.ui.Modal, title='공/방 보너스 구간 계산기'):
    ap_input = discord.ui.TextInput(label='현재 공격력 (미입력 시 생략)', placeholder='예: 281', required=False, max_length=3)
    dp_input = discord.ui.TextInput(label='현재 방어력 (미입력 시 생략)', placeholder='예: 380', required=False, max_length=3)
    async def on_submit(self, interaction: discord.Interaction):
        ap_val, dp_val = self.ap_input.value.strip(), self.dp_input.value.strip()
        if not ap_val and not dp_val: await interaction.response.send_message("최소 하나는 입력해 주세요!", ephemeral=True); return
        embed = discord.Embed(title="공/방 보너스 계산 결과", color=0xe74c3c)
        if ap_val and ap_val.isdigit(): embed.add_field(name=f"공격력 ({int(ap_val)})", value=get_bracket_info(int(ap_val), AP_BRACKETS, False), inline=False)
        if dp_val and dp_val.isdigit(): embed.add_field(name=f"방어력 ({int(dp_val)})", value=get_bracket_info(int(dp_val), DP_BRACKETS, True), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class DevourModal(discord.ui.Modal, title='어둠 포식 효율 계산'):
    start_stack = discord.ui.TextInput(label='현재스택 (발크스 미포함)', placeholder='100~299', required=True, max_length=3)
    target_stack = discord.ui.TextInput(label='희망스택 (101~300)', placeholder='101~300', required=True, max_length=3)
    async def on_submit(self, interaction: discord.Interaction):
        try: start, target = int(self.start_stack.value), int(self.target_stack.value)
        except ValueError: await interaction.response.send_message("숫자만 입력해 주세요!", ephemeral=True); return
        count, final_stack, total_cost = calculate_devour(start, target)
        embed = discord.Embed(color=0x3498db, title="어둠 포식 효율 계산") 
        embed.description = f"**시작 스택:** {start} ➡️ **희망 스택:** {target}\n\n**은은한 포식 (거래소)**\n필요 개수: {count}개\n총 비용: **{total_cost:,}** 은화 ({format_kr(total_cost)})\n\n최종 도달 스택: **{final_stack}**"
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SovWeaponSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="주무기", style=discord.ButtonStyle.secondary)
    async def btn_main(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(SovModal("주무기"))
    @discord.ui.button(label="각성무기", style=discord.ButtonStyle.secondary)
    async def btn_awk(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(SovModal("각성무기"))
    @discord.ui.button(label="보조무기", style=discord.ButtonStyle.secondary)
    async def btn_sub(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(SovModal("보조무기"))

class SovModal(discord.ui.Modal):
    start_lvl = discord.ui.TextInput(label='현재 단계 (0=노강, 5=동, 9=단)', placeholder='0 ~ 9 사이의 숫자', required=True, max_length=1)
    target_lvl = discord.ui.TextInput(label='목표 단계 (1=장, 5=동, 10=환)', placeholder='1 ~ 10 사이의 숫자', required=True, max_length=2)
    def __init__(self, weapon_type):
        super().__init__(title=f'군왕 {weapon_type} 강화 계산기')
        self.weapon_type = weapon_type
    async def on_submit(self, interaction: discord.Interaction):
        try: start, target = int(self.start_lvl.value), int(self.target_lvl.value)
        except ValueError: await interaction.response.send_message("숫자로만 입력해 주세요!", ephemeral=True); return
        if start < 0 or target > 10 or start >= target: await interaction.response.send_message("올바른 단계 범위를 입력해 주세요.", ephemeral=True); return
        total_crons, total_bs = 0, target - start
        desc = ""
        for level in range(start + 1, target + 1):
            cron_req = SOVEREIGN_DB[level]["cron"]
            total_crons += cron_req
            desc += f"▶ **{SOVEREIGN_DB[level]['name']}**: 크론석 `{cron_req:,}`개 + 태초블스 `1`개\n"
        total_silver = (total_crons * 3000000) + (total_bs * 100000000)
        start_name = "노강(+0)" if start == 0 else SOVEREIGN_DB[start]["name"]
        embed = discord.Embed(color=0xffd700, title=f"군왕 {self.weapon_type} 스트레이트 강화 비용")
        embed.description = f"**목표:** {start_name} ➡️ {SOVEREIGN_DB[target]['name']}\n\n{desc}\n**크론석:** **{total_crons:,}**개\n**태초블스:** **{total_bs:,}**개\n\n**예상 은화:** 약 **{total_silver:,} 은화**\n({format_kr(total_silver)})"
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TaxModal(discord.ui.Modal):
    def __init__(self, bonus_rate): super().__init__(title='거래소 실수령액 계산기'); self.bonus_rate = bonus_rate
    price_input = discord.ui.TextInput(label='판매 가격', placeholder='예: 200', required=True, max_length=15)
    qty_input = discord.ui.TextInput(label='개수', placeholder='예: 2000', required=True, max_length=10)
    async def on_submit(self, interaction: discord.Interaction):
        try: price, qty = int(self.price_input.value.replace(",", "").replace(" ", "")), int(self.qty_input.value.replace(",", "").replace(" ", ""))
        except ValueError: await interaction.response.send_message("숫자만 입력해 주세요!", ephemeral=True); return
        total_price = price * qty
        final_receipt = int(total_price * 0.65 * (1 + self.bonus_rate))
        embed = discord.Embed(color=0x3498db, title="거래소 실수령액 계산기")
        embed.description = f"**판매 가격:** {price:,} ({format_kr(price)})\n**개수:** {qty:,}개\n**총 판매가격:** {total_price:,} ({format_kr(total_price)})\n\n**실제 수령액:** **{final_receipt:,}** ({format_kr(final_receipt)})"
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TaxSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.vp_select = discord.ui.Select(placeholder="밸류 패키지", options=[discord.SelectOption(label="O", value="O"), discord.SelectOption(label="X", value="X")])
        self.fame_select = discord.ui.Select(placeholder="가문 명성", options=[discord.SelectOption(label="없음", value="0"), discord.SelectOption(label="1단계", value="1"), discord.SelectOption(label="2단계", value="2"), discord.SelectOption(label="3단계", value="3")])
        self.ring_select = discord.ui.Select(placeholder="거상의 반지", options=[discord.SelectOption(label="O", value="O"), discord.SelectOption(label="X", value="X")])
        async def defer_callback(inter): await inter.response.defer()
        self.vp_select.callback, self.fame_select.callback, self.ring_select.callback = defer_callback, defer_callback, defer_callback
        self.add_item(self.vp_select); self.add_item(self.fame_select); self.add_item(self.ring_select)
    @discord.ui.button(label="계산하기", style=discord.ButtonStyle.primary)
    async def btn_calc(self, interaction: discord.Interaction, button: discord.ui.Button):
        vp = self.vp_select.values[0] if self.vp_select.values else "X"
        fame = self.fame_select.values[0] if self.fame_select.values else "0"
        ring = self.ring_select.values[0] if self.ring_select.values else "X"
        bonus = sum([0.30 if vp == "O" else 0, 0.005 if fame == "1" else 0.010 if fame == "2" else 0.015 if fame == "3" else 0, 0.05 if ring == "O" else 0])
        await interaction.response.send_modal(TaxModal(bonus_rate=bonus))

class PearlTimeView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def fetch_and_show(self, interaction: discord.Interaction, hours: int, time_label: str):
        await interaction.response.defer(ephemeral=True)
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        now = datetime.now(KST)
        target_time = (now - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        
        ranking = []
        for item in PEARL_OUTFIT_DB:
            c.execute("SELECT total_trades, stock, timestamp FROM pearl_history WHERE item_id=? ORDER BY timestamp DESC LIMIT 1", (item['id'],))
            latest = c.fetchone()
            c.execute("SELECT total_trades FROM pearl_history WHERE item_id=? AND timestamp >= ? ORDER BY timestamp ASC LIMIT 1", (item['id'], target_time))
            oldest = c.fetchone()
            
            if latest and oldest:
                recent_trades = latest[0] - oldest[0]
                stock = latest[1]
                last_time_str = latest[2][5:16]
                if recent_trades > 0:
                    est_hours = (stock / recent_trades) * hours
                    est_timedelta = timedelta(hours=est_hours)
                    d = est_timedelta.days
                    h = est_timedelta.seconds // 3600
                    est_str = f"{d}일 {h}시간" if d > 0 else f"{h}시간"
                else: est_str = "계산 불가 (최근 거래없음)"
                ranking.append({"name": item["name"], "trades": recent_trades, "preorder": stock, "last": last_time_str, "est": est_str})
        conn.close()
        
        if not ranking:
            await interaction.followup.send("현재 봇이 데이터베이스(DB)를 수집 중입니다. (최소 10분 이후 데이터를 불러올 수 있습니다.)", ephemeral=True)
            return
            
        ranking.sort(key=lambda x: x["trades"], reverse=True)
        desc = f"**{time_label} 펄 의상 판매 개수**\n\n"
        for r in ranking:
            desc += f" {r['name']}\n거래수 : {r['trades']}개 / 예약구매 : {r['preorder']}개\n최근 데이터 : {r['last']}\n예상 : {r['est']}\n\n"
        
        embed = discord.Embed(color=0x9b59b6)
        embed.description = desc[:4000]
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="3일간", style=discord.ButtonStyle.secondary)
    async def btn_3d(self, interaction: discord.Interaction, button: discord.ui.Button): await self.fetch_and_show(interaction, 72, "3일간")
    @discord.ui.button(label="1일간", style=discord.ButtonStyle.secondary)
    async def btn_1d(self, interaction: discord.Interaction, button: discord.ui.Button): await self.fetch_and_show(interaction, 24, "1일간")
    @discord.ui.button(label="12시간", style=discord.ButtonStyle.secondary)
    async def btn_12h(self, interaction: discord.Interaction, button: discord.ui.Button): await self.fetch_and_show(interaction, 12, "12시간")
    @discord.ui.button(label="6시간", style=discord.ButtonStyle.secondary)
    async def btn_6h(self, interaction: discord.Interaction, button: discord.ui.Button): await self.fetch_and_show(interaction, 6, "6시간")
    @discord.ui.button(label="3시간", style=discord.ButtonStyle.secondary)
    async def btn_3h(self, interaction: discord.Interaction, button: discord.ui.Button): await self.fetch_and_show(interaction, 3, "3시간")

class SnipeInputModal(discord.ui.Modal):
    def __init__(self, page, parent_view):
        super().__init__(title=f'저격 수렵 계산기 - 입력 {page}')
        self.page = page; self.parent_view = parent_view; self.inputs = []
        for item_name in SNIPE_ITEMS_GROUPS[page - 1]:
            val = self.parent_view.data[item_name]
            text_input = discord.ui.TextInput(label=item_name, placeholder='0', required=False, default=str(val) if val > 0 else None)
            self.add_item(text_input)
            self.inputs.append((item_name, text_input))
    async def on_submit(self, interaction: discord.Interaction):
        for item_name, text_input in self.inputs:
            val = text_input.value.strip().replace(",", "")
            if val == "": self.parent_view.data[item_name] = 0
            elif val.isdigit(): self.parent_view.data[item_name] = int(val)
        await self.parent_view.update_message(interaction)

class SnipeCalcView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.data = {name: 0 for group in SNIPE_ITEMS_GROUPS for name in group}
    def generate_embed(self):
        embed = discord.Embed(title="저격 수렵 계산기", color=0x2b2d31)
        desc = "".join([f" {n} : `{c}`\n" for n, c in self.data.items()])
        embed.description = desc
        return embed
    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
    @discord.ui.button(label="입력1", style=discord.ButtonStyle.secondary)
    async def btn_in1(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(SnipeInputModal(1, self))
    @discord.ui.button(label="입력2", style=discord.ButtonStyle.secondary)
    async def btn_in2(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(SnipeInputModal(2, self))
    @discord.ui.button(label="입력3", style=discord.ButtonStyle.secondary)
    async def btn_in3(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(SnipeInputModal(3, self))
    @discord.ui.button(label="계산하기", style=discord.ButtonStyle.success)
    async def btn_calc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        total_silver = 0
        details = []
        for n, count in self.data.items():
            if count > 0:
                item_id = SNIPE_ITEM_IDS.get(n, 0)
                price, _, _ = await get_market_price(item_id) if item_id > 0 else (0, 0, 0)
                subtotal = count * price
                total_silver += subtotal
                details.append(f"**{n}** : {price:,} x {count} = **{subtotal:,}**")
        embed = discord.Embed(title="저격 수렵 최종 수익", color=0x2ecc71)
        if details: embed.description = "\n".join(details) + f"\n\n**총 수익:** **{total_silver:,}** 은화\n({format_kr(total_silver)})"
        else: embed.description = "입력된 수렵 전리품이 없습니다."
        await interaction.followup.send(embed=embed, ephemeral=True)

class SnipeMainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="계산하기", style=discord.ButtonStyle.success)
    async def btn_calc(self, interaction: discord.Interaction, button: discord.ui.Button):
        calc_view = SnipeCalcView()
        await interaction.response.send_message(embed=calc_view.generate_embed(), view=calc_view, ephemeral=True)

# ==========================================
# [어둠의 틈 시스템]
# ==========================================
def build_rift_status_embed(boss, spawn_time):
    """어둠의 틈 보스의 다음 젠 시간 상태를 보여주는 임베드를 만든다. (조회/등록 후 결과 모두 동일한 형태로 통일)"""
    now = datetime.now(KST)
    diff = spawn_time - now
    embed = discord.Embed(title="어둠의 틈", color=0x2b2d31)
    if diff.total_seconds() > 0:
        days, remainder = divmod(diff.total_seconds(), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        embed.description = f"다음 젠 까지 {int(days)}일 {int(hours)}시간 {int(minutes)}분 남음\n\n**젠 예정 시간**\n{format_dt(spawn_time)}"
    else:
        embed.description = f"**현재 젠 완료 상태입니다!**\n\n**젠 예정 시간**\n{format_dt(spawn_time)}"
    return embed

class DarkRiftMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        options = [discord.SelectOption(label=boss, value=boss) for boss in DARK_RIFT_DB.keys()]
        self.select = discord.ui.Select(placeholder="보스를 선택해주세요", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        boss = self.select.values[0]
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute("SELECT kill_time FROM rift_history WHERE user_id=? AND boss_name=?", (interaction.user.id, boss))
        row = c.fetchone()
        conn.close()
        
        if row:
            kill_time = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST)
            spawn_time = kill_time + timedelta(days=5)
            embed = build_rift_status_embed(boss, spawn_time)
        else:
            embed = discord.Embed(title="어둠의 틈", color=0x2b2d31)
            embed.description = "기록된 처치 시간이 없습니다. 아래 버튼으로 등록해주세요."
            
        await interaction.response.edit_message(embed=embed, view=DarkRiftActionView(boss))

class DarkRiftActionView(discord.ui.View):
    def __init__(self, boss):
        super().__init__(timeout=None)
        self.boss = boss
        
    @discord.ui.button(label="현재 시간으로", style=discord.ButtonStyle.success, custom_id="rift_btn_now")
    async def btn_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        now = datetime.now(KST)
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM rift_history WHERE user_id=? AND boss_name=?", (interaction.user.id, self.boss))
        c.execute("INSERT INTO rift_history VALUES (?, ?, ?)", (interaction.user.id, self.boss, now_str))
        conn.commit(); conn.close()
        
        spawn_time = now + timedelta(days=5)
        embed = build_rift_status_embed(self.boss, spawn_time)
        await interaction.response.edit_message(embed=embed, view=DarkRiftActionView(self.boss))

    @discord.ui.button(label="시간 직접 입력", style=discord.ButtonStyle.secondary, custom_id="rift_btn_manual")
    async def btn_manual(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DarkRiftManualModal(self.boss))
        
class DarkRiftManualModal(discord.ui.Modal):
    day_input = discord.ui.TextInput(label='일', placeholder='예: 31', required=True, max_length=2)
    hour_input = discord.ui.TextInput(label='시', placeholder='예: 14', required=True, max_length=2)
    minute_input = discord.ui.TextInput(label='분', placeholder='예: 30', required=True, max_length=2)

    def __init__(self, boss):
        super().__init__(title='어둠의 틈 시간 입력')
        self.boss = boss
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            d, h, m = int(self.day_input.value), int(self.hour_input.value), int(self.minute_input.value)
            now = datetime.now(KST)
            kill_time = now.replace(day=d, hour=h, minute=m, second=0, microsecond=0)
            conn = sqlite3.connect('bdo_data.db')
            c = conn.cursor()
            c.execute("DELETE FROM rift_history WHERE user_id=? AND boss_name=?", (interaction.user.id, self.boss))
            c.execute("INSERT INTO rift_history VALUES (?, ?, ?)", (interaction.user.id, self.boss, kill_time.strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit(); conn.close()
            
            spawn_time = kill_time + timedelta(days=5)
            embed = build_rift_status_embed(self.boss, spawn_time)
            await interaction.response.edit_message(embed=embed, view=DarkRiftActionView(self.boss))
        except ValueError: 
            await interaction.response.send_message("날짜와 시간을 올바른 숫자로 입력해 주세요.", ephemeral=True)

class BdoTimeView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="현재 시간 확인", style=discord.ButtonStyle.primary, custom_id="bdo_time_check")
    async def btn_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        now_t, status, remain = get_bdo_time()
        next_status = "밤" if status == "낮" else "낮"
        embed = discord.Embed(title="검은사막 인게임 시간", color=0x2b2d31)
        embed.description = f"현재 인게임 시간은 **{now_t}** 입니다.\n\n현재 상태: **{status}**\n{next_status}으로 전환까지 (현실 기준) **{remain}분** 남음"
        embed.set_footer(text=f"공식 낮/밤 주기 기준 · {datetime.now(KST).strftime('%H:%M')}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# [현황 제보 시스템 - 모달 및 출력]
# ==========================================
class StatusReportModal(discord.ui.Modal):
    def __init__(self, s_type, s_title):
        super().__init__(title=f'{s_title} 제보')
        self.s_type = s_type
        placeholder_val = '아에테리온 / 님파마레 / 오르비타 / 테네브라움 / 제피로스' if s_type == "edana" else '해축 / 달축 / 땅축'
        self.region = discord.ui.TextInput(label='종류', placeholder=placeholder_val, required=True)
        self.channel = discord.ui.TextInput(label='채널/서버', placeholder='예: 하이델-1', required=True)
        self.time = discord.ui.TextInput(label='남은 시간(분)', placeholder='예: 60', required=True, max_length=3)
        self.add_item(self.region); self.add_item(self.channel); self.add_item(self.time)
        
    async def on_submit(self, interaction: discord.Interaction):
        report_content = f"{self.region.value} | {self.channel.value} | 남은시간: {self.time.value}분"
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT INTO status_reports (type, user_id, content, timestamp) VALUES (?, ?, ?, ?)", (self.s_type, interaction.user.id, report_content, now_str))
        
        c.execute("SELECT user_id FROM status_alert_users")
        alert_users = c.fetchall()
        conn.commit(); conn.close()
        
        await interaction.response.send_message(f"제보가 등록되었습니다!", ephemeral=True)
        
        s_title = "영물의 축복" if self.s_type == "blessing" else "에다니아"
        alert_embed = discord.Embed(title=f"새로운 {s_title} 제보 도착!", color=0x3498db)
        alert_embed.description = f"**종류:** {self.region.value}\n**채널/서버:** {self.channel.value}\n**남은 시간:** {self.time.value}분"
        
        for (u_id,) in alert_users:
            user = bot.get_user(u_id)
            if user and user.id != interaction.user.id:
                try: await user.send(embed=alert_embed)
                except: pass

class StatusViewPanel(discord.ui.View):
    def __init__(self, s_type, s_title):
        super().__init__(timeout=None)
        self.s_type = s_type
        self.s_title = s_title
        
        btn_report = discord.ui.Button(label="위치 제보하기", style=discord.ButtonStyle.success, custom_id=f"btn_report_{s_type}")
        btn_report.callback = self.btn_report_callback
        self.add_item(btn_report)

        btn_refresh = discord.ui.Button(label="현황확인", style=discord.ButtonStyle.primary, custom_id=f"btn_refresh_{s_type}")
        btn_refresh.callback = self.btn_refresh_callback
        self.add_item(btn_refresh)
    
    async def btn_report_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StatusReportModal(self.s_type, self.s_title))
        
    async def btn_refresh_callback(self, interaction: discord.Interaction):
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute("SELECT content, timestamp FROM status_reports WHERE type=? ORDER BY timestamp DESC LIMIT 5", (self.s_type,))
        rows = c.fetchall()
        conn.close()
        
        embed = discord.Embed(title=f"최신 {self.s_title} 현황", color=0x9b59b6)
        if rows:
            desc = ""
            for row in rows:
                parts = row[0].split(" | ")
                if len(parts) >= 3: desc += f"`{row[1][11:16]}` | **{parts[0]}**\n• {parts[1]} / {parts[2]}\n\n"
                else: desc += f"`{row[1][11:16]}` | **{row[0]}**\n\n"
            embed.description = desc
        else: embed.description = "아직 등록된 제보가 없습니다."
        await interaction.response.edit_message(embed=embed, view=self)


# ==========================================
# [가입 승인 관리자 시스템 - 자동 역할 지급 및 삭제]
# ==========================================
class JoinProcessModal(discord.ui.Modal, title='가입 처리결과 전송'):
    result_message = discord.ui.TextInput(label='전달 내용', style=discord.TextStyle.paragraph, required=True)
    def __init__(self, target_user_id: int, is_approve: bool):
        super().__init__()
        self.target_user_id = target_user_id
        self.is_approve = is_approve
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target_member = interaction.guild.get_member(self.target_user_id)
        
        if not target_member:
            await interaction.followup.send("유저를 찾을 수 없어 처리를 중단합니다.", ephemeral=True)
            return
            
        color = 0x2ecc71 if self.is_approve else 0xe74c3c
        title = "가입이 승인되었습니다." if self.is_approve else "가입이 거절되었습니다."
        embed = discord.Embed(title=title, description="관리자의 전달 메시지입니다.", color=color)
        embed.add_field(name="전달 내용", value=make_codeblock(self.result_message.value), inline=False)
        
        if self.is_approve:
            role = interaction.guild.get_role(NEWBIE_JOIN_ROLE_ID)
            if not role:
                await interaction.followup.send("서버에서 해당 ID의 역할을 찾을 수 없습니다. (ID 확인 필요)", ephemeral=True)
                return
            try: 
                await target_member.add_roles(role)
            except discord.Forbidden:
                await interaction.followup.send("**[권한 오류]** 봇이 역할을 지급할 수 없습니다!\n디스코드 `서버 설정` -> `역할`에서 **봇의 역할**을 지급하려는 역할보다 **위로 드래그**해서 올려주세요.", ephemeral=True)
                return 
            except Exception as e:
                await interaction.followup.send(f"알 수 없는 오류 발생: {e}", ephemeral=True)
                return

        try: await target_member.send(embed=embed)
        except: pass
        
        try: await interaction.channel.delete(reason="가입 상담 처리 완료")
        except: pass

class JoinAdminView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @discord.ui.button(label="가입 승인", style=discord.ButtonStyle.success)
    async def btn_approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(ADMIN_ROLE_ID):
            await interaction.response.send_message("관리자만 누를 수 있습니다.", ephemeral=True); return
        await interaction.response.send_modal(JoinProcessModal(self.target_user_id, True))
        
    @discord.ui.button(label="가입 거절", style=discord.ButtonStyle.danger)
    async def btn_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(ADMIN_ROLE_ID):
            await interaction.response.send_message("관리자만 누를 수 있습니다.", ephemeral=True); return
        await interaction.response.send_modal(JoinProcessModal(self.target_user_id, False))

# ==========================================
# [티켓 생성 및 모달 시스템]
# ==========================================
async def get_or_create_category(guild: discord.Guild, ticket_type: str):
    config = TICKET_CATEGORIES.get(ticket_type)
    if not config:
        cat = discord.utils.get(guild.categories, name="기타 문의")
        if not cat: cat = await guild.create_category("기타 문의")
        return cat
    if config["id"]:
        cat = guild.get_channel(config["id"])
        if isinstance(cat, discord.CategoryChannel): return cat
    cat = discord.utils.get(guild.categories, name=config["name"])
    if not cat: cat = await guild.create_category(config["name"])
    return cat

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="문의 닫기", style=discord.ButtonStyle.danger, custom_id="close_ticket_button_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); return
        await interaction.response.send_message(f"**이 채널은 {interaction.user.mention}님에 의해 5초 후에 삭제됩니다.**")
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="티켓 마감")

class AnonymousReportModal(discord.ui.Modal, title='익명 제보 작성'):
    report_title = discord.ui.TextInput(label='제목', required=True, max_length=50)
    report_content = discord.ui.TextInput(label='내용 (관리자만 볼 수 있습니다)', style=discord.TextStyle.paragraph, required=True, max_length=1500)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        category = await get_or_create_category(interaction.guild, "anon")
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if admin_role: overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        now_str = datetime.now(KST).strftime('%m%d-%H%M')
        try:
            channel = await category.create_text_channel(name=f"익명제보-{now_str}", overwrites=overwrites, topic="익명 제보 채널")
            embed = discord.Embed(title="새로운 익명 제보", color=0x2c3e50)
            embed.add_field(name="제목", value=self.report_title.value, inline=False)
            embed.add_field(name="내용", value=make_codeblock(self.report_content.value), inline=False)
            embed.set_footer(text="제보자의 식별 정보는 기록되지 않았습니다.")
            await channel.send(embed=embed, view=CloseTicketView())
            await interaction.followup.send("제보가 100% 익명으로 관리자에게 전달되었습니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send("채널 생성 오류가 발생했습니다.", ephemeral=True)

class TicketInputModal(discord.ui.Modal):
    def __init__(self, ticket_type: str):
        self.ticket_type = ticket_type
        titles = {
            "join": "가입 상담 폼", "qna": "문의 및 건의 폼", "comp": "불편 사항 제보 폼", "error": "오류 제보 폼",
            "ato": "아토락시온 파티 구인", "shrine": "검은사당 파티 구인", "blood": "피의제단 파티 구인"
        }
        super().__init__(title=titles.get(ticket_type, "정보 입력"))
        self.inputs = {}
        
        if ticket_type in ["ato", "shrine", "blood"]:
            self.inputs['family'] = discord.ui.TextInput(label='가문명/캐릭터명', required=True)
            self.inputs['stats'] = discord.ui.TextInput(label='공/방합계', required=True)
            self.inputs['desc'] = discord.ui.TextInput(label='신청 내용', style=discord.TextStyle.paragraph, required=True)
            self.add_item(self.inputs['family']); self.add_item(self.inputs['stats']); self.add_item(self.inputs['desc'])

        elif ticket_type == "join":
            self.inputs['family'] = discord.ui.TextInput(label='가문명', required=True)
            self.inputs['style'] = discord.ui.TextInput(label='플레이 성향 (PVP/PVE/초식)', required=True)
            self.add_item(self.inputs['family']); self.add_item(self.inputs['style'])

        elif ticket_type == "comp":
            self.inputs['target'] = discord.ui.TextInput(label='신고자(대상)', required=True)
            self.inputs['time'] = discord.ui.TextInput(label='사건 발생 시간', required=True)
            self.inputs['desc'] = discord.ui.TextInput(label='상황 설명 및 증거 (로그 요청 가능)', style=discord.TextStyle.paragraph, required=True)
            self.add_item(self.inputs['target']); self.add_item(self.inputs['time']); self.add_item(self.inputs['desc'])
            
        elif ticket_type in ["qna", "error"]:
            self.inputs['title'] = discord.ui.TextInput(label='제목', required=True)
            self.inputs['desc'] = discord.ui.TextInput(label='내용', style=discord.TextStyle.paragraph, required=True)
            self.add_item(self.inputs['title']); self.add_item(self.inputs['desc'])

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        category = await get_or_create_category(interaction.guild, self.ticket_type)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if admin_role: overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        embed = discord.Embed(color=0x2b2d31)
        view_to_attach = CloseTicketView() 
        
        if self.ticket_type == "join":
            channel_name = f"가입상담-{interaction.user.name}"
            embed.title = "가입 상담"
            embed.description = "가입 상담이 시작되었습니다. 운영진과 대화 후 가입 승인 또는 거절됩니다."
            embed.add_field(name="제목", value="가입 상담", inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="정리 기준", value="봇이 만든 임시 문의 채널만 닫기/삭제합니다.", inline=False)
            embed.add_field(name="가입 처리", value="승인 시 매핑된 일반 멤버 역할을 지급합니다.", inline=False)
            join_info = "**가문명:** " + self.inputs['family'].value + "\n**성향:** " + self.inputs['style'].value
            embed.add_field(name="제출 정보", value=join_info, inline=False)
            view_to_attach = JoinAdminView(interaction.user.id) 
            
        elif self.ticket_type == "qna":
            channel_name = f"문의건의-{interaction.user.name}"
            embed.title = "문의 / 건의"
            embed.description = "임베드 내용확인용"
            embed.add_field(name="제목", value=self.inputs['title'].value, inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="정리 기준", value="봇이 만든 임시 문의 채널만 닫기/삭제합니다.", inline=False)
            embed.add_field(name="상세 내용", value=make_codeblock(self.inputs['desc'].value), inline=False)
            
        elif self.ticket_type == "error":
            channel_name = f"오제보-{interaction.user.name}"
            embed.title = "오제보 / 젠타임 오류"
            embed.description = "오제보 내용확인"
            embed.add_field(name="제목", value=self.inputs['title'].value, inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="정리 기준", value="봇이 만든 임시 문의 채널만 닫기/삭제합니다.", inline=False)
            embed.add_field(name="상세 내용", value=make_codeblock(self.inputs['desc'].value), inline=False)
            
        elif self.ticket_type == "comp":
            channel_name = f"불편제보-{interaction.user.name}"
            embed.title = "불편 사항 제보"
            embed.description = "서버 규칙 위반이나 불편사항 제보입니다."
            embed.add_field(name="제목", value="불편 사항 제보", inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="정리 기준", value="봇이 만든 임시 문의 채널만 닫기/삭제합니다.", inline=False)
            comp_info = "**신고자/대상:** " + self.inputs['target'].value + "\n**발생 시간:** " + self.inputs['time'].value + "\n**상황 설명:**\n" + make_codeblock(self.inputs['desc'].value)
            embed.add_field(name="제출 정보", value=comp_info, inline=False)
            
        elif self.ticket_type in ["ato", "shrine", "blood"]:
            if self.ticket_type == "ato":
                channel_name = f"아토락시온-{interaction.user.name}"
                embed.title = "아토락시온 파티 신청"
                embed.add_field(name="제목", value="아토락시온 파티", inline=False)
            elif self.ticket_type == "shrine":
                channel_name = f"검은사당-{interaction.user.name}"
                embed.title = "검은사당 파티 신청"
                embed.add_field(name="제목", value="검은사당 파티", inline=False)
            elif self.ticket_type == "blood":
                channel_name = f"피의제단-{interaction.user.name}"
                embed.title = "피의제단 파티 신청"
                embed.add_field(name="제목", value="피의제단 파티", inline=False)

            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            party_info = f"**가문명/캐릭터명:** {self.inputs['family'].value}\n**공/방합계:** {self.inputs['stats'].value}\n**신청 내용:**\n" + make_codeblock(self.inputs['desc'].value)
            embed.add_field(name="제출 정보", value=party_info, inline=False)

        try:
            channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)
            await channel.send(content=interaction.user.mention, embed=embed, view=view_to_attach)
            await interaction.followup.send(f"티켓 생성이 완료되었습니다: {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send("채널 생성 오류가 발생했습니다.", ephemeral=True)

class PartyTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="아토락시온 신청", style=discord.ButtonStyle.primary, custom_id="party_ato_btn")
    async def btn_ato(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(TicketInputModal("ato"))
    @discord.ui.button(label="검은사당 신청", style=discord.ButtonStyle.primary, custom_id="party_shrine_btn")
    async def btn_shrine(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(TicketInputModal("shrine"))
    @discord.ui.button(label="피의제단 신청", style=discord.ButtonStyle.primary, custom_id="party_blood_btn")
    async def btn_blood(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(TicketInputModal("blood"))

# ==========================================
# [완전히 분리된 전용 패널 Views]
# ==========================================
class SetupJoinView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="가입 상담", style=discord.ButtonStyle.primary, custom_id="join_panel_btn")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketInputModal("join"))
    @discord.ui.button(label="축복/에다니아 알림 설정", style=discord.ButtonStyle.secondary, custom_id="status_alert_btn")
    async def btn_status_alert(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM status_alert_users WHERE user_id=?", (interaction.user.id,))
        exists = c.fetchone()
        if exists:
            c.execute("DELETE FROM status_alert_users WHERE user_id=?", (interaction.user.id,))
            await interaction.response.send_message("축복/에다니아 개인 DM 알림이 해제되었습니다.", ephemeral=True)
        else:
            c.execute("INSERT INTO status_alert_users (user_id) VALUES (?)", (interaction.user.id,))
            await interaction.response.send_message("축복/에다니아 개인 DM 알림이 설정되었습니다.", ephemeral=True)
        conn.commit(); conn.close()

class BossTimeSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Select(placeholder="알림 받을 시간대를 선택하세요", options=[
            discord.SelectOption(label="1시간 전", value="60"),
            discord.SelectOption(label="30분 전", value="30"),
            discord.SelectOption(label="10분 전", value="10"),
            discord.SelectOption(label="5분 전", value="5")
        ], custom_id="boss_time_select"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        time_val = interaction.data['values'][0]
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute("SELECT 1 FROM boss_alert_settings WHERE user_id=? AND time_str=?", (interaction.user.id, time_val))
        if c.fetchone():
            c.execute("DELETE FROM boss_alert_settings WHERE user_id=? AND time_str=?", (interaction.user.id, time_val))
            msg = f"{time_val}분 전 알림이 해제되었습니다."
        else:
            c.execute("INSERT INTO boss_alert_settings VALUES (?, ?)", (interaction.user.id, time_val))
            msg = f"{time_val}분 전 알림이 설정되었습니다."
        conn.commit(); conn.close()
        await interaction.response.send_message(msg, ephemeral=True)
        return True

class SetupBossView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="월드보스 시간", style=discord.ButtonStyle.primary, custom_id="boss_time_btn")
    async def btn_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="오늘의 월드 보스 시간표", color=0xf39c12)
        today_str = WEEKDAYS[datetime.now(KST).weekday()][0]
        embed.description = "".join([f"**{t}** : {b}\n\n" for t, b in BOSS_DB[today_str]])
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @discord.ui.button(label="알림 설정", style=discord.ButtonStyle.secondary, custom_id="boss_alert_btn")
    async def btn_alert(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="월드보스 알림 설정", description="아래에서 알림 받을 시간을 선택해주세요. (다중 선택 가능, 한 번 더 누르면 취소)", color=0x2b2d31)
        await interaction.response.send_message(embed=embed, view=BossTimeSelectView(), ephemeral=True)

class SetupUtilityView(discord.ui.LayoutView):
    def __init__(self): 
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=discord.Color(0x2b2d31))
        
        container.add_item(discord.ui.TextDisplay(content="## [편의기능]\n\n**강화 및 공/방 계산**"))
        row1 = discord.ui.ActionRow()
        row1.add_item(discord.ui.Button(label="카프라스 계산기", style=discord.ButtonStyle.success, custom_id="util_cap"))
        row1.add_item(discord.ui.Button(label="공/방 구간 계산기", style=discord.ButtonStyle.danger, custom_id="util_apdp"))
        row1.add_item(discord.ui.Button(label="포식 계산기", style=discord.ButtonStyle.primary, custom_id="util_devour"))
        row1.add_item(discord.ui.Button(label="군왕 무기 계산기", style=discord.ButtonStyle.secondary, custom_id="util_sov"))
        container.add_item(row1)

        container.add_item(discord.ui.Separator()) 
        container.add_item(discord.ui.TextDisplay(content="**펄의상 및 거래소 효율 계산**"))
        row2 = discord.ui.ActionRow()
        row2.add_item(discord.ui.Button(label="데키아 등불", style=discord.ButtonStyle.secondary, custom_id="util_dekia"))
        row2.add_item(discord.ui.Button(label="영물의 축복", style=discord.ButtonStyle.secondary, custom_id="util_bless"))
        row2.add_item(discord.ui.Button(label="펄 의상", style=discord.ButtonStyle.secondary, custom_id="util_pearl"))
        row2.add_item(discord.ui.Button(label="거래소 실수령액", style=discord.ButtonStyle.secondary, custom_id="util_tax"))
        row2.add_item(discord.ui.Button(label="아이템 평균가", style=discord.ButtonStyle.secondary, custom_id="util_avg"))
        container.add_item(row2)

        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="**기타**"))
        row3 = discord.ui.ActionRow()
        row3.add_item(discord.ui.Button(label="어둠의 틈", style=discord.ButtonStyle.secondary, custom_id="util_rift"))
        row3.add_item(discord.ui.Button(label="저격 수렵 계산기", style=discord.ButtonStyle.secondary, custom_id="util_snipe"))
        row3.add_item(discord.ui.Button(label="제작노트", style=discord.ButtonStyle.link, url="https://www.kr.playblackdesert.com/ko-KR/Wiki?wikiNo=227"))
        container.add_item(row3)
        
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = interaction.data.get("custom_id")
        if not cid: return True
        if cid == "util_cap": await interaction.response.send_modal(CaphrasModal())
        elif cid == "util_apdp": await interaction.response.send_modal(ApDpModal())
        elif cid == "util_devour": await interaction.response.send_modal(DevourModal())
        elif cid == "util_sov": 
            embed = discord.Embed(title="군왕 무기 계산기", description="부위를 선택해주세요.", color=0x2b2d31)
            await interaction.response.send_message(embed=embed, view=SovWeaponSelectView(), ephemeral=True)
        elif cid == "util_dekia":
            await interaction.response.defer(ephemeral=True)
            tasks = [get_market_price(i["id"], i["sid"]) for i in DEKIA_DB]
            results = await asyncio.gather(*tasks)
            ranking = [{"name": i["name"], "light": i["light"], "price": p, "stock": s, "unit_price": p // i["light"]} for i, (p, s, _) in zip(DEKIA_DB, results) if p > 0]
            ranking.sort(key=lambda x: x["unit_price"])
            embed = discord.Embed(title="데키아 등불 가성비 랭킹", color=0xf1c40f)
            desc = ""
            for idx, r in enumerate(ranking): desc += f"**{idx+1}. {r['name']}**\n불빛: {r['light']}개 | 재고: {r['stock']:,}개\n가격: {r['price']:,} 은화\n**불빛 1개당: `{r['unit_price']:,}` 은화**\n\n"
            embed.description = desc[:4000] if desc else "데이터를 불러오지 못했습니다."
            await interaction.followup.send(embed=embed, ephemeral=True)
        elif cid == "util_bless":
            await interaction.response.defer(ephemeral=True)
            tasks = [get_market_price(i["id"], 0) for i in BLESS_DB]
            results = await asyncio.gather(*tasks)
            ranking = [{"name": i["name"], "residue": i["residue"], "price": p, "stock": s, "unit_price": p // i["residue"]} for i, (p, s, _) in zip(BLESS_DB, results) if p > 0]
            ranking.sort(key=lambda x: x["unit_price"])
            embed = discord.Embed(title="영물의 축복 가성비 랭킹", color=0x2ecc71)
            desc = ""
            for idx, r in enumerate(ranking): desc += f"**{idx+1}. {r['name']}**\n잔재: {r['residue']}개 | 재고: {r['stock']:,}개\n가격: {r['price']:,} 은화\n**잔재 1개당: `{r['unit_price']:,}` 은화**\n\n"
            embed.description = desc[:4000] if desc else "데이터를 불러오지 못했습니다."
            await interaction.followup.send(embed=embed, ephemeral=True)
        elif cid == "util_pearl":
            embed = discord.Embed(title="펄 의상", description="조회할 시간대를 선택해주세요.", color=0x2b2d31)
            await interaction.response.send_message(embed=embed, view=PearlTimeView(), ephemeral=True)
        elif cid == "util_tax":
            embed = discord.Embed(title="거래소 실수령액 계산", description="적용 중인 버프를 선택하세요.", color=0x2b2d31)
            await interaction.response.send_message(embed=embed, view=TaxSelectView(), ephemeral=True)
        elif cid == "util_avg": await interaction.response.send_modal(AvgPriceModal())
        elif cid == "util_rift":
            embed = discord.Embed(title="어둠의 틈", description="아래 버튼을 눌러주세요", color=0x2b2d31)
            await interaction.response.send_message(embed=embed, view=DarkRiftMainView(), ephemeral=True)
        elif cid == "util_snipe": 
            embed = discord.Embed(title="저격 수렵 계산기", description="수행하려는 작업을 선택해주세요.", color=0x2b2d31)
            await interaction.response.send_message(embed=embed, view=SnipeMainView(), ephemeral=True)
        return True

class OfficialLinksView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        links = [
            ("공지사항", "https://www.kr.playblackdesert.com/ko-KR/News/Notice"),
            ("업데이트", "https://www.kr.playblackdesert.com/ko-KR/News/Update"),
            ("이벤트", "https://www.kr.playblackdesert.com/ko-KR/News/Event"),
            ("펄상점", "https://www.kr.playblackdesert.com/ko-KR/News/PearlShop"),
            ("공식 홈페이지", "https://www.kr.playblackdesert.com/"),
            ("연구소", "https://www.global-lab.playblackdesert.com/"),
            ("쿠폰 확인", "https://www.kr.playblackdesert.com/ko-KR/ItemMarket/Coupon"),
            ("최신 영상", "https://www.youtube.com/@BlackDesert_KR"),
            ("검은사막 인벤", "https://black.inven.co.kr/"),
            ("검통디", "https://discord.gg/bdo-kr")
        ]
        for idx, (label, url) in enumerate(links):
            self.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.link, url=url, row=idx//5))

class ReportTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="불편사항 제보", style=discord.ButtonStyle.danger, custom_id="comp_ticket_btn")
    async def btn_comp(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(TicketInputModal("comp"))

class AnonTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="익명 제보", style=discord.ButtonStyle.primary, custom_id="anon_ticket_btn")
    async def btn_anon(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(AnonymousReportModal())

class QnaTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="문의/건의", style=discord.ButtonStyle.primary, custom_id="qna_ticket_btn")
    async def btn_qna(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(TicketInputModal("qna"))


# ==========================================
# [자동 스케줄러: 월드 보스 & 어둠의 틈 알림]
# ==========================================
async def send_dm_to_users(users, embed):
    for (u_id,) in users:
        user = bot.get_user(u_id)
        if user:
            try:
                await user.send(embed=embed)
                await asyncio.sleep(0.1) 
            except: pass

@tasks.loop(seconds=60)
async def boss_alert_loop():
    now = datetime.now(KST)
    conn = sqlite3.connect('bdo_data.db')
    c = conn.cursor()
    
    offsets = {"60": "1시간", "30": "30분", "10": "10분", "5": "5분"}
    for offset_str, offset_label in offsets.items():
        offset_min = int(offset_str)
        target_time = now + timedelta(minutes=offset_min)
        target_weekday = WEEKDAYS[target_time.weekday()][0]
        target_time_str = target_time.strftime("%H:%M")
        
        bosses = BOSS_DB.get(target_weekday, [])
        for boss_time, boss_name in bosses:
            if target_time_str == boss_time:
                c.execute("SELECT user_id FROM boss_alert_settings WHERE time_str=?", (offset_str,))
                users = c.fetchall()
                if users:
                    embed = discord.Embed(title=f"월드 보스 출현 {offset_label} 전!", description=f"**{boss_name}** 보스가 **{boss_time}**에 출현합니다!", color=0xe74c3c)
                    bot.loop.create_task(send_dm_to_users(users, embed))
    conn.close()

@tasks.loop(seconds=60)
async def rift_alert_loop():
    now = datetime.now(KST)
    conn = sqlite3.connect('bdo_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id, boss_name, kill_time FROM rift_history")
    rows = c.fetchall()
    conn.close()
    for user_id, boss_name, kill_time_str in rows:
        try:
            kill_time = datetime.strptime(kill_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST)
            spawn_time = kill_time + timedelta(days=5)
            diff = spawn_time - now
            total_minutes = int(diff.total_seconds() // 60)
            if total_minutes == 1440:
                user = bot.get_user(user_id)
                if user:
                    try: await user.send(f"**어둠의 틈 알림**\n{boss_name} 출현까지 **1일** 남았습니다!\n예정 시간: {format_dt(spawn_time)}")
                    except: pass
            elif total_minutes == 180:
                user = bot.get_user(user_id)
                if user:
                    try: await user.send(f"**어둠의 틈 알림**\n{boss_name} 출현까지 **3시간** 남았습니다!\n예정 시간: {format_dt(spawn_time)}")
                    except: pass
        except: pass

@tasks.loop(minutes=10)
async def pearl_tracker():
    conn = sqlite3.connect('bdo_data.db')
    c = conn.cursor()
    now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    tasks_req = [get_market_price(item["id"]) for item in PEARL_OUTFIT_DB]
    results = await asyncio.gather(*tasks_req)
    for item, (_, stock, count) in zip(PEARL_OUTFIT_DB, results):
        if count > 0: c.execute("INSERT INTO pearl_history VALUES (?, ?, ?, ?)", (item["id"], now_str, count, stock))
    seven_days_ago = (datetime.now(KST) - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("DELETE FROM pearl_history WHERE timestamp < ?", (seven_days_ago,))
    conn.commit(); conn.close()

# ==========================================
# [코어 명령어 및 봇 구동]
# ==========================================
async def setup_hook():
    global ITEM_LIST
    HARDCODED = {"카프라스의 돌": 721003, "기억의 파편": 44195, "블랙스톤 (무기)": 16001, "블랙스톤 (방어구)": 16002, "뾰족한 흑결정 조각": 4998, "단단한 흑결정 조각": 4997, "크론석": 16080, "고대 정령의 가루": 721002, "데보레카 목걸이": 11653, "프리오네 반지": 705535, "프리오네 귀걸이": 705534}
    ITEM_LIST.update(HARDCODED)

    print("📥 검은사막 아이템 DB 다운로드 중...")
    try:
        url = "https://api.arsha.io/util/db/dump?lang=kr"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    data = await response.json()
                    if not isinstance(data, list) or len(data) == 0:
                        print(f"⚠️ dump 응답이 비어있거나 형식이 예상과 다릅니다. type={type(data)}")
                    else:
                        temp_list = {}
                        skipped = 0
                        for item in data:
                            name = item.get('name')
                            id_raw = item.get('id')
                            if not name or id_raw is None:
                                skipped += 1
                                continue
                            id_val = int(id_raw)
                            if name not in temp_list or id_val < temp_list[name]:
                                temp_list[name] = id_val
                        ITEM_LIST.update(temp_list)
                        with open('items_v2.json', 'w', encoding='utf-8') as f:
                            json.dump(ITEM_LIST, f, ensure_ascii=False, indent=4)
                        print(f"✅ 총 {len(ITEM_LIST)}개의 아이템 연동 완료! (dump {len(data)}건 중 {skipped}건 스킵)")
                else:
                    body_preview = (await response.text())[:300]
                    print(f"⚠️ dump API 응답 실패: status={response.status}, body={body_preview}")
                    raise RuntimeError(f"dump API status {response.status}")
    except Exception as e:
        print(f"⚠️ dump 로드 중 예외 발생: {type(e).__name__}: {e}")
        if os.path.exists('items_v2.json'):
            with open('items_v2.json', 'r', encoding='utf-8') as f:
                backup = json.load(f)
                ITEM_LIST.update(backup)
            print(f"↩️ 로컬 백업(items_v2.json) 사용: {len(backup)}개 로드됨. 현재 ITEM_LIST 총 {len(ITEM_LIST)}개")
        else:
            print("❌ 로컬 백업(items_v2.json)도 없어서 HARDCODED 9개만 사용 중입니다.")

    bot.add_view(SetupJoinView())
    bot.add_view(SetupBossView())
    bot.add_view(BossTimeSelectView())
    bot.add_view(SetupUtilityView())
    bot.add_view(ReportTicketView())
    bot.add_view(AnonTicketView())
    bot.add_view(QnaTicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(StatusViewPanel("blessing", "영물의 축복"))
    bot.add_view(StatusViewPanel("edana", "에다니아"))
    bot.add_view(PartyTicketView())
    bot.add_view(BdoTimeView())
    await bot.tree.sync()

bot.setup_hook = setup_hook

# 채널별 설치 명령어들
@bot.tree.command(name="설치-권한설정", description="권한설정 및 가입 채널용 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_join(interaction: discord.Interaction):
    embed = discord.Embed(title="가입 상담 및 알림 설정", description="가입 티켓 생성 및 유용한 알림(축복/에다니아)을 켜고 끌 수 있습니다.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=SetupJoinView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-필드보스", description="필드보스 채널용 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_boss(interaction: discord.Interaction):
    embed = discord.Embed(title="월드보스 시간표", description="월드보스 출현 일정 조회 및 개인 DM 알림 설정을 제공합니다.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=SetupBossView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-편의기능", description="편의기능 채널용 전체 버튼 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_util(interaction: discord.Interaction):
    await interaction.channel.send(content=None, embed=None, view=SetupUtilityView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-공홈정보", description="검은사막 공식 홈페이지 링크 모음 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_links(interaction: discord.Interaction):
    embed = discord.Embed(title="검은사막 홈페이지", description="검은사막 주요 안내 링크입니다.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=OfficialLinksView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-축복제보", description="영물의 축복 제보 채널용 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_bless(interaction: discord.Interaction):
    embed = discord.Embed(title="영물의 축복 현황", description="하단 버튼을 통해 새로운 위치를 제보하거나 현황을 확인하세요.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=StatusViewPanel("blessing", "영물의 축복"))
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-에다니아제보", description="에다니아 제보 채널용 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_edana(interaction: discord.Interaction):
    embed = discord.Embed(title="에다니아 현황", description="하단 버튼을 통해 새로운 위치를 제보하거나 현황을 확인하세요.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=StatusViewPanel("edana", "에다니아"))
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-불편사항", description="불편사항 제보용 티켓 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_comp(interaction: discord.Interaction):
    embed = discord.Embed(title="불편사항 제보", description="서버 규칙 위반 및 불편사항을 제보해주세요.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=ReportTicketView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-익명제보", description="익명 제보용 티켓 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_anon(interaction: discord.Interaction):
    embed = discord.Embed(title="익명 제보", description="이 버튼을 통해 남긴 제보는 작성자를 숨긴 채 관리자에게만 전달됩니다.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=AnonTicketView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-건의사항", description="문의 및 건의용 티켓 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_qna(interaction: discord.Interaction):
    embed = discord.Embed(title="문의 및 건의", description="서버 발전을 위한 아이디어나 궁금한 점을 남겨주세요.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=QnaTicketView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-파티구인", description="파티 구인(아토락시온, 검은사당, 피의제단) 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_party(interaction: discord.Interaction):
    embed = discord.Embed(title="파티 구인", description="아토락시온, 검은사당, 피의제단 파티를 구인합니다.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=PartyTicketView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

@bot.tree.command(name="설치-인게임시간", description="검은사막 인게임 시간 확인 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_bdo_time(interaction: discord.Interaction):
    embed = discord.Embed(title="검은사막 인게임시간", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=BdoTimeView())
    await interaction.response.send_message("인게임 시간 패널 설치 완료", ephemeral=True)

@bot.tree.command(name="아이템디버그", description="[관리자] ITEM_LIST에 등록된 실제 이름/ID를 검색합니다")
@discord.app_commands.default_permissions(administrator=True)
async def debug_item_list(interaction: discord.Interaction, 키워드: str):
    await interaction.response.defer(ephemeral=True)
    if not ITEM_LIST:
        await interaction.followup.send("ITEM_LIST가 아직 로드되지 않았습니다.", ephemeral=True); return

    key = 키워드.replace(" ", "")
    # 1) 부분일치 전부
    exact_hits = [(n, i) for n, i in ITEM_LIST.items() if key in n.replace(" ", "")]
    # 2) fuzzy 매칭 (컷오프 없이 점수 그대로 보여줌, 디버그용)
    fuzzy_hits = process.extractBests(키워드, ITEM_LIST.keys(), limit=10)

    lines = [f"🔎 `{키워드}` 검색 결과 (ITEM_LIST 총 {len(ITEM_LIST)}개)\n"]
    lines.append(f"**부분일치: {len(exact_hits)}건**")
    for n, i in exact_hits[:15]:
        lines.append(f"  - `{n}` → id={i}")
    if not exact_hits:
        lines.append("  (없음)")

    lines.append(f"\n**유사도 매칭 (thefuzz, 컷오프 없음, 상위 10개)**")
    for n, score in fuzzy_hits:
        lines.append(f"  - `{n}` ({score}점) → id={ITEM_LIST[n]}")

    text = "\n".join(lines)
    if len(text) > 1900: text = text[:1900] + "\n...(생략)"
    await interaction.followup.send(make_codeblock(text), ephemeral=True)

# ==========================================
# [신규 유저 자동 DM 환영 시스템]
# ==========================================
@bot.event
async def on_member_join(member):
    if member.bot: return
    embed = discord.Embed(
        title="시나모롤 길드에 오신 것을 환영합니다!",
        description="안녕하세요, " + member.mention + "님!\n우리 길드에 오신 것을 진심으로 환영합니다.", color=0x87CEEB
    )
    embed.add_field(name="시나모롤 길드 가입 안내", value="저희 길드는 편안한 분위기 속에서 함께 성장하는 길드를 지향합니다.", inline=False)
    embed.add_field(name="길드 레이드 및 콘텐츠", value="• **매일 밤 21시 진행**\n• 검은사당, 아토락시온, 피의 제단 등 콘텐츠는 **신청제**로 운영하고 있습니다.", inline=False)
    embed.add_field(name="디스코드", value="다양한 자체 제작 봇과 편의 기능을 제공하고 있습니다. 디스코드 참여를 적극 권장드립니다.", inline=False)
    embed.add_field(name="뉴비/복귀 유저 지원", value="\"메인퀘 밀어주세요\", \"성장하세요\" 같은 뻔한 안내만 하지 않습니다.\n\n길드장이 직접 일정 조율 후 **1:1로 성장 방향, 장비 세팅, 콘텐츠 진입** 등을 도와드립니다.\n검은사막 적응부터 뉴비 탈출까지 함께합니다!", inline=False)
    if member.display_avatar: embed.set_thumbnail(url=member.display_avatar.url)
    try: await member.send(embed=embed)
    except: pass

@bot.event
async def on_ready():
    init_db()
    if not boss_alert_loop.is_running(): boss_alert_loop.start()
    if not rift_alert_loop.is_running(): rift_alert_loop.start()
    if not pearl_tracker.is_running(): pearl_tracker.start()
    await bot.change_presence(activity=discord.Game("시나모롤 길드 도우미 V2"))
    print(f'시나모롤 V2 봇 로그인 성공: {bot.user.name}')

bot.run('111')