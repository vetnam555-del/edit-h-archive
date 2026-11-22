/* 연말정산 카드 공제 계산기(구독 선물 2026 연말 판, 2026-11-22 운영자 '메리트 있게끔 해 줘').
 * build_gift.py 가 이 파일을 선물 페이지에 그대로 넣고, selftest(t_card_calc)가 node 로 손계산 사례와 맞춰 본다.
 * 금액 단위는 모두 원. 근거(2026-11-22 국가법령정보센터 원문으로 확인):
 *  - 조세특례제한법 제126조의2 [법률 제21467호, 시행 2026.9.18.] — 2028.12.31 까지 사용분.
 *    ① 문턱 = 총급여의 25%  ② 공제율 신용 15% · 체크·현금영수증 30% · 전통시장 40% · 대중교통 40% ·
 *    도서·신문·공연·박물관·미술관·영화·체육시설(총급여 7천만원 이하만) 30%, 문턱은 신용 → 체크(+문화) → 40% 순으로 뺀다(제2항 제6호)
 *    ⑩ 기본 한도 7천만원 이하 300만(자녀등 1명 350·2명 이상 400), 초과 250만(275·300) — 2025.12.23 개정
 *    ⑪ 한도 넘은 몫은 전통시장+대중교통 공제액(7천만원 이하는 문화체육 더해 300만, 초과 200만 한도)만큼 더 — 2025.12.23 신설
 *    (제2항 제7호 소비증가분은 2024년 사용분에만 — 2026년엔 없다)
 *  - 소득세법 제47조(근로소득공제, 2천만원 한도) · 제55조(세율, 2022.12.31 개정 뒤 그대로) · 제59조(근로소득세액공제와 총급여별 한도)
 *    · 제59조의4 ⑨(표준세액공제 13만원) — [법률 제21221호, 시행 2026.7.1.]
 * '돌려받는 돈'은 본인 기본공제 + 자녀 기본공제, 4대보험 총급여의 9.4%(가정), 다른 공제 없음으로 대략 계산한다 — 화면에 그렇게 적는다.
 */
(function (root) {
  var MAN = 10000;

  function wageDeduction(pay) {   // 소득세법 제47조
    var d;
    if (pay <= 500 * MAN) d = pay * 0.7;
    else if (pay <= 1500 * MAN) d = 350 * MAN + (pay - 500 * MAN) * 0.4;
    else if (pay <= 4500 * MAN) d = 750 * MAN + (pay - 1500 * MAN) * 0.15;
    else if (pay <= 10000 * MAN) d = 1200 * MAN + (pay - 4500 * MAN) * 0.05;
    else d = 1475 * MAN + (pay - 10000 * MAN) * 0.02;
    return Math.min(d, 2000 * MAN, pay);
  }

  var BRACKETS = [   // 소득세법 제55조 — [이하, 세율, 그 구간까지의 세액]
    [1400 * MAN, 0.06, 0], [5000 * MAN, 0.15, 84 * MAN], [8800 * MAN, 0.24, 624 * MAN],
    [15000 * MAN, 0.35, 1536 * MAN], [30000 * MAN, 0.38, 3706 * MAN], [50000 * MAN, 0.40, 9406 * MAN],
    [100000 * MAN, 0.42, 17406 * MAN], [Infinity, 0.45, 38406 * MAN]];

  function incomeTax(base) {
    var lo = 0;
    for (var i = 0; i < BRACKETS.length; i++) {
      var b = BRACKETS[i];
      if (base <= b[0]) return b[2] + (base - lo) * b[1];
      lo = b[0];
    }
    return 0;
  }

  function wageCredit(tax, pay) {   // 소득세법 제59조
    var c = tax <= 130 * MAN ? tax * 0.55 : 71.5 * MAN + (tax - 130 * MAN) * 0.3, cap;
    if (pay <= 3300 * MAN) cap = 74 * MAN;
    else if (pay <= 7000 * MAN) cap = Math.max(74 * MAN - (pay - 3300 * MAN) * 0.008, 66 * MAN);
    else if (pay <= 12000 * MAN) cap = Math.max(66 * MAN - (pay - 7000 * MAN) * 0.5, 50 * MAN);
    else cap = Math.max(50 * MAN - (pay - 12000 * MAN) * 0.5, 20 * MAN);
    return Math.min(c, cap);
  }

  /* 카드 소득공제 — s = {pay, kids, credit, debit, market, transit, culture} (원). 조특법 제126조의2 ②⑩⑪ */
  function cardDeduction(s) {
    var pay = s.pay, low = pay <= 7000 * MAN, kids = Math.min(s.kids || 0, 2);
    var C = s.credit || 0, D = s.debit || 0, M = s.market || 0, T = s.transit || 0, K = s.culture || 0;
    if (!low) { C += K; K = 0; }   // 7천만원 초과: 문화체육 30% 없음 — 신용카드로 쓴 것으로 본다(보수적)
    var floor = pay * 0.25, used = C + D + M + T + K;
    var a1 = M * 0.4, a2 = T * 0.4, a3 = K * 0.3, a4 = D * 0.3, a5 = C * 0.15, ex;
    if (floor <= C) ex = floor * 0.15;
    else if (floor <= C + D + K) ex = C * 0.15 + (floor - C) * 0.3;
    else ex = C * 0.15 + (D + K) * 0.3 + (floor - C - D - K) * 0.4;
    var raw = Math.max(0, a1 + a2 + a3 + a4 + a5 - ex);
    var limit = (low ? [300, 350, 400] : [250, 275, 300])[kids] * MAN, ded = raw, extra = 0;
    if (raw > limit) {
      extra = Math.min(raw - limit, Math.min(a1 + a2 + a3, (low ? 300 : 200) * MAN));
      ded = limit + extra;
    }
    return {floor: floor, used: used, gap: Math.max(0, floor - used), raw: raw, limit: limit, extra: extra,
            deduction: ded, capped: raw > limit + extra};
  }

  /* 결정세액(지방소득세 10% 포함) — 대략: 본인·자녀 기본공제, 4대보험 9.4%, 근로소득세액공제, 표준세액공제 13만원 */
  function taxAfter(pay, kids, deduction) {
    var income = pay - wageDeduction(pay);
    var base = Math.max(0, income - 150 * MAN * (1 + (kids || 0)) - pay * 0.094 - deduction);
    var t = incomeTax(base);
    return Math.max(0, t - wageCredit(t, pay) - 13 * MAN) * 1.1;
  }

  /* 화면에 보여 줄 답 — s 에 rest(12월 31일까지 더 쓸 돈) */
  function plan(s) {
    var now = cardDeduction(s), rest = s.rest || 0;
    var byCredit = cardDeduction(Object.assign({}, s, {credit: (s.credit || 0) + rest}));
    var byDebit = cardDeduction(Object.assign({}, s, {debit: (s.debit || 0) + rest}));
    var none = taxAfter(s.pay, s.kids, 0);
    var refund = function (r) { return Math.round(none - taxAfter(s.pay, s.kids, r.deduction)); };
    return {now: now, byCredit: byCredit, byDebit: byDebit,
            refundNow: refund(now), refundCredit: refund(byCredit), refundDebit: refund(byDebit),
            gain: refund(byDebit) - refund(byCredit)};
  }

  var api = {wageDeduction: wageDeduction, incomeTax: incomeTax, wageCredit: wageCredit,
             cardDeduction: cardDeduction, taxAfter: taxAfter, plan: plan};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CardCalc = api;
})(this);
