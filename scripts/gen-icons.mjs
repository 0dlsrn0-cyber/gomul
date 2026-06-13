// icon.svg → 래스터 PNG 아이콘 생성 (PWA 설치 호환용).
// 실행: node scripts/gen-icons.mjs
//
// 만들어지는 파일:
//   icon-192.png            : 192x192 (purpose any)
//   icon-512.png            : 512x512 (purpose any)
//   icon-maskable-512.png   : 512x512, 풀블리드 배경 + 내용 안전영역(80%) 안에 배치 (purpose maskable)
//   apple-touch-icon.png    : 180x180 (iOS 홈화면)
//
// 주의: SVG의 '古' 글자는 렌더 머신의 CJK 폰트로 그려진다. 결과 PNG를 눈으로 확인할 것.
import sharp from 'sharp';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const svg = readFileSync(join(ROOT, 'icon.svg'));

const BG = '#0B0F1A';

async function render(size, outName) {
  await sharp(svg, { density: 384 })
    .resize(size, size, { fit: 'contain', background: BG })
    .png()
    .toFile(join(ROOT, outName));
  console.log('  ✓', outName, `(${size}x${size})`);
}

async function renderMaskable(size, outName) {
  const inner = Math.round(size * 0.8); // 안전영역 80%
  const iconBuf = await sharp(svg, { density: 384 })
    .resize(inner, inner, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer();
  const pad = Math.round((size - inner) / 2);
  await sharp({
    create: { width: size, height: size, channels: 4, background: BG },
  })
    .composite([{ input: iconBuf, top: pad, left: pad }])
    .png()
    .toFile(join(ROOT, outName));
  console.log('  ✓', outName, `(maskable ${size}x${size}, 내용 ${inner}px)`);
}

console.log('아이콘 생성:');
await render(192, 'icon-192.png');
await render(512, 'icon-512.png');
await render(180, 'apple-touch-icon.png');
await renderMaskable(512, 'icon-maskable-512.png');
console.log('완료.');
