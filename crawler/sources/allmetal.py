"""
올메탈 (allmetal.co.kr) 게시판 파서 — 메인 한국 시세 소스.

게시판 첫 페이지에서 가장 최근 글의 wr_id를 찾고, 본문 텍스트를 줄 단위로 파싱.
본문 형식 예시:
    A동 - 17,700
    상동 - 16,800
    파동 - 15,700
    황동(절봉) - 10,600
    AL 샤시 - 3,600
    STS304 - 1,600
    아연A - 2,800
    중량B - 320
    경량B - 300
    생철 - 380
    폐전선(단선) - 10,400
    납 - 1,500
    배터리 - 650
"""

from __future__ import annotations

import re
import sys
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE = 'https://allmetal.co.kr'
LIST_URL = f'{BASE}/bbs/board.php?bo_table=price&page=1'
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Linux; gomul-sise-tracker; family-internal) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    )
}

# (정규식, item_id) — 위에서부터 우선 매칭, 같은 item_id 두 번째 매치는 무시.
# 본문에서 라벨과 가격이 분리된 셀에 있어서 \s+ 가 줄바꿈을 포함해 매칭함.
PATTERNS: list[tuple[str, str]] = [
    # === 동(銅) 계열 ===
    (r'A동\s+([\d,]+)',                                          'copper-a'),
    (r'상동\s+([\d,]+)',                                         'copper-b'),
    (r'파동\s+([\d,]+)',                                         'copper-c'),

    # 동선 — 종류별로 매핑 (고압선A/B 가장 먼저, '잡선' 가장 마지막)
    (r'폐?전선\s*\(\s*고압선?\s*A\s*\)\s+([\d,]+)',             'wire-hv-a'),
    (r'폐?전선\s*\(\s*고압선?\s*B\s*\)\s+([\d,]+)',             'wire-hv-b'),
    (r'폐?전선\s*\(\s*단선\s*\)\s+([\d,]+)',                    'wire-bare'),
    (r'폐?전선\s*\(\s*통신선?\s*\)\s+([\d,]+)',                 'wire-comm'),
    (r'폐?전선\s*\(\s*중선\s*\)\s+([\d,]+)',                    'wire-medium'),
    (r'폐?전선\s*\(\s*잡선\s*\)\s+([\d,]+)',                    'wire-coated'),

    # 황동(신주) — 절봉(절삭용) / 주물(주조용) 별도 매핑
    (r'황동\s*\(\s*절봉\s*\)\s+([\d,]+)',                       'brass'),
    (r'황동\s*\(\s*주물\s*\)\s+([\d,]+)',                       'brass-cast'),

    # 인청동 (Cu-Sn 합금) — 2종 우선
    (r'인청동\s*2종\s+([\d,]+)',                                'phosphor-bronze'),
    (r'인청동\s*3종\s+([\d,]+)',                                'phosphor-bronze'),
    (r'인청동\s+([\d,]+)',                                      'phosphor-bronze'),

    # 양은 (Cu-Ni-Zn 합금) — 양백·백동 표기 변종
    (r'양은\s+([\d,]+)',                                        'nickel-silver'),
    (r'양백\s+([\d,]+)',                                        'nickel-silver'),
    (r'백동\s+([\d,]+)',                                        'nickel-silver'),

    # 알루미늄 5종 — 종류별 매핑
    (r'AL\s*프로파일\s+([\d,]+)',                               'al-profile'),
    (r'AL\s*판재\s+([\d,]+)',                                   'al-plate'),
    (r'AL\s*샤시\s+([\d,]+)',                                   'al-frame'),
    (r'AL\s*주물\s+([\d,]+)',                                   'al-cast'),
    (r'AL\s*분철\s+([\d,]+)',                                   'al-powder'),

    # 스테인리스 304 일반 (분철 자동 제외 — \s+ 다음에 숫자 직접)
    (r'STS\s*304\s+([\d,]+)',                                   'stainless'),

    # 아연 (A급 우선)
    (r'아연\s*A\s+([\d,]+)',                                    'zinc'),
    (r'아연\s+([\d,]+)',                                        'zinc'),

    # 철 (B급 → A급 → 무등급 순)
    (r'중량\s*B\s+([\d,]+)',                                    'iron-heavy'),
    (r'중량\s*A\s+([\d,]+)',                                    'iron-heavy'),
    (r'경량\s*B\s+([\d,]+)',                                    'iron-light'),
    (r'경량\s*A\s+([\d,]+)',                                    'iron-light'),
    (r'생철\s+([\d,]+)',                                        'iron-misc'),
    (r'잡철\s+([\d,]+)',                                        'iron-misc'),

    # 납·배터리 (납은 폐납 등 한글 접두 제외)
    (r'(?<![가-힣])납\s+([\d,]+)',                              'lead'),
    (r'배터리\s+([\d,]+)',                                      'car-battery'),

    # 니켈 (99.9% 같은 등급 표기 흡수)
    (r'니켈\s*(?:99[.\d]+%?)?\s*([\d,]+)',                      'nickel'),
]

COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(p), id_) for p, id_ in PATTERNS
]


def _find_latest_wr_id(html: str) -> Optional[int]:
    """게시판 목록에서 가장 큰 wr_id 추출 (= 가장 최근 글)."""
    soup = BeautifulSoup(html, 'lxml')
    ids = []
    for a in soup.select('a[href*="wr_id="]'):
        m = re.search(r'wr_id=(\d+)', a.get('href', ''))
        if m:
            ids.append(int(m.group(1)))
    if not ids:
        # 폴백: 그냥 페이지 전체 텍스트에서 wr_id 추출
        ids = [int(x) for x in re.findall(r'wr_id=(\d+)', html)]
    return max(ids) if ids else None


def _extract_post_date(html: str) -> Optional[str]:
    """게시글 페이지에서 작성일자 추출. 'YYYY-MM-DD' 또는 None."""
    soup = BeautifulSoup(html, 'lxml')

    # 그누보드 흔한 셀렉터들
    text_candidates = []
    for sel in ['strong.bo_v_nb', '.bo_v_nb', '.bo_v_info', '.view_info', 'time']:
        for el in soup.select(sel):
            text_candidates.append(el.get_text(strip=True))

    # 본문 외 영역(헤더·메타)에서 우선 검색
    for text in text_candidates:
        m = re.search(r'(\d{2,4})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})\b', text)
        if m:
            y, mo, d = m.groups()
            year = int(y)
            if year < 100:
                year += 2000
            return f'{year:04d}-{int(mo):02d}-{int(d):02d}'

    # 폴백: 페이지 전체에서 YY-MM-DD HH:MM 패턴
    full_text = soup.get_text(' ', strip=True)
    m = re.search(r'(?<!\d)(\d{2})-(\d{2})-(\d{2})\s+\d{1,2}:\d{2}', full_text)
    if m:
        yy, mo, d = m.groups()
        return f'20{yy}-{mo}-{d}'
    return None


def _extract_post_body(html: str) -> str:
    """게시글 본문 텍스트 추출 (그누보드 일반 구조 시도)."""
    soup = BeautifulSoup(html, 'lxml')

    # 그누보드 본문 영역 후보들
    for sel in ['#bo_v_con', '.view_content', '#bo_v_atc', 'article', 'main']:
        node = soup.select_one(sel)
        if node:
            return node.get_text('\n', strip=False)

    # 폴백: body 전체
    return soup.get_text('\n', strip=False)


def _parse_post_body(text: str) -> dict[str, dict]:
    """본문 텍스트(셀 단위 줄바꿈 다수)에서 품목별 가격 추출.

    공백·줄바꿈을 단일 공백으로 정규화한 뒤 라벨↔가격 짝을 정규식으로 매칭.
    같은 item_id에 대해서는 가장 먼저 매칭된 결과만 채택 (PATTERNS 순서가 우선순위).
    """
    normalized = re.sub(r'\s+', ' ', text)

    found: dict[str, dict] = {}
    for compiled_pat, item_id in COMPILED:
        if item_id in found:
            continue
        m = compiled_pat.search(normalized)
        if not m:
            continue
        try:
            price = int(m.group(1).replace(',', ''))
        except (ValueError, IndexError):
            continue
        if price <= 0 or price > 999_999_999:
            continue
        # 너무 작은 가격은 의심스러움 (모터·배터리는 100~1000 가능, 다른 건 보통 100+)
        if price < 50:
            continue
        found[item_id] = {
            'price': price,
            'src': 'allmetal',
            'label': m.group(0)[:50].strip(),
        }
    return found


def fetch() -> dict:
    """
    올메탈 최신 시세 게시글 fetch & parse.

    Returns:
        {
            'ok': bool,
            'prices': { item_id: {'price': int, 'src': 'allmetal', 'label': str}, ... },
            'post_date': 'YYYY-MM-DD' or None,
            'wr_id': int or None,
            'error': str or None,
        }
    """
    out = {'ok': False, 'prices': {}, 'post_date': None, 'wr_id': None, 'error': None}

    print('  [allmetal] 게시판 목록 fetch...', flush=True)
    try:
        r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        out['error'] = f'목록 fetch 실패: {e}'
        print(f'    ! {out["error"]}')
        return out

    wr_id = _find_latest_wr_id(r.text)
    if not wr_id:
        out['error'] = '최근 wr_id 추출 실패 (사이트 구조 변경?)'
        print(f'    ! {out["error"]}')
        return out
    out['wr_id'] = wr_id
    print(f'    ✓ 최근 글: wr_id={wr_id}')

    post_url = f'{BASE}/bbs/board.php?bo_table=price&wr_id={wr_id}'
    print(f'  [allmetal] 본문 fetch: wr_id={wr_id}')
    try:
        r = requests.get(post_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        out['error'] = f'본문 fetch 실패: {e}'
        print(f'    ! {out["error"]}')
        return out

    out['post_date'] = _extract_post_date(r.text)
    if out['post_date']:
        print(f'    ✓ 작성일: {out["post_date"]}')

    body_text = _extract_post_body(r.text)
    if len(body_text) < 50:
        out['error'] = f'본문 너무 짧음 ({len(body_text)}자) — 셀렉터 확인 필요'
        print(f'    ! {out["error"]}')
        return out

    out['prices'] = _parse_post_body(body_text)
    out['ok'] = True
    print(f'    ✓ 매칭 품목 {len(out["prices"])}종:')
    for item_id, info in sorted(out['prices'].items()):
        print(f'      - {item_id:14s} {info["price"]:>9,} 원/kg  [{info["label"]}]')
    return out


# 단독 실행 시 테스트
if __name__ == '__main__':
    import json
    result = fetch()
    print('\n--- JSON 결과 ---')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get('ok') and result.get('prices') else 1)
