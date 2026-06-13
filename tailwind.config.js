/** @type {import('tailwindcss').Config} */
// 런타임 CDN(cdn.tailwindcss.com) 대신 정적 빌드용 설정.
// 이전에 index.html <head> 안에 인라인으로 있던 tailwind.config 를 그대로 옮긴 것.
// UI 클래스를 바꾸면 `npm run build:css` 로 tailwind.css 를 다시 생성해야 한다.
module.exports = {
  content: ['./index.html', './app.js', './data.js'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Pretendard Variable', 'Pretendard', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
      colors: {
        ink: {
          950: '#07090F',
          900: '#0B0F1A',
          800: '#111725',
          700: '#1A2233',
          600: '#2A3347',
        },
        brand: {
          gold: '#E8C275',
          copper: '#C87533',
        },
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.04) inset, 0 20px 40px -20px rgba(0,0,0,0.6)',
        glow: '0 0 0 1px rgba(232,194,117,0.25), 0 12px 30px -10px rgba(232,194,117,0.25)',
      },
    },
  },
  plugins: [],
};
