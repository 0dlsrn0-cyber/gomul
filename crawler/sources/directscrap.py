"""
다이렉트스크랩 (directscrap.co.kr) — 백업 한국 시세 소스.

올메탈이 묵었거나 깨졌을 때 fallback으로 사용. 사이트 SSL이 self-signed라서
`verify=False` 우회 필요. 데이터 형식:

    A동(꽈베기) (500kg 이상 도착도(vat별도)) ￦ 17,900
    상동 (500kg 이상 도착도(vat별도)) ￦ 17,100
    신주(절봉) (500kg 이상 도착도(vat별도)) ￦ 10,700  ← brass(황동)
    스텐304(A) (1,000kg 이상 도착도(vat별도)) ￦ 1,600
    샤시(A) (1,000kg 이상 도착도(vat별도)) ￦ 3,500
    생철a (5,000kg 이상 도착도(vat별도)) ￦ 420
    중량a/b, 경량a (5,000kg 이상 도착도(vat별도)) ...

다이렉트스크랩은 "신주" 라는 이름으로 황동을 표기 (절봉/주물/노베1).
보통 매일 갱신됨 (올메탈보다 신선할 때 많음).
"""

from __future__ import annotations

import re
import sys
import urllib3
from typing import Optional

import requests
from bs4 import BeautifulSoup

# SSL self-signed 경고 무시 (사이트가 인증서를 직접 발급함)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URLS = [
    ('http://www.directscrap.co.kr/html2/main.php',     '비철'),
    ('http://directscrap.co.kr/html/scrapiron_main.php', '철'),
]
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Linux; gomul-sise-tracker; family-internal) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    )
}

# 정규식 패턴 (라벨 ... ￦ 가격) — 우선순위 순서, 같은 item_id 첫 매치만 채택
PATTERNS: list[tuple[str, str]] = [
    # ===== 비철 =====
    # 동(銅) — A동·상동·파동
    (r'A동\(꽈베기\)[^￦]*￦\s*([\d,]+)',           'copper-a'),
    (r'(?<![가-힣])상동\s[^￦]*￦\s*([\d,]+)',      'copper-b'),
    (r'(?<![가-힣])파동\s[^￦]*￦\s*([\d,]+)',      'copper-c'),

    # 황동(신주) — 절봉/주물 별도, 그 외(노베 등)는 일반 황동으로
    (r'신주\s*\(\s*절봉\s*\)[^￦]*￦\s*([\d,]+)',   'brass'),
    (r'신주\s*\(\s*주물\s*\)[^￦]*￦\s*([\d,]+)',   'brass-cast'),
    (r'신주\s*\([^)]+\)[^￦]*￦\s*([\d,]+)',        'brass'),

    # 스테인리스 304 (316은 우리 목록에 없음)
    (r'스텐\s*304\s*\([^￦]*￦\s*([\d,]+)',         'stainless'),

    # 알루미늄 샤시
    (r'샤시\s*\([^￦]*￦\s*([\d,]+)',               'al-frame'),

    # 아연
    (r'(?<![가-힣])아연\s[^￦]*￦\s*([\d,]+)',      'zinc'),

    # ===== 철 =====
    (r'생철\s*[a-zA-Z]?\s*\([^￦]*￦\s*([\d,]+)',   'iron-misc'),
    (r'중량\s*[abAB]\s*\([^￦]*￦\s*([\d,]+)',      'iron-heavy'),
    (r'경량\s*[a-zA-Z]?\s*\([^￦]*￦\s*([\d,]+)',   'iron-light'),
]

COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(p), id_) for p, id_ in PATTERNS
]


def _extract_date(text: str) -> Optional[str]:
    """페이지에서 기준일자 'YYYY-MM-DD' 추출."""
    m = re.search(r'(20\d{2})[.\s]+(\d{1,2})[.\s]+(\d{1,2})', text)
    if m:
        return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    return None


def _parse(text: str) -> dict[str, dict]:
    """정규화된 텍스트에서 품목별 가격 추출."""
    found: dict[str, dict] = {}
    for compiled_pat, item_id in COMPILED:
        if item_id in found:
            continue
        m = compiled_pat.search(text)
        if not m:
            continue
        try:
            price = int(m.group(1).replace(',', ''))
        except (ValueError, IndexError):
            continue
        if not (50 <= price <= 999_999_999):
            continue
        found[item_id] = {
            'price': price,
            'src': 'directscrap',
            'label': m.group(0)[:50].strip(),
        }
    return found


def fetch() -> dict:
    """
    다이렉트스크랩 비철·철 페이지에서 시세 가져오기.

    Returns:
        {
            'ok': bool,
            'prices': { item_id: {'price': int, 'src': 'directscrap', 'label': str}, ... },
            'data_date': 'YYYY-MM-DD' or None,
            'error': str or None,
        }
    """
    out = {'ok': False, 'prices': {}, 'data_date': None, 'error': None}
    all_prices: dict[str, dict] = {}
    fetch_errors: list[str] = []
    data_dates: list[str] = []

    for url, label in URLS:
        print(f'  [directscrap] {label} fetch (verify=False)...', flush=True)
        try:
            r = requests.get(url, verify=False, timeout=20, headers=HEADERS)
            r.raise_for_status()
            r.encoding = 'utf-8'
        except Exception as e:
            fetch_errors.append(f'{label}: {e}')
            print(f'    ! {label} fetch 실패: {e}')
            continue

        soup = BeautifulSoup(r.text, 'lxml')
        text = soup.get_text(' ', strip=True)
        text = re.sub(r'\s+', ' ', text)

        d = _extract_date(text)
        if d:
            data_dates.append(d)

        prices = _parse(text)
        for k, v in prices.items():
            if k not in all_prices:
                all_prices[k] = v
        print(f'    ✓ {label} 페이지: {len(prices)}종 매칭')

    if not all_prices:
        out['error'] = '; '.join(fetch_errors) or '데이터 추출 실패'
        return out

    out['ok'] = True
    out['prices'] = all_prices
    if data_dates:
        out['data_date'] = max(data_dates)

    print(f'  → 다이렉트스크랩 총 {len(all_prices)}종, 기준일 {out["data_date"]}')
    for k, v in sorted(all_prices.items()):
        print(f'    - {k:14s} {v["price"]:>9,} 원/kg  [{v["label"]}]')
    return out


if __name__ == '__main__':
    import json
    result = fetch()
    print('\n--- JSON 결과 ---')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get('ok') else 1)
