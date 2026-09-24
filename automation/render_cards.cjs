// 카드 HTML(한 페이지에 .card 여러 장) → PNG 1080×1350.
// 사용: node automation/render_cards.cjs <cards.html> <out_dir> [--jpeg-dir=<dir>] <file1.png> <file2.png> ...
// --jpeg-dir: 인스타그램 API 는 JPEG 만 받으므로 같은 카드를 JPEG(품질 92)로도 저장한다(파일명은 .png → .jpg).
// 넘치는 카드는 글자 크기 배율(--k)을 3%씩 최대 20%까지 줄이고, 그래도 넘치면 결과에 overflow:true 로 남긴다.
// 결과(JSON)는 stdout 마지막 줄.
const path = require('path');
const { execSync } = require('child_process');

function loadPlaywright() {
  try { return require('playwright'); } catch (_) {
    const root = execSync('npm root -g').toString().trim();
    return require(path.join(root, 'playwright'));
  }
}

(async () => {
  const [, , htmlPath, outDir, ...rest] = process.argv;
  const jpegDir = (rest.find((a) => a.startsWith('--jpeg-dir=')) || '').slice('--jpeg-dir='.length);
  const files = rest.filter((a) => !a.startsWith('--'));
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1 });
  await page.goto('file://' + path.resolve(htmlPath));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);

  const report = await page.evaluate(() => {
    // 카드 내용은 아래에서 위로 쌓이므로(.body 가 flex-end) 넘치면 위쪽으로 삐져나간다 —
    // 스크롤 높이와 함께 첫 요소가 카드 위 여백(60px) 안으로 들어왔는지도 본다.
    const fits = (card) => {
      const top = card.getBoundingClientRect().top;
      for (const body of card.querySelectorAll('.body')) {
        if (body.scrollHeight > body.clientHeight + 1) return false;
        const first = body.firstElementChild;
        if (first && first.getBoundingClientRect().top < top + 60) return false;
      }
      return card.scrollHeight <= card.clientHeight + 1;
    };
    // .shrink: 줄을 고르게 나눈(balance) 뒤 상자 폭을 가장 긴 줄에 맞춘다 — 말풍선 오른쪽이 비지 않게.
    // 폭만 줄이므로 높이는 늘지 않아 위의 넘침 판정이 그대로 유효하다.
    const shrinkWrap = (el) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      const rects = [...range.getClientRects()].filter((r) => r.width > 0);
      if (!rects.length) return;
      const cs = getComputedStyle(el);
      const px = (v) => parseFloat(v) || 0;
      const inner = el.getBoundingClientRect().left + px(cs.borderLeftWidth) + px(cs.paddingLeft);
      const text = Math.max(...rects.map((r) => r.right)) - inner;
      el.style.width = Math.ceil(text + px(cs.paddingLeft) + px(cs.paddingRight) + px(cs.borderLeftWidth) + px(cs.borderRightWidth) + 2) + 'px';
    };
    return [...document.querySelectorAll('.card')].map((card) => {
      let k = 1;
      while (!fits(card) && k > 0.8) {
        k = Math.round((k - 0.03) * 100) / 100;
        card.style.setProperty('--k', k);
      }
      card.querySelectorAll('.shrink').forEach(shrinkWrap);
      const fonts = [...new Set([...card.querySelectorAll('*')].map((e) => getComputedStyle(e).fontFamily.split(',')[0].replace(/['"]/g, '')))];
      return { k, overflow: !fits(card), fonts };
    });
  });

  // 폰트가 실제로 로드됐는지(대체 글꼴로 찍히는 사고 방지)
  const loaded = await page.evaluate(() => [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/['"]/g, '')));
  const cards = await page.$$('.card');
  if (cards.length !== files.length) {
    console.error(`카드 수(${cards.length})와 파일명 수(${files.length})가 다릅니다`);
    process.exit(2);
  }
  for (let i = 0; i < cards.length; i++) {
    await cards[i].screenshot({ path: path.join(outDir, files[i]) });
    if (jpegDir) await cards[i].screenshot({ path: path.join(jpegDir, files[i].replace(/\.png$/, '.jpg')), type: 'jpeg', quality: 92 });
    report[i].file = files[i];
  }
  await browser.close();
  console.log(JSON.stringify({ cards: report, fontsLoaded: [...new Set(loaded)] }));
})().catch((e) => { console.error(e); process.exit(1); });
