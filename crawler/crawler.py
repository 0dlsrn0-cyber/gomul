#!/usr/bin/env python3
"""
고물시세 크롤러 — 매일 새벽 6시(KST) GitHub Actions에서 자동 실행.

데이터 흐름:
  1. crawler/manual_prices.json (가족 직접 입력값)
  2. crawler/sources/allmetal.py (한국 실시세 - 메인)
  3. crawler/sources/directscrap.py (한국 실시세 - 백업)
  4. crawler/sources/nonferrous.py (한국비철금속협회 LME, USD/톤)
  5. yfinance (환율 + 귀금속)
  6. 폴백 기본값

품목별 우선순위로 머지해서 data.json 생성.

[신뢰성 원칙 — 차트/숫자가 거짓말하지 않게]
  - history(차트용)에는 '실제로 관측된 매입가'(수동·올메탈·다이렉트스크랩)만 누적한다.
    LME×비율 추정이나 폴백 기본값은 오늘 표시값(gwangju)으로만 쓰고 history엔 쌓지 않는다.
  - 전일비(change)는 직전 관측치와 '같은 소스'일 때만 계산한다
    (소스 전환 allmetal↔directscrap 으로 인한 가짜 급등락 방지).
  - 과거 가격을 난수로 지어내지 않는다(예전 estimate_history 삭제). 실측이 하루씩 쌓인다.
  - 각 품목에 priceSource / priceEstimated / rawSource 를 기록해 출처를 투명하게 남긴다.
  - 발행은 항상 한다(soft error는 status에 담아 앱 배너로 노출). 알림은 워크플로가 처리.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------- 경로 ----------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_FILE = REPO_ROOT / "data.json"
MANUAL_FILE = SCRIPT_DIR / "manual_prices.json"

# Windows 콘솔(cp949)에서도 한글·기호 로그가 깨지지 않게 stdout/stderr를 UTF-8로
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# 모듈 import 경로 셋업
sys.path.insert(0, str(SCRIPT_DIR))
from sources import allmetal, directscrap, nonferrous  # noqa: E402

# ---------- 시간 ----------
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
TODAY_STR = NOW.strftime("%Y-%m-%d")
NOW_ISO = NOW.isoformat(timespec="seconds")

# ---------- 단위 환산 상수 ----------
LB_TO_KG = 0.45359237
OZ_TO_KG = 0.0311034768  # troy ounce

# ---------- 신뢰성 정책 상수 ----------
HISTORY_MAX = 90
# '실제로 관측된 매입가'로 인정하는 소스 (이것만 history에 누적)
OBSERVED_SOURCES = {"수동", "올메탈", "다이렉트스크랩"}
PRECIOUS_KEYS = {"gold", "silver", "platinum", "palladium"}


# ============================================================
#  Yahoo Finance: 환율 + 귀금속
# ============================================================
def fetch_yahoo() -> tuple[dict[str, float], set[str]]:
    """환율(USD/KRW) + 귀금속(금/은/백금/팔라듐).

    Returns:
        (values, fallback_keys)
        fallback_keys: 실시세를 못 받아 폴백 상수로 채운 key 집합 (정확도 표시용).
    """

    fallbacks = {
        "usd_krw":     1400.0,
        "gold_oz":     2400.0,
        "silver_oz":   30.0,
        "platinum_oz": 1000.0,
        "palladium_oz":950.0,
    }
    tickers = {
        "usd_krw":     "KRW=X",
        "gold_oz":     "GC=F",
        "silver_oz":   "SI=F",
        "platinum_oz": "PL=F",
        "palladium_oz":"PA=F",
    }

    try:
        import yfinance as yf
    except ImportError:
        print("  ! yfinance 미설치 — 전부 폴백 사용")
        return fallbacks.copy(), set(fallbacks.keys())

    out: dict[str, float] = {}
    fb_keys: set[str] = set()
    for key, ticker in tickers.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if hist.empty:
                raise RuntimeError("empty history")
            out[key] = float(hist["Close"].iloc[-1])
            print(f"    ✓ {ticker:8s} → {out[key]:,.4f}")
        except Exception as e:
            out[key] = fallbacks[key]
            fb_keys.add(key)
            print(f"    ✗ {ticker:8s} FALLBACK {out[key]} ({e})")
    return out, fb_keys


def usd_per_ton_to_krw_per_kg(usd_ton: float, usd_krw: float) -> int:
    """USD/톤 → KRW/kg."""
    return int(round(usd_ton * usd_krw / 1000))


def usd_per_oz_to_krw_per_kg(usd_oz: float, usd_krw: float) -> int:
    """USD/troy oz → KRW/kg."""
    return int(round(usd_oz * usd_krw / OZ_TO_KG))


# ============================================================
#  품목 정의 (31종)
# ============================================================
# 컬럼: id, name, subtitle, category, color_from, color_to, symbol,
#        lme_base (LME에서 매핑할 금속명 또는 None),
#        lme_ratio (LME × ratio = 한국 매입가 추정 비율),
#        fallback_gwangju
ITEM_RULES = [
    # ---- 동(銅) 계열 (10) ----
    ("copper-a",    "구리 상",      "1A · 깨끗한 동",       "동(銅) 계열",    "#F0A95C", "#8B4513", "Cu+",  "copper",   0.92,  17700),
    ("copper-b",    "구리 중",      "2A · 약간 산화",       "동(銅) 계열",    "#D69150", "#6B3410", "Cu",   "copper",   0.86,  16800),
    ("copper-c",    "구리 하",      "3A · 산화/혼입",       "동(銅) 계열",    "#A87040", "#4A2410", "Cu-",  "copper",   0.81,  15700),
    ("wire-hv-a",   "고압선 A",     "고압 케이블 A급",      "동(銅) 계열",    "#E5B47A", "#8C5520", "高+",  "copper",   0.66,  12800),
    ("wire-hv-b",   "고압선 B",     "고압 케이블 B급",      "동(銅) 계열",    "#D5A065", "#7A4515", "高",   "copper",   0.59,  11500),
    ("wire-bare",   "나동선",       "단선 · 피복 없는 동선",  "동(銅) 계열",    "#E2A55C", "#7A3D11", "線+",  "copper",   0.53,  10400),
    ("wire-comm",   "통신선",       "통신·전화 케이블",     "동(銅) 계열",    "#C28855", "#5A3010", "通",   "copper",   0.31,  6000),
    ("wire-medium", "중선",         "중간 등급 피복선",     "동(銅) 계열",    "#B5814A", "#4F2A12", "中",   "copper",   0.30,  5900),
    ("wire-coated", "피복선",       "잡선 · 일반 피복선",   "동(銅) 계열",    "#B07845", "#3A2818", "線",   "copper",   0.20,  3800),
    ("motor",       "모터·컴프레서","동권선 함유 복합",     "동(銅) 계열",    "#8B6B40", "#2A1810", "電",   "copper",   0.045, 870),

    # ---- 알루미늄 계열 (5) ----
    ("al-profile",  "AL 프로파일",  "압출재 · 일반 산업용", "알루미늄 계열",  "#E0E5EA", "#7B8794", "型",   "aluminum", 0.71,  3800),
    ("al-plate",    "AL 판재",      "판형 알루미늄",        "알루미늄 계열",  "#D6DCE2", "#76828F", "板",   "aluminum", 0.69,  3700),
    ("al-frame",    "AL 샤시",      "창틀 압출재",          "알루미늄 계열",  "#D6D9DE", "#7B8794", "窓",   "aluminum", 0.67,  3600),
    ("al-cast",     "AL 주물",      "주조용 알루미늄",      "알루미늄 계열",  "#C5CCD5", "#6A7785", "鑄",   "aluminum", 0.50,  2700),
    ("al-powder",   "AL 분철",      "가공 부산물 · 칩",     "알루미늄 계열",  "#B8C0CA", "#5C6573", "粉",   "aluminum", 0.43,  2300),

    # ---- 철(鐵) 계열 (3) ----
    ("iron-heavy",  "철 중량",      "두꺼운 철 · 6mm 이상", "철(鐵) 계열",    "#8A95A5", "#3F4857", "Fe+",  None,        None,   320),
    ("iron-light",  "철 경량",      "얇은 철 · 6mm 미만",   "철(鐵) 계열",    "#A0AAB8", "#5C6573", "Fe-",  None,        None,   300),
    ("iron-misc",   "잡철",         "生鐵 · 혼합 철물",     "철(鐵) 계열",    "#6B7280", "#242A34", "雜",   None,        None,   380),

    # ---- 일반 비철 (6) ----
    ("stainless",       "스테인리스",   "STS 304",             "일반 비철",      "#C9D2DC", "#5A6676", "SS",   None,        None,   1600),
    ("brass",           "황동(신주)",   "절봉 · Cu-Zn 절삭용", "일반 비철",      "#E8C275", "#8B6914", "Br",   "copper",    0.55,   10600),
    ("brass-cast",      "황동 주물",    "주조용 · Cu-Zn",      "일반 비철",      "#C9A55A", "#6F4E10", "鑄",   "copper",    0.52,   10200),
    ("phosphor-bronze", "인청동(주석)", "Cu-Sn · 청동 합금",   "일반 비철",      "#B5814E", "#4A2D14", "靑",   "copper",    0.89,   17400),
    ("nickel-silver",   "양은",         "양백 · Cu-Ni-Zn",     "일반 비철",      "#D8DDE3", "#7B8590", "洋",   "copper",    0.55,   10700),
    ("lead",            "납",           "Pb · 일반 납",        "일반 비철",      "#6E7785", "#2A313C", "Pb",   "lead",      0.55,   1500),
    ("car-battery",     "자동차 배터리","납축전지 · 액 포함",  "일반 비철",      "#8FBF7F", "#2D5A1F", "蓄",   "lead",      0.23,   650),

    # ---- 기타 비철금속 (6) ----
    ("silver",      "은",           "Ag · 순은 (kg 환산)",  "기타 비철금속",  "#F0F4F9", "#8E9AA6", "Ag",   "silver",    0.90,   1270000),
    ("gold",        "금",           "Au · 순금 (kg 환산)",  "기타 비철금속",  "#FFD700", "#8B6914", "Au",   "gold",      0.97,   137500000),
    ("zinc",        "아연",         "Zn · 함석",            "기타 비철금속",  "#A8B5C5", "#4A5868", "Zn",   "zinc",      0.55,   2800),
    ("nickel",      "니켈",         "Ni · 산업급",          "기타 비철금속",  "#B5C9B0", "#567252", "Ni",   "nickel",    0.85,   23000),
    ("platinum",    "백금",         "Pt · 촉매·보석",       "기타 비철금속",  "#E8E8EC", "#9CA3AF", "Pt",   "platinum",  0.96,   30800000),
    ("palladium",   "팔라듐",       "Pd · 촉매변환기",      "기타 비철금속",  "#D8D9E0", "#7A8090", "Pd",   "palladium", 0.94,   28300000),
]


# ============================================================
#  헬퍼
# ============================================================
def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ! {path.name} 로드 실패 ({e})")
        return {}


def lme_to_krw_kg(
    lme_usd_ton: dict, yahoo: dict, yahoo_fb_keys: set[str], nonferrous_ok: bool
) -> tuple[dict[str, int], set[str]]:
    """USD/톤·oz 가격을 KRW/kg으로 변환.

    Returns:
        (lme_krw, real_keys)
        real_keys: 폴백이 아닌 '진짜 실시세'로 환산된 metal key 집합
                   (raw 출처 'LME' vs '추정' 판정에 사용).
    """
    krw = yahoo.get("usd_krw", 1400.0)
    krw_is_fb = "usd_krw" in yahoo_fb_keys
    out: dict[str, int] = {}
    real: set[str] = set()

    # 비철 6종 (한국비철금속협회) — USD/톤
    for key, usd_ton in lme_usd_ton.items():
        out[key] = usd_per_ton_to_krw_per_kg(usd_ton, krw)
        if nonferrous_ok and not krw_is_fb:
            real.add(key)

    # 귀금속 (yfinance) — USD/oz
    oz_map = {
        "gold": "gold_oz", "silver": "silver_oz",
        "platinum": "platinum_oz", "palladium": "palladium_oz",
    }
    for metal, oz_key in oz_map.items():
        if oz_key in yahoo:
            out[metal] = usd_per_oz_to_krw_per_kg(yahoo[oz_key], krw)
            if oz_key not in yahoo_fb_keys and not krw_is_fb:
                real.add(metal)
    return out, real


# ============================================================
#  메인
# ============================================================
def main() -> int:
    print(f"=== 고물시세 크롤러 시작 {NOW_ISO} ===\n")

    # status 트래킹
    warnings: list[str] = []
    errors: list[str] = []

    # ---- 1. 한국 시세 (메인 — 올메탈) ----
    print("[1/6] 올메탈 (allmetal.co.kr) — 메인")
    allmetal_res = allmetal.fetch()
    allmetal_prices = allmetal_res.get("prices", {}) or {}

    # 게시글 노후화 체크
    post_date_str = allmetal_res.get("post_date")
    post_age_days: Optional[int] = None
    if post_date_str:
        try:
            pd = datetime.fromisoformat(post_date_str).date()
            post_age_days = (NOW.date() - pd).days
            print(f"   → {len(allmetal_prices)}종, 작성일 {post_date_str} ({post_age_days}일 전)\n")
        except Exception:
            print(f"   → {len(allmetal_prices)}종, 작성일 파싱 실패\n")
    else:
        print(f"   → {len(allmetal_prices)}종 (작성일 모름)\n")

    # ---- 2. 한국 시세 (백업 — 다이렉트스크랩) ----
    print("[2/6] 다이렉트스크랩 (directscrap.co.kr) — 백업")
    directscrap_res = directscrap.fetch()
    directscrap_prices = directscrap_res.get("prices", {}) or {}
    ds_date = directscrap_res.get("data_date")
    print(f"   → {len(directscrap_prices)}종, 기준일 {ds_date or '?'}\n")

    # ---- 한국 시세 머지 (allmetal 우선, 빈 자리만 directscrap) ----
    korean_prices: dict[str, dict] = {}
    for item_id, info in directscrap_prices.items():
        korean_prices[item_id] = info  # 백업 먼저
    for item_id, info in allmetal_prices.items():
        korean_prices[item_id] = info  # 메인이 덮어씀

    # ---- 한국 시세 상태 판정 ----
    if not allmetal_res.get("ok") and not directscrap_res.get("ok"):
        errors.append(
            f"한국 시세 수집 완전 실패 — 올메탈: {allmetal_res.get('error', '?')} / "
            f"다이렉트스크랩: {directscrap_res.get('error', '?')}"
        )
    elif not allmetal_res.get("ok"):
        warnings.append(
            f"올메탈 fetch 실패 → 다이렉트스크랩 백업 {len(directscrap_prices)}종 사용 중"
        )
    elif not directscrap_res.get("ok"):
        warnings.append(
            f"다이렉트스크랩 백업 fetch 실패 (메인 정상): {directscrap_res.get('error', '?')}"
        )

    # 올메탈 매칭 부족 / 노후화 경고
    if allmetal_res.get("ok") and len(allmetal_prices) < 8:
        warnings.append(f"올메탈 매칭 {len(allmetal_prices)}종 (예상 12+종, 파서 점검 권장)")
    if post_age_days is not None:
        if post_age_days >= 14:
            errors.append(f"올메탈 게시글 {post_age_days}일 묵음 (마지막: {post_date_str})")
        elif post_age_days >= 7:
            warnings.append(f"올메탈 게시글 {post_age_days}일 묵음 (마지막: {post_date_str})")
    elif allmetal_res.get("ok"):
        # 작성일을 못 읽으면 노후화 가드가 작동 못 하므로 명시적으로 경고
        warnings.append("올메탈 게시글 작성일 파싱 실패 — 노후화 감지 불가")

    if not korean_prices and not errors:
        errors.append("한국 시세 매칭 0종 — 양쪽 파서 모두 실패")

    print(f"   ★ 머지 결과: {len(korean_prices)}종 (allmetal {len(allmetal_prices)} + directscrap {len(directscrap_prices)})\n")

    # ---- 3. 한국비철금속협회 LME ----
    print("[3/6] 한국비철금속협회 LME (USD/톤)")
    nonferrous_res = nonferrous.fetch()
    lme_usd_ton = nonferrous_res.get("prices", {}) or {}
    if not nonferrous_res.get("ok"):
        warnings.append(f"한국비철금속협회 fetch 실패: {nonferrous_res.get('error', '?')}")
    print(f"   → {len(lme_usd_ton)}종, 기준일 {nonferrous_res.get('data_date', '?')}\n")

    # ---- 4. yfinance (환율 + 귀금속) ----
    print("[4/6] Yahoo Finance (환율 + 귀금속)")
    yahoo, yahoo_fb_keys = fetch_yahoo()
    print(f"   → USD/KRW = {yahoo['usd_krw']:,.2f}\n")
    if "usd_krw" in yahoo_fb_keys:
        warnings.append("환율(USD/KRW) yfinance 폴백 사용 — 환산값 정확도 낮음")
    precious_fb = sorted(k.replace("_oz", "") for k in yahoo_fb_keys if k != "usd_krw")
    if precious_fb:
        warnings.append(f"귀금속 시세 yfinance 폴백 사용: {', '.join(precious_fb)} — 추정값")

    # 통합 LME (KRW/kg) 사전 + '진짜 실시세' key 집합
    lme_krw, lme_real_keys = lme_to_krw_kg(
        lme_usd_ton, yahoo, yahoo_fb_keys, nonferrous_res.get("ok", False)
    )
    print("   LME 환산 KRW/kg:")
    for k, v in lme_krw.items():
        tag = "" if k in lme_real_keys else " (추정)"
        print(f"      {k:9s}: {v:>15,}{tag}")
    print()

    # ---- 5. 수동 입력 ----
    print("[5/6] manual_prices.json")
    manual_root = load_json(MANUAL_FILE)
    manual_items = manual_root.get("items", {})
    print(f"   → 수동 {len(manual_items)}종\n")

    # ---- 6. 이전 data.json (history 누적) ----
    print("[6/6] 이전 data.json (history 누적용)")
    prev_root = load_json(OUTPUT_FILE)
    prev_items_by_id = {it["id"]: it for it in prev_root.get("items", [])}
    prev_is_legacy = bool(prev_items_by_id) and not any(
        isinstance(it.get("historySource"), list) for it in prev_items_by_id.values()
    )
    if prev_is_legacy:
        print("   ⚠ 이전 data.json이 구 스키마(합성 history 포함) — 정직 리셋: 실측만 새로 누적\n")
    else:
        print(f"   → 이전 {len(prev_items_by_id)}종\n")

    # ============================================================
    #  품목 빌드 — 우선순위로 머지
    # ============================================================
    print("─" * 60)
    print("품목 빌드 (우선순위: 수동 > 올메탈 > 다이렉트스크랩 > LME×비율(추정) > 폴백)")
    print("─" * 60)

    out_items: list[dict] = []
    estimated_items: list[str] = []

    for rule in ITEM_RULES:
        (item_id, name, sub, cat, c1, c2, sym,
         lme_base, lme_ratio, fb_gwangju) = rule

        man = manual_items.get(item_id, {}) or {}
        kor = korean_prices.get(item_id) or {}

        # ---- 매입가(gwangju) + 소스 결정 ----
        if isinstance(man.get("gwangju"), (int, float)):
            gwangju = int(man["gwangju"])
            price_source = "수동"
        elif kor.get("price"):
            gwangju = int(kor["price"])
            price_source = "올메탈" if kor.get("src") == "allmetal" else "다이렉트스크랩"
        elif lme_base and lme_base in lme_krw and lme_ratio is not None:
            gwangju = int(round(lme_krw[lme_base] * lme_ratio))
            price_source = "LME추정"
        else:
            gwangju = fb_gwangju
            price_source = "폴백"

        # priceEstimated(추정 배지): '관측된 한국 매입가'가 아니면 True.
        #   LME×비율은 실제 LME가 진짜여도 '매입가 추정'이므로 배지를 단다.
        price_estimated = price_source not in OBSERVED_SOURCES
        if price_estimated:
            estimated_items.append(item_id)

        # price_real_basis(차트 누적 가능 여부): 오늘 값이 '실제 데이터'에 근거하는가.
        #   관측 매입가 + (진짜 LME/시세에 근거한) LME추정 → 누적 가능.
        #   하드코딩 폴백, 또는 입력이 폴백인 LME추정 → 누적 안 함(차트 오염 방지).
        if price_source in OBSERVED_SOURCES:
            price_real_basis = True
        elif price_source == "LME추정":
            price_real_basis = lme_base in lme_real_keys
        else:  # 폴백
            price_real_basis = False

        # ---- 원청(raw) + 출처 ----
        if lme_base and lme_base in lme_krw:
            raw = int(lme_krw[lme_base])
            raw_source = "LME" if lme_base in lme_real_keys else "추정"
        else:
            # 비LME 품목: 진짜 도매가가 없으므로 매입가에 8% 얹은 참고 추정치
            raw = int(round(gwangju * 1.08))
            raw_source = "추정"

        # ---- history (실측만 누적; 구 스키마면 리셋) ----
        prev = prev_items_by_id.get(item_id)
        if prev and isinstance(prev.get("historySource"), list):
            # 손상된(직접 편집/부분 쓰기) prev 항목이 크롤러를 죽이지 않도록 방어적으로 복원.
            # 잘못된 원소는 버려서 '항상 발행' 보장을 유지(최악의 경우 빈 배열로 self-heal).
            history = [int(x) for x in (prev.get("history") or []) if isinstance(x, (int, float))]
            hist_dates = [str(d) for d in (prev.get("historyDates") or []) if d is not None]
            hist_src = [str(s) for s in (prev.get("historySource") or []) if s is not None]
        else:
            history, hist_dates, hist_src = [], [], []

        # 세 배열 길이 정합성 방어 (꼬였으면 짧은 쪽 기준으로 자름)
        n = min(len(history), len(hist_dates), len(hist_src))
        history, hist_dates, hist_src = history[-n:], hist_dates[-n:], hist_src[-n:]

        # 실제 데이터 근거가 있을 때만 누적. 같은 날 재실행이면 마지막 점을 갱신(중복 방지).
        if price_real_basis:
            if hist_dates and hist_dates[-1] == TODAY_STR:
                history[-1], hist_src[-1] = gwangju, price_source
            else:
                history.append(gwangju)
                hist_dates.append(TODAY_STR)
                hist_src.append(price_source)
            history = history[-HISTORY_MAX:]
            hist_dates = hist_dates[-HISTORY_MAX:]
            hist_src = hist_src[-HISTORY_MAX:]

        # ---- 전일비(change) — 오늘이 실측 누적된 날 + 같은 소스 연속일 때만 ----
        # 추정/폴백이라 오늘 누적 안 한 날은 history[-1]이 어제 값이라 오늘 표시값과 안 맞음 → 0(보합).
        if price_real_basis and len(history) >= 2 and history[-2] > 0 and hist_src[-1] == hist_src[-2]:
            change_pct = round((history[-1] - history[-2]) / history[-2] * 100, 1)
        else:
            change_pct = 0.0

        out_item = {
            "id": item_id,
            "name": name,
            "subtitle": sub,
            "category": cat,
            "symbol": sym,
            "colorFrom": c1,
            "colorTo": c2,
            "unit": "원/kg",
            "raw": raw,
            "rawSource": raw_source,
            "change": change_pct,
            "gwangju": gwangju,
            "priceSource": price_source,
            "priceEstimated": price_estimated,
            "defaultMargin": 0.80,
            "history": history,
            "historyDates": hist_dates,
            "historySource": hist_src,
        }
        # 부가 필드는 '수동 입력이 있을 때만' 유지 — 가짜 업체/지역 생성 금지
        for k in ("scrapAvg", "scrapMin", "scrapMax", "vendors"):
            if k in man:
                out_item[k] = man[k]

        out_items.append(out_item)
        flag = " ⚠추정" if price_estimated else ""
        print(f"  {name:14s} {gwangju:>13,} 원/kg ({change_pct:+.1f}%)  ← {price_source}{flag}")

    # ---- 저장 ----
    overall_ok = len(errors) == 0
    output = {
        "today": TODAY_STR,
        "generated_at": NOW_ISO,
        "schema": 2,
        "status": {
            "ok": overall_ok,
            "warnings": warnings,
            "errors": errors,
            "estimated_items": estimated_items,
        },
        "source": {
            "usd_krw": yahoo.get("usd_krw"),
            "usd_krw_fallback": "usd_krw" in yahoo_fb_keys,
            "allmetal_ok": allmetal_res.get("ok", False),
            "allmetal_count": len(allmetal_prices),
            "allmetal_post_date": post_date_str,
            "allmetal_post_age_days": post_age_days,
            "directscrap_ok": directscrap_res.get("ok", False),
            "directscrap_count": len(directscrap_prices),
            "directscrap_data_date": directscrap_res.get("data_date"),
            "korean_merged_count": len(korean_prices),
            "nonferrous_ok": nonferrous_res.get("ok", False),
            "nonferrous_count": len(lme_usd_ton),
            "nonferrous_data_date": nonferrous_res.get("data_date"),
            "manual_count": len(manual_items),
        },
        "items": out_items,
    }

    try:
        OUTPUT_FILE.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        # 파일을 못 쓰면 발행할 데이터가 없음 → 하드 실패
        print(f"\n❌ data.json 쓰기 실패: {e}")
        return 2

    print(f"\n✅ {OUTPUT_FILE.relative_to(REPO_ROOT)} 작성 ({len(out_items)}종, 추정 {len(estimated_items)}종)")
    print()
    print("─" * 60)
    if errors:
        print("❌ 오류:")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print("⚠️  경고:")
        for w in warnings:
            print(f"  - {w}")
    if not errors and not warnings:
        print("✅ 모든 소스 정상")
    print("─" * 60)
    print()

    # data.json은 soft error가 있어도 항상 발행한다(앱 배너가 status.errors를 보여줌).
    # 워크플로의 별도 단계가 status.errors/warnings를 읽어 알림(이슈)을 처리한다.
    # 여기서는 '파일을 못 쓴 하드 실패'(return 2)만 비정상 종료로 본다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
