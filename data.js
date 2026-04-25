// 고물시세 폴백 mock 데이터
// 실제 데이터는 data.json (크롤러가 매일 갱신)을 우선 사용. 이 파일은 data.json 없을 때만 사용됨.
// 단위는 모두 원/kg.

let TODAY = new Date('2026-04-25');

// ---------- 유틸 ----------
function seedRandom(seed) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function generateHistory(currentPrice, seed, days = 90, volatility = 0.015) {
  const rand = seedRandom(seed);
  const prices = new Array(days);
  let p = currentPrice;
  for (let i = days - 1; i >= 0; i--) {
    prices[i] = Math.round(p);
    const drift = (rand() - 0.5) * volatility * 2;
    p = p / (1 + drift);
  }
  prices[days - 1] = currentPrice;
  return prices;
}

function makeVendors(gwangju) {
  return [
    { name: '대성자원 (서구 금호동)', price: Math.round(gwangju * 1.012) },
    { name: '상록재활용 (북구 운암동)', price: Math.round(gwangju * 1.004) },
    { name: '동양자원 (광산구 송정동)', price: Math.round(gwangju * 0.992) },
    { name: '중앙상회 (남구 봉선동)', price: Math.round(gwangju * 0.978) },
  ];
}

// ---------- 품목 정의 (30종) ----------
let ITEMS = [
  // ==================== 동(銅) 계열 (10) ====================
  {
    id: 'copper-a', category: '동(銅) 계열',
    name: '구리 상', subtitle: '1A · 깨끗한 동',
    symbol: 'Cu+', colorFrom: '#F0A95C', colorTo: '#8B4513',
    raw: 19473, change: 1.4, scrapAvg: 17500,
    scrapMin: { price: 17000, region: '경북 구미' },
    scrapMax: { price: 18000, region: '서울 강서구' },
    gwangju: 17700, defaultMargin: 0.80, seed: 101,
  },
  {
    id: 'copper-b', category: '동(銅) 계열',
    name: '구리 중', subtitle: '2A · 약간 산화',
    symbol: 'Cu', colorFrom: '#D69150', colorTo: '#6B3410',
    raw: 19473, change: 1.2, scrapAvg: 16500,
    scrapMin: { price: 16000, region: '경북 구미' },
    scrapMax: { price: 17000, region: '서울 강서구' },
    gwangju: 16800, defaultMargin: 0.80, seed: 102,
  },
  {
    id: 'copper-c', category: '동(銅) 계열',
    name: '구리 하', subtitle: '3A · 산화/혼입',
    symbol: 'Cu-', colorFrom: '#A87040', colorTo: '#4A2410',
    raw: 19473, change: 1.0, scrapAvg: 15500,
    scrapMin: { price: 15000, region: '강원 원주' },
    scrapMax: { price: 16000, region: '경기 시흥' },
    gwangju: 15700, defaultMargin: 0.80, seed: 103,
  },
  {
    id: 'wire-hv-a', category: '동(銅) 계열',
    name: '고압선 A', subtitle: '고압 케이블 A급',
    symbol: '高+', colorFrom: '#E5B47A', colorTo: '#8C5520',
    raw: 19473, change: 0.9, scrapAvg: 12500,
    scrapMin: { price: 12000, region: '경기 화성' },
    scrapMax: { price: 13000, region: '서울 강북구' },
    gwangju: 12800, defaultMargin: 0.80, seed: 104,
  },
  {
    id: 'wire-hv-b', category: '동(銅) 계열',
    name: '고압선 B', subtitle: '고압 케이블 B급',
    symbol: '高', colorFrom: '#D5A065', colorTo: '#7A4515',
    raw: 19473, change: 0.8, scrapAvg: 11200,
    scrapMin: { price: 10800, region: '강원 강릉' },
    scrapMax: { price: 11700, region: '인천 남동구' },
    gwangju: 11500, defaultMargin: 0.80, seed: 105,
  },
  {
    id: 'wire-bare', category: '동(銅) 계열',
    name: '나동선', subtitle: '단선 · 피복 없는 동선',
    symbol: '線+', colorFrom: '#E2A55C', colorTo: '#7A3D11',
    raw: 19473, change: 1.3, scrapAvg: 10100,
    scrapMin: { price: 9800, region: '충남 천안' },
    scrapMax: { price: 10500, region: '인천 남동구' },
    gwangju: 10400, defaultMargin: 0.80, seed: 106,
  },
  {
    id: 'wire-comm', category: '동(銅) 계열',
    name: '통신선', subtitle: '통신·전화 케이블',
    symbol: '通', colorFrom: '#C28855', colorTo: '#5A3010',
    raw: 19473, change: 0.4, scrapAvg: 5800,
    scrapMin: { price: 5500, region: '전남 순천' },
    scrapMax: { price: 6200, region: '경기 안산' },
    gwangju: 6000, defaultMargin: 0.80, seed: 107,
  },
  {
    id: 'wire-medium', category: '동(銅) 계열',
    name: '중선', subtitle: '중간 등급 피복선',
    symbol: '中', colorFrom: '#B5814A', colorTo: '#4F2A12',
    raw: 19473, change: 0.3, scrapAvg: 5700,
    scrapMin: { price: 5400, region: '경북 포항' },
    scrapMax: { price: 6100, region: '경기 시흥' },
    gwangju: 5900, defaultMargin: 0.80, seed: 108,
  },
  {
    id: 'wire-coated', category: '동(銅) 계열',
    name: '피복선', subtitle: '잡선 · 일반 피복선',
    symbol: '線', colorFrom: '#B07845', colorTo: '#3A2818',
    raw: 19473, change: 0.9, scrapAvg: 3700,
    scrapMin: { price: 3500, region: '전남 순천' },
    scrapMax: { price: 4000, region: '서울 강남구' },
    gwangju: 3800, defaultMargin: 0.80, seed: 109,
  },
  {
    id: 'motor', category: '동(銅) 계열',
    name: '모터·컴프레서', subtitle: '동권선 함유 복합',
    symbol: '電', colorFrom: '#8B6B40', colorTo: '#2A1810',
    raw: 19473, change: 0.8, scrapAvg: 850,
    scrapMin: { price: 750, region: '강원 강릉' },
    scrapMax: { price: 950, region: '경기 안산' },
    gwangju: 870, defaultMargin: 0.80, seed: 110,
  },

  // ==================== 알루미늄 계열 (5) ====================
  {
    id: 'al-profile', category: '알루미늄 계열',
    name: 'AL 프로파일', subtitle: '압출재 · 일반 산업용',
    symbol: '型', colorFrom: '#E0E5EA', colorTo: '#7B8794',
    raw: 5377, change: -0.3, scrapAvg: 3700,
    scrapMin: { price: 3500, region: '경기 안산' },
    scrapMax: { price: 3900, region: '경남 창원' },
    gwangju: 3800, defaultMargin: 0.80, seed: 201,
  },
  {
    id: 'al-plate', category: '알루미늄 계열',
    name: 'AL 판재', subtitle: '판형 알루미늄',
    symbol: '板', colorFrom: '#D6DCE2', colorTo: '#76828F',
    raw: 5377, change: -0.4, scrapAvg: 3600,
    scrapMin: { price: 3450, region: '경기 화성' },
    scrapMax: { price: 3800, region: '울산' },
    gwangju: 3700, defaultMargin: 0.80, seed: 202,
  },
  {
    id: 'al-frame', category: '알루미늄 계열',
    name: 'AL 샤시', subtitle: '창틀 압출재',
    symbol: '窓', colorFrom: '#D6D9DE', colorTo: '#7B8794',
    raw: 5377, change: -0.6, scrapAvg: 3500,
    scrapMin: { price: 3300, region: '충남 천안' },
    scrapMax: { price: 3700, region: '부산 강서구' },
    gwangju: 3600, defaultMargin: 0.80, seed: 203,
  },
  {
    id: 'al-cast', category: '알루미늄 계열',
    name: 'AL 주물', subtitle: '주조용 알루미늄',
    symbol: '鑄', colorFrom: '#C5CCD5', colorTo: '#6A7785',
    raw: 5377, change: -0.5, scrapAvg: 2600,
    scrapMin: { price: 2450, region: '경북 안동' },
    scrapMax: { price: 2800, region: '경기 화성' },
    gwangju: 2700, defaultMargin: 0.80, seed: 204,
  },
  {
    id: 'al-powder', category: '알루미늄 계열',
    name: 'AL 분철', subtitle: '가공 부산물 · 칩',
    symbol: '粉', colorFrom: '#B8C0CA', colorTo: '#5C6573',
    raw: 5377, change: -0.7, scrapAvg: 2200,
    scrapMin: { price: 2050, region: '강원 원주' },
    scrapMax: { price: 2400, region: '경기 안산' },
    gwangju: 2300, defaultMargin: 0.80, seed: 205,
  },

  // ==================== 철(鐵) 계열 (3) ====================
  {
    id: 'iron-heavy', category: '철(鐵) 계열',
    name: '철 중량', subtitle: '두꺼운 철 · 6mm 이상',
    symbol: 'Fe+', colorFrom: '#8A95A5', colorTo: '#3F4857',
    raw: 460, change: 0.4, scrapAvg: 320,
    scrapMin: { price: 300, region: '강원 춘천' },
    scrapMax: { price: 360, region: '인천 남동구' },
    gwangju: 320, defaultMargin: 0.80, seed: 301,
  },
  {
    id: 'iron-light', category: '철(鐵) 계열',
    name: '철 경량', subtitle: '얇은 철 · 6mm 미만',
    symbol: 'Fe-', colorFrom: '#A0AAB8', colorTo: '#5C6573',
    raw: 460, change: 0.2, scrapAvg: 290,
    scrapMin: { price: 270, region: '강원 춘천' },
    scrapMax: { price: 320, region: '경기 시흥' },
    gwangju: 300, defaultMargin: 0.80, seed: 302,
  },
  {
    id: 'iron-misc', category: '철(鐵) 계열',
    name: '잡철', subtitle: '生鐵 · 혼합 철물',
    symbol: '雜', colorFrom: '#6B7280', colorTo: '#242A34',
    raw: 460, change: -0.2, scrapAvg: 360,
    scrapMin: { price: 340, region: '전남 목포' },
    scrapMax: { price: 400, region: '경기 안산' },
    gwangju: 380, defaultMargin: 0.80, seed: 303,
  },

  // ==================== 일반 비철 (6) ====================
  {
    id: 'stainless', category: '일반 비철',
    name: '스테인리스', subtitle: 'STS 304',
    symbol: 'SS', colorFrom: '#C9D2DC', colorTo: '#5A6676',
    raw: 2100, change: 0.8, scrapAvg: 1550,
    scrapMin: { price: 1450, region: '울산' },
    scrapMax: { price: 1700, region: '경기 시흥' },
    gwangju: 1600, defaultMargin: 0.80, seed: 401,
  },
  {
    id: 'brass', category: '일반 비철',
    name: '황동(신주)', subtitle: '절봉 · Cu-Zn 절삭용',
    symbol: 'Br', colorFrom: '#E8C275', colorTo: '#8B6914',
    raw: 15189, change: 1.1, scrapAvg: 10500,
    scrapMin: { price: 10200, region: '충북 청주' },
    scrapMax: { price: 10800, region: '서울 금천구' },
    gwangju: 10600, defaultMargin: 0.80, seed: 402,
  },
  {
    id: 'brass-cast', category: '일반 비철',
    name: '황동 주물', subtitle: '주조용 · Cu-Zn',
    symbol: '鑄', colorFrom: '#C9A55A', colorTo: '#6F4E10',
    raw: 15189, change: 0.4, scrapAvg: 10100,
    scrapMin: { price: 9800, region: '경북 포항' },
    scrapMax: { price: 10400, region: '서울 금천구' },
    gwangju: 10200, defaultMargin: 0.80, seed: 408,
  },
  {
    id: 'phosphor-bronze', category: '일반 비철',
    name: '인청동(주석)', subtitle: 'Cu-Sn · 청동 합금',
    symbol: '靑', colorFrom: '#B5814E', colorTo: '#4A2D14',
    raw: 17500, change: 0.6, scrapAvg: 17000,
    scrapMin: { price: 16500, region: '경기 시흥' },
    scrapMax: { price: 17800, region: '서울 성동구' },
    gwangju: 17400, defaultMargin: 0.80, seed: 403,
  },
  {
    id: 'nickel-silver', category: '일반 비철',
    name: '양은', subtitle: '양백 · Cu-Ni-Zn',
    symbol: '洋', colorFrom: '#D8DDE3', colorTo: '#7B8590',
    raw: 11500, change: 0.0, scrapAvg: 10500,
    scrapMin: { price: 9800, region: '경기 평택' },
    scrapMax: { price: 11200, region: '서울 영등포구' },
    gwangju: 10700, defaultMargin: 0.80, seed: 404,
  },
  {
    id: 'lead', category: '일반 비철',
    name: '납', subtitle: 'Pb · 일반 납',
    symbol: 'Pb', colorFrom: '#6E7785', colorTo: '#2A313C',
    raw: 2865, change: -1.0, scrapAvg: 1450,
    scrapMin: { price: 1380, region: '전북 군산' },
    scrapMax: { price: 1550, region: '경기 안산' },
    gwangju: 1500, defaultMargin: 0.80, seed: 405,
  },
  {
    id: 'car-battery', category: '일반 비철',
    name: '자동차 배터리', subtitle: '납축전지 · 액 포함',
    symbol: '蓄', colorFrom: '#8FBF7F', colorTo: '#2D5A1F',
    raw: 2865, change: -0.8, scrapAvg: 670,
    scrapMin: { price: 600, region: '강원 원주' },
    scrapMax: { price: 720, region: '경기 평택' },
    gwangju: 650, defaultMargin: 0.80, seed: 406,
  },

  // ==================== 기타 비철금속 (6) ====================
  {
    id: 'silver', category: '기타 비철금속',
    name: '은', subtitle: 'Ag · 순은 (kg 환산)',
    symbol: 'Ag', colorFrom: '#F0F4F9', colorTo: '#8E9AA6',
    raw: 3625503, change: 2.1, scrapAvg: 3262953,
    scrapMin: { price: 3140000, region: '제주' },
    scrapMax: { price: 3300000, region: '서울 종로구' },
    gwangju: 3262953, defaultMargin: 0.80, seed: 601,
  },
  {
    id: 'gold', category: '기타 비철금속',
    name: '금', subtitle: 'Au · 순금 (kg 환산)',
    symbol: 'Au', colorFrom: '#FFD700', colorTo: '#8B6914',
    raw: 224142961, change: 1.8, scrapAvg: 217418672,
    scrapMin: { price: 210000000, region: '대전' },
    scrapMax: { price: 220000000, region: '서울 종로구' },
    gwangju: 217418672, defaultMargin: 0.80, seed: 602,
  },
  {
    id: 'zinc', category: '기타 비철금속',
    name: '아연', subtitle: 'Zn · 함석',
    symbol: 'Zn', colorFrom: '#A8B5C5', colorTo: '#4A5868',
    raw: 5087, change: -0.4, scrapAvg: 2800,
    scrapMin: { price: 2550, region: '강원 동해' },
    scrapMax: { price: 3000, region: '경기 안산' },
    gwangju: 2800, defaultMargin: 0.80, seed: 603,
  },
  {
    id: 'nickel', category: '기타 비철금속',
    name: '니켈', subtitle: 'Ni · 산업급',
    symbol: 'Ni', colorFrom: '#B5C9B0', colorTo: '#567252',
    raw: 27201, change: 0.6, scrapAvg: 23000,
    scrapMin: { price: 22000, region: '충남 당진' },
    scrapMax: { price: 24000, region: '경기 평택' },
    gwangju: 23121, defaultMargin: 0.80, seed: 604,
  },
  {
    id: 'platinum', category: '기타 비철금속',
    name: '백금', subtitle: 'Pt · 촉매·보석',
    symbol: 'Pt', colorFrom: '#E8E8EC', colorTo: '#9CA3AF',
    raw: 95641549, change: 1.0, scrapAvg: 91815887,
    scrapMin: { price: 89000000, region: '대구' },
    scrapMax: { price: 93000000, region: '서울 종로구' },
    gwangju: 91815887, defaultMargin: 0.80, seed: 605,
  },
  {
    id: 'palladium', category: '기타 비철금속',
    name: '팔라듐', subtitle: 'Pd · 촉매변환기',
    symbol: 'Pd', colorFrom: '#D8D9E0', colorTo: '#7A8090',
    raw: 71268380, change: -0.5, scrapAvg: 66992277,
    scrapMin: { price: 65000000, region: '울산' },
    scrapMax: { price: 68500000, region: '서울 종로구' },
    gwangju: 66992277, defaultMargin: 0.80, seed: 606,
  },
];

// 단위 / 업체 / 추세 자동 채움
ITEMS.forEach((it) => {
  it.unit = '원/kg';
  it.vendors = makeVendors(it.gwangju);
  const vol =
    ['silver', 'gold', 'platinum', 'palladium'].includes(it.id)
      ? 0.018
      : it.category === '철(鐵) 계열'
      ? 0.008
      : 0.015;
  it.history = generateHistory(it.gwangju, it.seed, 90, vol);
});
