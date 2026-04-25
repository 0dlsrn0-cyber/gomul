#!/usr/bin/env python3
"""
고물시세 크롤러 — 매일 새벽 6시(KST) GitHub Actions에서 자동 실행.

데이터 흐름:
  1. crawler/manual_prices.json (가족 직접 입력값)
  2. crawler/sources/allmetal.py (한국 실시세 - 메인)
  3. crawler/sources/nonferrous.py (한국비철금속협회 LME, USD/톤)
  4. yfinance (환율 + 귀금속)
  5. 폴백 기본값

품목별 우선순위로 머지해서 data.json 생성.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------- 경로 ----------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_FILE = REPO_ROOT / "data.json"
MANUAL_FILE = SCRIPT_DIR / "manual_prices.json"

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


# ============================================================
#  Yahoo Finance: 환율 + 귀금속
# ============================================================
def fetch_yahoo() -> dict[str, float]:
    """환율(USD/KRW) + 귀금속(금/은/백금/팔라듐)."""

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
        print("  ! yfinance 미설치 — 폴백 사용")
        return fallbacks.copy()

    out: dict[str, float] = {}
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
            print(f"    ✗ {ticker:8s} FALLBACK {out[key]} ({e})")
    return out


def usd_per_ton_to_krw_per_kg(usd_ton: float, usd_krw: float) -> int:
    """USD/톤 → KRW/kg."""
    return int(round(usd_ton * usd_krw / 1000))


def usd_per_oz_to_krw_per_kg(usd_oz: float, usd_krw: float) -> int:
    """USD/troy oz → KRW/kg."""
    return int(round(usd_oz * usd_krw / OZ_TO_KG))


# ============================================================
#  품목 정의 (20종)
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
def stable_seed(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % 10**8


def estimate_history(current_price: float, days: int = 90,
                     volatility: float = 0.012, seed: int = 42) -> list[int]:
    rng = random.Random(seed)
    history = [int(round(current_price))]
    for _ in range(days - 1):
        drift = (rng.random() - 0.5) * volatility * 2
        prev = history[-1] / (1 + drift)
        history.append(int(round(prev)))
    history.reverse()
    history[-1] = int(round(current_price))
    return history


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ! {path.name} 로드 실패 ({e})")
        return {}


def vendors_default(gwangju: int) -> list[dict]:
    """광주 가상 업체 4곳 — 데이터 구조 유지용 (UI는 더 이상 표시 안 함)."""
    return [
        {"name": "대성자원 (서구 금호동)",   "price": int(round(gwangju * 1.012))},
        {"name": "상록재활용 (북구 운암동)", "price": int(round(gwangju * 1.004))},
        {"name": "동양자원 (광산구 송정동)", "price": int(round(gwangju * 0.992))},
        {"name": "중앙상회 (남구 봉선동)",   "price": int(round(gwangju * 0.978))},
    ]


def lme_to_krw_kg(lme_usd_ton: dict, yahoo: dict) -> dict[str, int]:
    """nonferrous에서 받은 USD/톤 가격을 KRW/kg으로 변환."""
    krw = yahoo.get("usd_krw", 1400.0)
    out = {}
    for key, usd_ton in lme_usd_ton.items():
        out[key] = usd_per_ton_to_krw_per_kg(usd_ton, krw)
    # 귀금속 (yfinance에서)
    if "gold_oz" in yahoo:
        out["gold"] = usd_per_oz_to_krw_per_kg(yahoo["gold_oz"], krw)
    if "silver_oz" in yahoo:
        out["silver"] = usd_per_oz_to_krw_per_kg(yahoo["silver_oz"], krw)
    if "platinum_oz" in yahoo:
        out["platinum"] = usd_per_oz_to_krw_per_kg(yahoo["platinum_oz"], krw)
    if "palladium_oz" in yahoo:
        out["palladium"] = usd_per_oz_to_krw_per_kg(yahoo["palladium_oz"], krw)
    return out


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

    # 둘 다 없는 경우는 위에서 errors 처리됨. 머지 후 0종이면 추가 오류
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
    yahoo = fetch_yahoo()
    print(f"   → USD/KRW = {yahoo['usd_krw']:,.2f}\n")

    # 통합 LME (KRW/kg) 사전
    lme_krw = lme_to_krw_kg(lme_usd_ton, yahoo)
    print(f"   LME 환산 KRW/kg:")
    for k, v in lme_krw.items():
        print(f"      {k:9s}: {v:>15,}")
    print()

    # ---- 5. 수동 입력 ----
    print("[5/6] manual_prices.json")
    manual_root = load_json(MANUAL_FILE)
    manual_items = manual_root.get("items", {})
    print(f"   → 수동 {len(manual_items)}종\n")

    # ---- 6. 이전 data.json (히스토리 누적) ----
    print("[6/6] 이전 data.json (history 누적용)")
    prev_root = load_json(OUTPUT_FILE)
    prev_items_by_id = {it["id"]: it for it in prev_root.get("items", [])}
    print(f"   → 이전 {len(prev_items_by_id)}종\n")

    # ============================================================
    #  품목 빌드 — 우선순위로 머지
    # ============================================================
    print("─" * 60)
    print("품목 빌드 (우선순위: 수동 > 올메탈 > LME×비율 > 폴백)")
    print("─" * 60)

    out_items: list[dict] = []

    for rule in ITEM_RULES:
        (item_id, name, sub, cat, c1, c2, sym,
         lme_base, lme_ratio, fb_gwangju) = rule

        man = manual_items.get(item_id, {}) or {}
        kor = korean_prices.get(item_id) or {}

        # ---- 광주 매입가 결정 ----
        if isinstance(man.get("gwangju"), (int, float)):
            gwangju = int(man["gwangju"])
            src = "수동"
        elif kor.get("price"):
            gwangju = int(kor["price"])
            src = f"올메탈[{kor.get('label', '')[:20]}]"
        elif lme_base and lme_base in lme_krw and lme_ratio is not None:
            gwangju = int(round(lme_krw[lme_base] * lme_ratio))
            src = f"LME×{lme_ratio}"
        else:
            gwangju = fb_gwangju
            src = "폴백"

        # ---- 원청 (참고가) ----
        if lme_base and lme_base in lme_krw:
            raw = lme_krw[lme_base]
        else:
            raw = int(round(gwangju * 1.08))

        # ---- 히스토리 (이전 + 오늘) ----
        prev = prev_items_by_id.get(item_id)
        if prev and isinstance(prev.get("history"), list) and prev["history"]:
            history = list(prev["history"])
            history.append(gwangju)
            history = history[-90:]
        else:
            vol = (
                0.018 if item_id in {"silver", "gold", "platinum", "palladium"}
                else 0.008 if cat == "철(鐵) 계열"
                else 0.015
            )
            history = estimate_history(gwangju, days=90, volatility=vol,
                                       seed=stable_seed(item_id))

        # ---- 전일비 ----
        if len(history) >= 2 and history[-2] > 0:
            change_pct = round((history[-1] - history[-2]) / history[-2] * 100, 1)
        else:
            change_pct = 0.0

        # ---- 전국 평균/최저/최고 (수동 > 자동 추정) ----
        scrap_avg = int(man.get("scrapAvg") or round(gwangju * 0.99))
        scrap_min = man.get("scrapMin") or {
            "price": int(round(scrap_avg * 0.93)), "region": "경북 구미",
        }
        scrap_max = man.get("scrapMax") or {
            "price": int(round(scrap_avg * 1.05)), "region": "서울 강서구",
        }

        # ---- 광주 업체 (구조만 유지, UI에선 미사용) ----
        vendors = man.get("vendors") or vendors_default(gwangju)

        out_items.append({
            "id": item_id,
            "name": name,
            "subtitle": sub,
            "category": cat,
            "symbol": sym,
            "colorFrom": c1,
            "colorTo": c2,
            "unit": "원/kg",
            "raw": int(round(raw)),
            "change": change_pct,
            "scrapAvg": scrap_avg,
            "scrapMin": scrap_min,
            "scrapMax": scrap_max,
            "gwangju": gwangju,
            "defaultMargin": 0.80,
            "vendors": vendors,
            "history": history,
        })
        print(f"  {name:14s} {gwangju:>13,} 원/kg ({change_pct:+.1f}%)  ← {src}")

    # ---- 저장 ----
    overall_ok = len(errors) == 0
    output = {
        "today": TODAY_STR,
        "generated_at": NOW_ISO,
        "status": {
            "ok": overall_ok,
            "warnings": warnings,
            "errors": errors,
        },
        "source": {
            "usd_krw": yahoo.get("usd_krw"),
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

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✅ {OUTPUT_FILE.relative_to(REPO_ROOT)} 작성 ({len(out_items)}종)")
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

    # 오류 발생 시 GitHub Actions가 워크플로 실패로 인식 → 자동 알림 메일
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
