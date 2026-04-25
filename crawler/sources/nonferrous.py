"""
한국비철금속협회 (nonferrous.or.kr) LME 시세 파서.

LME 6대 비철금속의 USD/톤 가격을 가져와서 KRW/kg 환산용 베이스로 사용.

페이지 구조 (단일 테이블, 22행):
  [0] ['일자', '품목']                                  ← 헤더 1
  [1] ['Cu', 'Al', 'Zn', 'Pb', 'Ni', 'Sn']             ← 헤더 2 (금속 약자)
  [2] ['2026. 04. 23', '13190.0', '3642.0', '3446.0', '1940.5', '18425.0', '50250.0']
  [3] [이전 일자, ...]
  ...

페이지 인코딩: UTF-8 (단 Content-Type이 다르게 응답해서 강제 지정 필요)
"""

from __future__ import annotations

import re
import sys
from typing import Optional

import requests
from bs4 import BeautifulSoup

URL = 'https://www.nonferrous.or.kr/stats/?act=sub3'
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Linux; gomul-sise-tracker; family-internal) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    )
}

METAL_SYMBOL_TO_KEY = {
    'Cu': 'copper',
    'Al': 'aluminum',
    'Zn': 'zinc',
    'Pb': 'lead',
    'Ni': 'nickel',
    'Sn': 'tin',
}


def _is_date_cell(s: str) -> bool:
    return bool(re.match(r'\d{4}', s.strip()))


def fetch() -> dict:
    """
    한국비철금속협회 LME 시세 fetch.

    Returns:
        {
            'ok': bool,
            'prices': {'copper': 13190.0, ...},  # USD/톤
            'data_date': 'YYYY-MM-DD' or None,
            'error': str or None,
        }
    """
    out = {'ok': False, 'prices': {}, 'data_date': None, 'error': None}

    print('  [nonferrous] LME 페이지 fetch...', flush=True)
    try:
        r = requests.get(URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        r.encoding = 'utf-8'
    except Exception as e:
        out['error'] = f'fetch 실패: {e}'
        print(f'    ! {out["error"]}')
        return out

    soup = BeautifulSoup(r.text, 'lxml')
    table = soup.find('table')
    if not table:
        out['error'] = '<table> 없음 (사이트 구조 변경?)'
        print(f'    ! {out["error"]}')
        return out

    rows = table.find_all('tr')

    # 1) 금속 약자 헤더 행 찾기
    header_cols: Optional[list[str]] = None
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
        if len(cells) >= 6 and all(c in METAL_SYMBOL_TO_KEY for c in cells[:6]):
            header_cols = cells[:6]
            break

    if not header_cols:
        out['error'] = '금속 약자 헤더 못 찾음'
        print(f'    ! {out["error"]}')
        return out
    print(f'    ✓ 헤더: {header_cols}')

    # 2) 첫 데이터 행 찾기
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
        if len(cells) < 1 + len(header_cols):
            continue
        if not _is_date_cell(cells[0]):
            continue

        date_str = cells[0]
        # 날짜 정규화: '2026. 04. 23' → '2026-04-23'
        m = re.match(r'(\d{4})[.\s]+(\d{1,2})[.\s]+(\d{1,2})', date_str)
        if m:
            out['data_date'] = f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

        prices: dict[str, float] = {}
        for i, sym in enumerate(header_cols):
            data_idx = i + 1
            if data_idx >= len(cells):
                continue
            try:
                prices[METAL_SYMBOL_TO_KEY[sym]] = float(cells[data_idx].replace(',', ''))
            except ValueError:
                pass

        if prices:
            out['prices'] = prices
            out['ok'] = True
            print(f'    ✓ 기준일: {out["data_date"] or date_str}')
            for k, v in prices.items():
                print(f'      - {k:9s}: {v:>10,.1f} USD/톤')
            return out

    out['error'] = '데이터 행 못 찾음'
    print(f'    ! {out["error"]}')
    return out


if __name__ == '__main__':
    import json
    result = fetch()
    print('\n--- JSON 결과 ---')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get('ok') else 1)
