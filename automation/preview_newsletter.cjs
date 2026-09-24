// 뉴스레터 HTML 을 모바일 폭(420px)으로 잘라 찍어 검수용 PNG 를 만든다(커밋하지 않는 임시 파일).
// 사용: node automation/preview_newsletter.cjs <issue.html> <out_prefix>
// → <out_prefix>_0.png, _1.png ... (세로 1400px씩)
const path = require('path');
const { execSync } = require('child_process');

function loadPlaywright() {
  try { return require('playwright'); } catch (_) {
    return require(path.join(execSync('npm root -g').toString().trim(), 'playwright'));
  }
}

(async () => {
  const [, , htmlPath, prefix] = process.argv;
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  await page.goto('file://' + path.resolve(htmlPath));
  await page.waitForTimeout(500);
  const H = await page.evaluate(() => document.documentElement.scrollHeight);
  const outs = [];
  for (let y = 0, i = 0; y < H; y += 1400, i++) {
    const p = `${prefix}_${i}.png`;
    await page.screenshot({ path: p, fullPage: true, clip: { x: 0, y, width: 420, height: Math.min(1400, H - y) } });
    outs.push(p);
  }
  await browser.close();
  console.log(outs.join('\n'));
})().catch((e) => { console.error(e); process.exit(1); });
