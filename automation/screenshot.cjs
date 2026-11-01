// HTML 한 장 → PNG 한 장(사이트 그림: 공유 미리보기·아이콘). automation/build_site_assets.py 가 부른다.
// 사용: node automation/screenshot.cjs <page.html> <out.png> <width> <height> [--transparent]
// --transparent: 배경을 투명하게(동그란 아이콘의 모서리).
const path = require('path');
const { execSync } = require('child_process');

function loadPlaywright() {
  try { return require('playwright'); } catch (_) {
    const root = execSync('npm root -g').toString().trim();
    return require(path.join(root, 'playwright'));
  }
}

(async () => {
  const [, , htmlPath, outPath, w, h, ...flags] = process.argv;
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.resolve(htmlPath));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  const missing = await page.evaluate(() => [...document.images].filter((i) => !i.complete || !i.naturalWidth).map((i) => i.src));
  if (missing.length) { console.error('그림을 못 읽음: ' + missing.join(', ')); process.exit(1); }
  // .jpg 로 받으면 JPEG(품질 95)로 바로 찍는다 — 웹툰 장(comic.py)이 ffmpeg 없이도 인스타용 JPEG 를 만든다. 나머지는 지금처럼 PNG.
  const jpeg = /\.jpe?g$/i.test(outPath);
  await page.screenshot(jpeg ? { path: outPath, type: 'jpeg', quality: 95 } : { path: outPath, omitBackground: flags.includes('--transparent') });
  const fonts = await page.evaluate(() => [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family));
  // class 'fit' 상자가 넘쳤나(글이 길어 칸 밖으로) — 부르는 쪽(웹툰 comic.py)이 실패로 다룬다. 다른 쪽은 이 칸을 안 읽는다.
  const overflow = await page.evaluate(() => [...document.querySelectorAll('.fit')]
    .filter((e) => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1).map((e) => e.className));
  console.log(JSON.stringify({ out: outPath, fonts: [...new Set(fonts)], overflow }));
  await browser.close();
})();
