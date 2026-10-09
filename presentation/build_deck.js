// 발표 자료 생성: node presentation/build_deck.js  (pptxgenjs 필요: npm install pptxgenjs)
// 내용의 원본은 docs/PPT_재료.md, 그림은 outputs/figures/eda_*.png. 수치를 여기서 새로 만들지 않는다
// 출력: presentation/AVM_발표.pptx  (제출 파일명은 제출할 때 따로 바꾼다 — 공개 저장소에 회사 이름을 남기지 않기 위해)
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..");
const FIG = (n) => path.join(ROOT, "outputs", "figures", `eda_${n}.png`);
const SUMMARY = process.argv.includes("--summary"); // 요약본: 표지 + 과제 PPT 8항목 각 1장
const OUT = path.join(__dirname, SUMMARY ? "AVM_발표_요약.pptx" : "AVM_발표.pptx");

// 색: 짙은 남색이 주(제목·강조 배경), 주황 한 가지를 강조, 그림의 권역 3색(파랑·주황·청록)과 맞춤
const COL = { navy: "1B2640", navy2: "2C3A5C", ink: "1F2328", ink2: "52514E", muted: "8A8984", line: "D9DCE3",
  tint: "F2F4F8", white: "FFFFFF", orange: "EB6834", blue: "2A78D6", aqua: "1BAF7A", red: "D03B3B" };
const FONT = "Pretendard"; // 설치돼 있지 않은 PC에서는 기본 글꼴로 바뀜 → 제출은 PDF(글꼴 포함)를 함께

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "김인석";
pres.title = "서울 다세대(빌라) 자동 시세 산정 모델";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
const W = 13.333, H = 7.5, M = 0.6;

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: COL.white },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: W - 2 * M, h: 0.8, fontFace: FONT, fontSize: 26,
      bold: true, color: COL.ink, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "kicker", type: "body", x: M, y: 0.12, w: 6, h: 0.3, fontFace: FONT, fontSize: 11,
      color: COL.orange, bold: true, margin: 0 }, text: "" } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.45, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color: COL.muted, align: "right" },
});
pres.defineSlideMaster({ title: "DARK", background: { color: COL.navy } });

// ---------------------------------------------------------------- 도구
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function img(slide, name, x, y, maxW, maxH) { // 비율 유지, 상자 안 가운데
  const f = FIG(name), s = pngSize(f);
  let w = maxW, h = (maxW * s.h) / s.w;
  if (h > maxH) { h = maxH; w = (maxH * s.w) / s.h; }
  slide.addImage({ path: f, x: x + (maxW - w) / 2, y: y + (maxH - h) / 2, w, h });
}
function content(kicker, title) { // title의 **…**은 주황으로 강조(참고 덱처럼 제목 안 핵심 한 곳)
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText(`AVM  /  ${kicker}`, { placeholder: "kicker" });
  const runs = title.split(/\*\*(.+?)\*\*/).map((t, i) => ({ text: t, options: i % 2 ? { color: COL.orange } : {} })).filter((r) => r.text);
  s.addText(runs, { placeholder: "title" });
  return s;
}
function text(slide, t, o) { slide.addText(t, { isTextBox: true, fontFace: FONT, fontSize: 14, color: COL.ink, margin: 0, valign: "top", lineSpacingMultiple: 1.2, ...o }); }
function bullets(slide, items, o) {
  slide.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: i < items.length - 1, paraSpaceAfter: 6 } })),
    { isTextBox: true, fontFace: FONT, fontSize: 14, color: COL.ink, margin: 0, valign: "top", lineSpacingMultiple: 1.2, ...o });
}
function card(slide, x, y, w, h, fill) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill || COL.tint }, line: { color: fill || COL.tint }, rectRadius: 0.08 });
}
function stat(slide, x, y, w, big, label, color) {
  card(slide, x, y, w, 1.6);
  text(slide, big, { x: x + 0.25, y: y + 0.18, w: w - 0.5, h: 0.8, fontSize: 36, bold: true, color: color || COL.navy, valign: "middle" });
  text(slide, label, { x: x + 0.25, y: y + 1.0, w: w - 0.5, h: 0.5, fontSize: 12, color: COL.ink2 });
}
function table(slide, rows, o) { // rows[0] = 머리글
  const head = rows[0].map((c) => ({ text: c, options: { bold: true, color: COL.white, fill: { color: COL.navy2 } } }));
  const body = rows.slice(1).map((r, i) => r.map((c) => (typeof c === "object" ? c : { text: String(c), options: { fill: { color: i % 2 ? COL.tint : COL.white } } })));
  slide.addTable([head, ...body], { fontFace: FONT, fontSize: 12, color: COL.ink, border: { type: "solid", pt: 0.5, color: COL.line },
    valign: "middle", margin: [3, 6, 3, 6], ...o });
}
function note(slide, t) { text(slide, t, { x: M, y: H - 0.55, w: W - 2 * M - 1, h: 0.35, fontSize: 10, color: COL.muted, valign: "middle" }); }

// 본문은 비전공자 기준(평가 항목: PPT만 보고 이해할 수 있는지) — 장마다 제목 아래 "쉽게 말하면" 한 줄, 전문 용어는 부록으로
const Y0 = 1.75; // 본문 시작
function plain(slide, t) { // 제목 아래 쉬운 한 줄
  text(slide, t, { x: M, y: 1.12, w: W - 2 * M, h: 0.45, fontSize: 15, color: COL.ink2, valign: "middle" });
}

// ---------------------------------------------------------------- 표지
{
  const s = pres.addSlide({ masterName: "DARK" });
  text(s, SUMMARY ? "데이터 분석 과제 전형  |  제출 자료 요약본" : "데이터 분석 과제 전형  |  제출 자료", { x: M + 0.2, y: 1.6, w: 10, h: 0.5, fontSize: 18, color: COL.orange, bold: true });
  text(s, "서울 다세대(빌라)\nAI 시세 산정 모델", { x: M + 0.2, y: 2.2, w: 11, h: 1.9, fontSize: 40, bold: true, color: COL.white });
  text(s, "지번·층·호를 넣으면 시세·범위·신뢰도·근거를 산출합니다  |  강서구 화곡동 · 관악구 · 강남구  |  기준일 2026-10-06(과제 안내일)", { x: M + 0.2, y: 4.35, w: 12.2, h: 0.4, fontSize: 16, color: "C9D3E6" });
  if (SUMMARY) { // 요약본은 결과를 표지에서 바로 보이게
    [["9%", "실제 가격과의 보통 오차"], ["79%", "실제 가격 ±20% 안"], ["86%", "신뢰도 0.8 초과 물건 적중률"], ["0건", "표본 20건 실행 실패"]].forEach(([n, l], i) => {
      const x = M + 0.2 + i * 2.7;
      text(s, n, { x, y: 4.95, w: 2.5, h: 0.6, fontSize: 30, bold: true, color: i === 2 ? COL.orange : COL.white });
      text(s, l, { x, y: 5.55, w: 2.5, h: 0.35, fontSize: 12, color: "C9D3E6" });
    });
  }
  text(s, "지원자 김인석", { x: M + 0.2, y: 6.2, w: 6, h: 0.4, fontSize: 16, color: COL.white });
  text(s, "github.com/KimInSeok-DA/DA_Seoul_Villa_AVM", { x: M + 0.2, y: 6.6, w: 8, h: 0.35, fontSize: 12, color: "C9D3E6" });
}

// ---------------------------------------------------------------- 한눈에 보기
if (!SUMMARY) {
  const s = content("한눈에 보기", "공시가격에서 출발해 **건물 특징으로 보정**했습니다");
  plain(s, "검증 결과, 추정값은 실제 거래가와 보통 9% 차이가 났고 10건 중 8건이 ±20% 안에 들었습니다");
  const y = Y0, w = 2.85, g = 0.25;
  stat(s, M, y, w, "9%", "실제 가격과의 보통 오차(두 검증 상황 평균)");
  stat(s, M + (w + g), y, w, "79%", "실제 가격 ±20% 안에 든 비율(두 검증 상황 평균)");
  stat(s, M + 2 * (w + g), y, w, "86%", "신뢰도 0.8 초과 물건의 ±20% 적중률", COL.orange);
  stat(s, M + 3 * (w + g), y, w, "20초", "20건 계산(기준 30분 이내)");
  const steps = [["데이터 수집", "6년 치 실거래에서 이상 거래를\n제외하고 최근 3년 1만 4천 건 사용"],
    ["기본 추정", "공시가격 × 그 동네의\n실거래 배율"], ["머신러닝 보정", "연식·층·승강기·위치 등\n공시가격이 덜 반영한 요인"],
    ["범위·신뢰도 계산", "과거 오차로 가격 범위와\n신뢰도 산출"]];
  const sy = 3.75, sw = 2.85;
  steps.forEach(([h, b], i) => {
    const x = M + i * (sw + g);
    s.addShape(pres.shapes.OVAL, { x, y: sy, w: 0.5, h: 0.5, fill: { color: COL.navy }, line: { color: COL.navy } });
    text(s, String(i + 1), { x, y: sy, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: COL.white, align: "center", valign: "middle" });
    text(s, h, { x: x + 0.65, y: sy, w: sw - 0.65, h: 0.5, fontSize: 14, bold: true, valign: "middle" });
    text(s, b, { x, y: sy + 0.65, w: sw, h: 1.0, fontSize: 12, color: COL.ink2 });
  });
  card(s, M, 5.6, W - 2 * M, 1.05);
  text(s, "크게 빗나간 경우는 대부분 직거래처럼 사정이 있을 수 있는, 시세와 다른 가격의 거래였습니다. 이런 사정은 주소만으로는 알 수 없어 한계로 정리했고, 지하층·노후 건물처럼 미리 알 수 있는 위험은 신뢰도를 낮춰 표시합니다.",
    { x: M + 0.3, y: 5.7, w: W - 2 * M - 0.6, h: 0.85, fontSize: 14, color: COL.ink, valign: "middle" });
}

// ---------------------------------------------------------------- 읽는 법
if (!SUMMARY) {
  const s = content("읽는 법", "자료를 읽는 데 필요한 **숫자 네 가지**");
  plain(s, "예시: 화곡동 빌라 한 채를 넣으면 추정 2.41억, 범위 1.99억～2.84억, 신뢰도 0.83이 나옵니다");
  // 범위 막대 그림
  const bx = M + 0.4, by = 2.3, bw = 11.3, lo = 1.99, hi = 2.84, est = 2.41, min = 1.7, max = 3.2;
  const X = (v) => bx + ((v - min) / (max - min)) * bw;
  s.addShape(pres.shapes.LINE, { x: bx, y: by + 0.35, w: bw, h: 0, line: { color: COL.line, width: 1.5 } });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: X(lo), y: by + 0.15, w: X(hi) - X(lo), h: 0.4, fill: { color: "CADBF3" }, line: { color: "CADBF3" }, rectRadius: 0.2 });
  s.addShape(pres.shapes.OVAL, { x: X(est) - 0.16, y: by + 0.19, w: 0.32, h: 0.32, fill: { color: COL.navy }, line: { color: COL.white, width: 2 } });
  text(s, "추정 2.41억", { x: X(est) - 1, y: by - 0.35, w: 2, h: 0.35, fontSize: 14, bold: true, align: "center", color: COL.navy });
  text(s, "1.99억", { x: X(lo) - 0.6, y: by + 0.65, w: 1.2, h: 0.3, fontSize: 12, align: "center", color: COL.ink2 });
  text(s, "2.84억", { x: X(hi) - 0.6, y: by + 0.65, w: 1.2, h: 0.3, fontSize: 12, align: "center", color: COL.ink2 });
  const cards = [
    ["오차율", "추정값이 실제 거래가와 몇 % 다른지를 나타냅니다. 여러 건의 가운데 값(중앙값)을 썼고, 이 모델은 약 9%입니다"],
    ["±20% 적중률", "추정값이 실제 가격의 ±20% 안에 든 비율입니다. 3억 원짜리 집이면 2.4억～3.6억이고, 이 모델은 10건 중 8건입니다"],
    ["80% 범위", "위 막대의 하한～상한입니다. 실제 가격이 10번 중 8번 들어오도록 계산했고, 검증에서는 77～83%였습니다"],
    ["신뢰도(0～1)", "추정이 ±20% 안에 들 가능성입니다. 0.8이면 비슷한 물건 10건 중 8건이 맞았다는 뜻이며, 낮을수록 주의가 필요합니다"],
  ];
  const cw = (W - 2 * M - 0.75) / 4;
  cards.forEach(([h, b], i) => {
    const x = M + i * (cw + 0.25);
    card(s, x, 3.65, cw, 2.2);
    text(s, h, { x: x + 0.25, y: 3.8, w: cw - 0.5, h: 0.4, fontSize: 17, bold: true, color: COL.navy });
    text(s, b, { x: x + 0.25, y: 4.3, w: cw - 0.5, h: 1.45, fontSize: 13 });
  });
}

// ---------------------------------------------------------------- 목차(과제 PPT 필수 8항목)
if (!SUMMARY) {
  const s = content("목차", "**8가지 항목** 순서로 구성했습니다");
  plain(s, "오른쪽 숫자는 해당 장 번호입니다. 기술 상세는 부록(24～30장)에 정리했습니다");
  const items = [["1", "기술 스택", "언어·라이브러리·모델·AI 도구·API", "5"], ["2", "데이터 소스", "출처·수집 방식·건수, 정제 방법", "6～7"],
    ["3", "시세 요인", "사용한 변수와 제외한 변수, 그 이유", "8～10"], ["4", "모델 설계", "흐름도, 13가지 방법 비교", "11～12"],
    ["5", "자체 검증", "632개 건물 검증, 신뢰도, 잘 맞힌·빗나간 사례", "13～16"], ["6", "예시 산출", "3건의 입력·출력·근거, 실제 실행 화면", "17～18"],
    ["7", "AI 활용", "단계별 역할, AI 오류와 확인 방법", "19～20"], ["8", "한계와 개선안", "개선 방향", "21"]];
  const cw = (W - 2 * M - 0.3) / 2, rh = 1.02;
  items.forEach(([n, h, d, pg], i) => {
    const x = M + Math.floor(i / 4) * (cw + 0.3), y = Y0 + (i % 4) * (rh + 0.12);
    card(s, x, y, cw, rh, i % 2 ? COL.white : COL.tint);
    text(s, n.padStart(2, "0"), { x: x + 0.25, y, w: 0.8, h: rh, fontSize: 24, bold: true, color: COL.orange, valign: "middle" });
    text(s, h, { x: x + 1.1, y: y + 0.17, w: cw - 2.3, h: 0.4, fontSize: 17, bold: true, color: COL.navy });
    text(s, d, { x: x + 1.1, y: y + 0.55, w: cw - 2.3, h: 0.35, fontSize: 12, color: COL.ink2 });
    text(s, pg, { x: x + cw - 1.2, y, w: 0.95, h: rh, fontSize: 16, bold: true, color: COL.navy, align: "right", valign: "middle" });
  });
}

// ---------------------------------------------------------------- 1. 기술 스택
{
  const s = content("1  기술 스택", "Python으로 **수집부터 추정까지** 구현했습니다");
  plain(s, `데이터는 공공데이터포털·VWorld 등 공공 API에서 직접 수집했습니다${SUMMARY ? "" : "(버전·출처 상세는 부록 B)"}`);
  const items = [["언어", "Python", "수집·분석·실행을 한 언어로"], ["데이터 처리", "pandas · numpy", "표 데이터 결합과 정제"],
    ["머신러닝", "XGBoost · scikit-learn", "여러 방법 비교 후 최종 모델 선정"], ["공공 데이터", "공공데이터포털·VWorld", "실거래가, 공시가격, 건축물대장, 좌표"],
    ["시각화·기록", "Jupyter·matplotlib·Git", "분석 노트북, 그래프, 작업 이력 공개"], ["AI 도구", "Claude Code", "코드 작성·점검·문서화 보조(7번 항목)"]];
  const cw = (W - 2 * M - 0.5) / 3, ch = 2.35;
  items.forEach(([k, v, d], i) => {
    const x = M + (i % 3) * (cw + 0.25), y = Y0 + Math.floor(i / 3) * (ch + 0.25);
    card(s, x, y, cw, ch, i === 5 ? "FBEDE7" : COL.tint);
    text(s, k, { x: x + 0.3, y: y + 0.25, w: cw - 0.6, h: 0.35, fontSize: 13, color: i === 5 ? COL.orange : COL.ink2, bold: true });
    text(s, v, { x: x + 0.3, y: y + 0.7, w: cw - 0.6, h: 0.55, fontSize: 20, bold: true, color: COL.navy });
    text(s, d, { x: x + 0.3, y: y + 1.4, w: cw - 0.6, h: 0.8, fontSize: 13 });
  });
}

// ---------------------------------------------------------------- 2. 데이터 소스
{
  const s = content("2  데이터 소스", "공공 데이터 **8가지**를 주소(지번) 기준으로 연결했습니다");
  plain(s, `건축물대장은 현행·말소, 코드는 법정동·행정동 각 2종이라 카드 6장에 8가지입니다. 다세대와 연립을 모두 포함했습니다${SUMMARY ? "" : "(상세는 부록 B)"}`);
  const items = [
    ["실거래가", "실제 거래 가격", "2020-10 ~ 2026-10 매매 36,997건"], ["공시가격", "정부가 매긴 호별 가격", "2026년, 107,236호"],
    ["건축물대장(현행·말소)", "사용승인일·승강기·층수, 철거 여부", "9,928개 지번 + 말소 49,074지번"], ["필지 좌표·땅값", "위치 좌표와 ㎡당 공시지가", "3개 구 123,615필지"],
    ["지하철역", "가장 가까운 역까지 거리", "275개 역"], ["법정동·행정동 코드", "주소를 고유번호(PNU)로 변환", "30개 법정동, 행정동 63개 연결"],
  ];
  const cw = (W - 2 * M - 0.5) / 3, ch = 1.95;
  items.forEach(([k, q, n], i) => {
    const x = M + (i % 3) * (cw + 0.25), y = Y0 + Math.floor(i / 3) * (ch + 0.25);
    card(s, x, y, cw, ch);
    text(s, k, { x: x + 0.3, y: y + 0.22, w: cw - 0.6, h: 0.45, fontSize: 20, bold: true, color: COL.navy });
    text(s, q, { x: x + 0.3, y: y + 0.75, w: cw - 0.6, h: 0.4, fontSize: 14 });
    text(s, n, { x: x + 0.3, y: y + 1.25, w: cw - 0.6, h: 0.4, fontSize: 13, color: COL.ink2 });
  });
  text(s, "좌표는 지도 서비스(Kakao 등) 대신 정부 연속지적도에서 받았습니다. 지도 서비스는 약관상 결과를 저장할 수 없기 때문입니다.",
    { x: M, y: 6.2, w: W - 2 * M, h: 0.55, fontSize: 13, color: COL.ink2 });
}

// ---------------------------------------------------------------- 2. 정제
if (!SUMMARY) {
  const s = content("2  데이터 다듬기", "이상 거래를 제외하고 **최근 3년** 거래로 학습했습니다");
  plain(s, "계약 취소, 시세와 동떨어진 가격(가족 간 거래 등), 철거된 옛 건물의 거래를 걸러 냈습니다");
  const steps = [["36,997", "받은 매매 거래"], ["−2,188", "계약이 취소된 거래"], ["−331", "공시가격보다 지나치게 낮은 거래\n(가족 간 거래 등으로 추정)"],
    ["−1,115", "철거된 옛 건물의 거래,\n여러 호를 한꺼번에 판 거래"], ["33,363", "정제 후 거래"], ["14,401", "학습에 쓴 최근 3년"]];
  steps.forEach(([n, l], i) => {
    const y = Y0 + i * 0.83, dark = i === 0 || i >= 4;
    card(s, M, y, 4.3, 0.72, dark ? COL.navy : COL.tint);
    text(s, n, { x: M + 0.2, y, w: 1.4, h: 0.72, fontSize: 20, bold: true, color: dark ? COL.white : COL.orange, valign: "middle" });
    text(s, l, { x: M + 1.65, y, w: 2.55, h: 0.72, fontSize: 12, color: dark ? COL.white : COL.ink, valign: "middle" });
  });
  img(s, "A1_monthly_volume", M + 4.6, Y0 - 0.05, 7.55, 3.25);
  bullets(s, [
    "거래량은 2021년에 가장 많았고 2023년까지 크게 줄었습니다. 시장 상황이 달라 오래된 거래는 현재 시세와 잘 맞지 않습니다",
    "학습 기간 3년·5년·6년을 같은 방식으로 검증한 결과, 최근 3년이 가장 정확했습니다(처음 보는 건물 기준 적중 10건 중 7.5건 → 8건)",
  ], { x: M + 4.8, y: 5.15, w: 7.3, h: 1.6, fontSize: 13 });
}

// ---------------------------------------------------------------- 3. 시세 요인 ① 공시가격
if (!SUMMARY) {
  const s = content("3  시세 요인", "공시가격 하나로 실제 가격 차이의 **87%**를 설명할 수 있습니다");
  plain(s, "그래서 공시가격을 추정의 출발점으로 삼았습니다. 실거래가는 보통 공시가격의 1.76배입니다");
  img(s, "B1_price_vs_public", M, Y0 - 0.1, 5.0, 4.9);
  img(s, "B2_r2_single_features", M + 5.3, Y0 - 0.1, 6.8, 2.95);
  bullets(s, [
    "왼쪽: 점 하나가 거래 1건입니다. 공시가격이 높을수록 실거래가도 높아 점들이 한 줄로 모입니다",
    "오른쪽: 요인별 설명력입니다. 공시가격 하나(87%)가 면적·지역·땅값·연식·역·층을 함께 넣은 선형 회귀(72%)보다 큽니다",
    "공시가격은 정부가 위치·면적·층·연식을 따져 호마다 매긴 가격이라 이미 많은 정보를 담고 있습니다",
  ], { x: M + 5.5, y: 4.85, w: 6.6, h: 2.0, fontSize: 13 });
}

// ---------------------------------------------------------------- 3. 시세 요인 ② 공시가격이 놓치는 것
if (!SUMMARY) {
  const s = content("3  시세 요인", "공시가격이 덜 반영하는 요인: **노후 건물과 저층**");
  plain(s, "공시가격이 같아도 노후 건물·지하·1층은 공시가격 대비 더 높게 거래됩니다. 이 차이를 머신러닝으로 보정했습니다");
  img(s, "C1_age", M, Y0 - 0.05, 7.4, 2.6);
  img(s, "C2_floor", M, Y0 + 2.6, 7.4, 2.6);
  card(s, M + 7.7, Y0, 4.43, 5.0);
  bullets(s, [
    "왼쪽 그래프: 새 건물일수록 ㎡당 가격이 높습니다",
    "오른쪽 그래프: 그러나 '실거래가 ÷ 공시가격' 배율은 노후 건물이 더 높습니다(강남 1.77배 → 2.12배). 재개발 기대가 공시가격에 덜 반영된 것으로 보입니다",
    "지하층의 ㎡당 가격은 지상의 54～59%이고, 배율은 지하·1층이 높습니다",
    "이 차이를 연식·층·승강기·면적·위치 정보로 보정합니다",
  ], { x: M + 7.95, y: Y0 + 0.25, w: 3.95, h: 4.6, fontSize: 13 });
}

// ---------------------------------------------------------------- 3. 쓴 변수·버린 변수
{
  const s = content("3  시세 요인", "사용한 정보와 제외한 정보: **주소와 층으로 알 수 있는 것만** 사용했습니다");
  plain(s, "추정 시점에 알 수 없는 정보(예: 직거래 여부)는 가격에 영향이 커도 사용할 수 없습니다");
  const colW = (W - 2 * M - 0.3) / 2;
  card(s, M, Y0, colW, 4.0);
  text(s, "사용한 정보", { x: M + 0.3, y: Y0 + 0.15, w: 4, h: 0.4, fontSize: 18, bold: true, color: COL.navy });
  bullets(s, [
    "공시가격, 동네 실거래 배율, 시기별 시세 변화",
    "연식 · 층(지하·꼭대기 층 여부) · 건물 층수 · 전용면적",
    "승강기 · 세대수 · 세대당 주차",
    "지하철역 거리 · 땅값 · 위치(좌표) · 지역",
    "머신러닝 중요도가 높은 정보: 연식 · 지역 · 층 · 건물 층수 · 면적 · 위치",
  ], { x: M + 0.3, y: Y0 + 0.7, w: colW - 0.6, h: 3.2, fontSize: 14 });
  const x2 = M + colW + 0.3;
  card(s, x2, Y0, colW, 4.0, "FBEDE7");
  text(s, "제외한 정보와 이유", { x: x2 + 0.3, y: Y0 + 0.15, w: 5, h: 0.4, fontSize: 18, bold: true, color: COL.orange });
  bullets(s, [
    "직거래 여부, 매도·매수인 정보: 추정 시점에 알 수 없음",
    "전월세: 전세금은 매매가와 성격이 다름",
    "건축년도: 연식과 중복 / 동 수: 세대수와 거의 중복",
    "건물 구조: 90%가 철근콘크리트라 구별력이 없음",
    "학교·공원 거리: 기간 내 반영하지 못함(개선안)",
  ], { x: x2 + 0.3, y: Y0 + 0.7, w: colW - 0.6, h: 3.2, fontSize: 14 });
}

// ---------------------------------------------------------------- 4. 모델 흐름도
{
  const s = content("4  모델 설계", "주소 한 줄이 **시세·범위·신뢰도·근거**가 되는 과정");
  plain(s, "실행할 때마다 저장된 거래로 다시 계산하므로, 새 거래를 정제 데이터에 추가하고 다시 실행하면 반영됩니다");
  const boxes = [
    ["① 입력", "구·동·지번·층\n호·면적(빈칸 허용)", COL.tint], ["② 주소 확인", "고유번호(PNU)로 변환\n권역 밖이면 사유와 함께 실패 처리", COL.tint],
    ["③ 공시가격 찾기", "수집 데이터에 없으면\n실행 중 공공 API 조회", COL.tint], ["④ 기본 추정", "공시가격 × 실거래 배율\n(같은 건물 거래 우선)", COL.navy],
    ["⑤ 머신러닝 보정", "연식·층·위치 등으로\n기본 추정 보정", COL.navy], ["⑥ 추정값", "보정한 두 값의 평균", COL.navy],
    ["⑦ 범위·신뢰도", "비슷한 물건의 과거 오차로\n80% 범위·신뢰도 산출", COL.orange], ["⑧ 출력", "추정·하한·상한·신뢰도\n근거 한 줄", COL.tint],
  ];
  const bw = 2.75, bh = 1.45, gx = 0.37;
  boxes.forEach(([h, b, fill], i) => {
    const row = i < 4 ? 0 : 1, col = row === 0 ? i : 7 - i;
    const x = M + col * (bw + gx), y = row === 0 ? 1.85 : 4.35;
    const dark = fill !== COL.tint;
    card(s, x, y, bw, bh, fill);
    text(s, h, { x: x + 0.2, y: y + 0.12, w: bw - 0.4, h: 0.4, fontSize: 15, bold: true, color: dark ? COL.white : COL.navy });
    text(s, b, { x: x + 0.2, y: y + 0.55, w: bw - 0.4, h: 0.85, fontSize: 12, color: dark ? COL.white : COL.ink2 });
    if (row === 0 && col < 3) s.addShape(pres.shapes.LINE, { x: x + bw + 0.05, y: y + bh / 2, w: gx - 0.1, h: 0, line: { color: COL.muted, width: 1.5, endArrowType: "triangle" } });
    if (row === 1 && col > 0) s.addShape(pres.shapes.LINE, { x: x - gx + 0.05, y: y + bh / 2, w: gx - 0.1, h: 0, line: { color: COL.muted, width: 1.5, beginArrowType: "triangle" } });
  });
  const lastX = M + 3 * (bw + gx) + bw / 2;
  s.addShape(pres.shapes.LINE, { x: lastX, y: 1.85 + bh + 0.05, w: 0, h: 4.35 - 1.85 - bh - 0.1, line: { color: COL.muted, width: 1.5, endArrowType: "triangle" } });
  text(s, "⑤의 두 값은 건물 특징만으로 직접 낸 가격과, ④가 빗나갈 정도를 예측해 고친 가격입니다. 장단점이 달라 두 값의 평균을 씁니다",
    { x: M, y: 6.15, w: W - 2 * M, h: 0.5, fontSize: 13, color: COL.ink2 });
}

// ---------------------------------------------------------------- 4. 모델 고르기
if (!SUMMARY) {
  const s = content("4  모델 설계", "13가지 방법을 같은 조건으로 비교해 **가장 안정적인 방법**을 선택했습니다");
  plain(s, "검증 방식: 일부 건물을 따로 떼어 두고, 나머지로 학습한 뒤 떼어 둔 건물의 실거래가를 맞혔습니다");
  s.addChart(pres.charts.BAR, [{ name: "±20% 적중률", labels: ["기본 추정", "선형 회귀", "비슷한 거래 평균", "랜덤포레스트", "XGBoost(선택)"],
    values: [73.7, 73.7, 77.1, 77.2, 78.6] }], {
    x: M, y: Y0, w: 6.2, h: 4.7, barDir: "bar", chartColors: ["9FB4D9", "9FB4D9", "9FB4D9", "9FB4D9", COL.navy],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0\"%\"", dataLabelFontSize: 12, dataLabelColor: COL.ink2,
    dataLabelFontFace: "+mn-lt", catAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 12, catAxisLabelColor: COL.ink,
    valAxisHidden: true, valAxisMinVal: 60, valAxisMaxVal: 82, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    showLegend: false, showTitle: true, title: "방법마다 가장 좋은 계산 방식의 ±20% 적중률(과거 거래가 있는 건물)",
    titleFontSize: 12, titleColor: COL.ink2, titleFontFace: "+mn-lt", barGapWidthPct: 60,
  });
  table(s, [
    ["구분", "내용"],
    ["후보", "선형 회귀 · 비슷한 거래 평균 · 랜덤포레스트 · XGBoost\n× 계산 방식 3가지 + 기본 추정 = 13가지"],
    ["검증 상황", "① 처음 보는 건물\n② 과거 거래가 있는 건물\n③ 1년 전 모델로 1년 뒤 예측"],
    ["데이터 분리", "건물 단위로 분리\n(같은 건물이 학습·검증에 섞이면 성적이 부풀려짐)"],
    ["선정 기준", "결과를 보기 전에 확정\n2,000회 재표본으로 차이가 우연인지 확인"],
    [{ text: "선택", options: { bold: true, color: COL.navy, fill: { color: "E3EAF6" } } },
     { text: "XGBoost(두 방식의 평균): 세 상황 모두 상위권\n랜덤포레스트 잔차 방식은 한 상황 78.8%였으나 다른 상황에서 순위가 낮음", options: { bold: true, color: COL.navy, fill: { color: "E3EAF6" } } }],
  ], { x: M + 6.5, y: Y0, w: W - 2 * M - 6.5, colW: [1.25, W - 2 * M - 6.5 - 1.25], fontSize: 12, rowH: [0.4, 0.75, 0.9, 0.75, 0.75, 0.95] });
  note(s, "기술 용어(GroupKFold·그리드서치·부트스트랩)와 상세 결과는 부록 D · 그래프는 학습 기간 6년으로 비교할 당시의 값");
}

// ---------------------------------------------------------------- 5. 자체 검증
if (!SUMMARY) {
  const s = content("5  자체 검증", "학습에 쓰지 않은 632개 건물로 검증한 결과, **10건 중 8건이 ±20% 안**에 들었습니다");
  plain(s, "최근 1년 거래가 있는 건물 3,159개 중 632개를 미리 떼어 두고, 건물마다 가장 최근 거래가를 맞혔습니다");
  const hi = (t) => ({ text: t, options: { bold: true, color: COL.navy, fill: { color: "E3EAF6" } } });
  table(s, [
    ["검증 상황", "보통 오차(중앙값)", "±20% 안에 든 비율", "실제 가격이 80% 범위 안에 든 비율"],
    ["처음 보는 건물", hi("9.4%"), hi("78.5%"), "82.9%"],
    ["과거 거래가 있는 건물", hi("8.6%"), hi("80.1%"), "80.7%"],
    ["(비교) 기본 추정만 사용", "11.1% / 10.7%", "71.7% / 73.9%", "69.8% / 67.7%"],
  ], { x: M, y: Y0, w: W - 2 * M, colW: [3.6, 2.8, 2.6, 3.133], fontSize: 15, rowH: 0.62 });
  const cols = [["강서 화곡동", "8.4%", "80%"], ["관악구", "8.3%", "84%"], ["강남구", "9.7%", "73%"]];
  text(s, "지역별 결과(과거 거래가 있는 건물): 보통 오차 · ±20% 적중", { x: M, y: 4.45, w: 7, h: 0.35, fontSize: 13, bold: true, color: COL.navy });
  cols.forEach(([g, a, b], i) => {
    const x = M + i * 2.6;
    card(s, x, 4.9, 2.4, 1.2);
    text(s, g, { x: x + 0.2, y: 5.0, w: 2.0, h: 0.3, fontSize: 13, color: COL.ink2 });
    text(s, `${a}  ·  ${b}`, { x: x + 0.2, y: 5.35, w: 2.1, h: 0.55, fontSize: 18, bold: true, color: COL.navy });
  });
  card(s, M + 7.9, 4.9, 4.23, 1.2, "E3EAF6");
  text(s, "처음 세운 목표(보통 오차 10% 이하, ±20% 적중 75% 이상, 범위 포함 70～90%)를 모두 달성했습니다",
    { x: M + 8.1, y: 5.0, w: 3.9, h: 1.0, fontSize: 13, color: COL.ink, valign: "middle" });
  note(s, "자체 검증은 대상 거래를 뺀 조건이라 보수적인 수치이며, 실제 물건의 거래가 수집 데이터에 있으면 일반 비교사례로 쓰입니다 · 면적 빈칸·MAPE 등 상세는 부록 C");
}

// ---------------------------------------------------------------- 5. 신뢰도
if (!SUMMARY) {
  const s = content("5  자체 검증", "신뢰도가 높은 물건일수록 **오차가 작았습니다**");
  plain(s, "보통 오차는 신뢰도 0.6 이하 물건 17%, 0.8 초과 물건 7%이고, ±20% 적중률은 62%에서 86%로 높아졌습니다");
  img(s, "D1_pred_vs_actual_reliability", M, Y0 - 0.1, 8.2, 5.1);
  card(s, M + 8.45, Y0, 3.68, 1.75, COL.navy);
  text(s, "가장 높은 신뢰도 0.88", { x: M + 8.7, y: Y0 + 0.15, w: 3.2, h: 0.35, fontSize: 13, bold: true, color: "C9D3E6" });
  text(s, "174건 중 91% 적중", { x: M + 8.7, y: Y0 + 0.5, w: 3.2, h: 0.55, fontSize: 24, bold: true, color: COL.white });
  text(s, "보통 오차 7.0% (과거 거래가 있는 건물)", { x: M + 8.7, y: Y0 + 1.1, w: 3.2, h: 0.4, fontSize: 12, color: "C9D3E6" });
  card(s, M + 8.45, Y0 + 1.95, 3.68, 2.9);
  bullets(s, [
    "왼쪽: 대각선 띠(±20%) 안의 점이 많을수록 정확합니다. 632건 중 80%가 띠 안에 있습니다",
    "오른쪽: 표시한 신뢰도와 실제 적중률이 거의 같습니다(0.56→62%, 0.77→77%, 0.86→86%)",
    "동네 가격 편차가 크거나 소형·강남·지하층·노후 건물이면 신뢰도를 낮게 계산합니다",
  ], { x: M + 8.7, y: Y0 + 2.15, w: 3.2, h: 2.6, fontSize: 12 });
}

// ---------------------------------------------------------------- 5. 잘 맞힌 사례
if (!SUMMARY) {
  const s = content("5  자체 검증", "잘 맞힌 경우: 검증 건물의 **30%는 오차 5% 이내**였습니다");
  plain(s, "632건 중 192건이 실거래가 ±5% 안에 들었습니다. 아래는 권역별로 오차가 가장 작았던 중개거래입니다");
  stat(s, M, Y0, 3.4, "30%", "오차 5% 이내(632건 중 192건)", COL.orange);
  stat(s, M, Y0 + 1.8, 3.4, "91%", "가장 높은 신뢰도(0.88) 174건의 ±20% 적중률");
  table(s, [
    ["물건", "실거래가*", "추정", "차이", "신뢰도", "근거"],
    ["강서 화곡동 57.31㎡ 1층", "2.07억", "2.07억", "−0.1%", "0.88", "같은 건물 거래, 보정 +9%"],
    ["강서 화곡동 23.59㎡ 4층", "2.01억", "2.01억", "+0.1%", "0.83", "같은 건물 거래 3건, 보정 −6%"],
    ["관악 신림동 59.93㎡ 4층", "3.60억", "3.60억", "0.0%", "0.83", "같은 건물 거래 없이 동네 비율만"],
    ["관악 봉천동 45.13㎡ 2층", "3.01억", "3.01억", "−0.1%", "0.88", "같은 건물 거래, 보정 −3%"],
    ["강남 청담동 90.12㎡ 1층", "19.11억", "19.18억", "+0.4%", "0.58", "기본 추정 15.6억, 보정 +23%"],
    ["강남 개포동 54.55㎡ 3층", "6.74억", "6.78억", "+0.6%", "0.69", "동네 비율, 보정 +4%"],
  ], { x: M + 3.7, y: Y0, w: 8.43, colW: [2.35, 1.0, 1.0, 0.8, 0.8, 2.48], fontSize: 12, rowH: 0.42 });
  bullets(s, [
    "같은 건물의 최근 거래나 거래가 많은 동네의 비율이 있으면 기본 추정이 안정적이었습니다",
    "청담동 19억 원대 주택은 기본 추정(15.6억)이 낮았지만, 머신러닝 보정이 23% 올려 0.4% 차이로 맞혔습니다",
    "잘 맞은 물건이라도 강남·노후 조건이면 신뢰도를 낮게 표시합니다. 신뢰도는 결과가 아니라 조건으로 정해집니다",
  ], { x: M + 3.85, y: 5.0, w: 8.2, h: 1.7, fontSize: 13 });
  note(s, "* 기준일 환산 실거래가 · 0%대 오차는 우연도 작용하므로 전체 성적은 13장 표가 기준입니다 · 출처: outputs/calibration_holdout_preds.csv(과거 거래가 있는 건물, 면적 입력)");
}

// ---------------------------------------------------------------- 5. 크게 틀린 사례
if (!SUMMARY) {
  const s = content("5  자체 검증", "크게 빗나간 경우는 대부분 **시세와 다른 가격에 거래된 집**이었습니다");
  plain(s, "직거래처럼 사정이 있을 수 있는 거래는 주소만으로 알 수 없어 모델의 한계로 정리했습니다");
  stat(s, M, Y0, 3.4, "78%", "±20%를 벗어난 126건 중 공시가격 대비 유난히 싸거나 비싸게 거래된 비율", COL.orange);
  stat(s, M, Y0 + 1.8, 3.4, "11 / 15", "오차가 가장 큰 15건 중 직거래");
  table(s, [
    ["물건", "실거래가*", "추정", "차이", "추정 원인"],
    ["강남 대치동 24.67㎡ 5층", "1.80억", "3.87억", "+115%", "공시가격과 거의 같은 값에 거래"],
    ["강남 청담동 37.2㎡ 2층", "3.89억", "7.41억", "+91%", "직거래, 공시가격보다 싸게"],
    ["관악 봉천동 60.09㎡ 3층", "2.10억", "3.82억", "+82%", "직거래"],
    ["관악 봉천동 68.67㎡ 1층", "1.84억", "3.32억", "+80%", "직거래, 34년 된 건물"],
    ["강서 화곡동 30.00㎡ 7층", "1.24억", "2.19억", "+76%", "직거래, 공시가격보다 싸게"],
  ], { x: M + 3.7, y: Y0, w: 8.43, colW: [2.6, 1.15, 1.0, 0.85, 2.83], fontSize: 12, rowH: 0.45 });
  bullets(s, [
    "직거래(검증 대상의 10%)는 보통 오차가 22%입니다. 거래 당사자 간 사정이 가격에 반영된 것으로 보입니다",
    "지하층·노후 건물은 미리 알 수 있어 신뢰도를 낮춰 표시합니다",
    "비싼 집은 조금 낮게, 싼 집은 조금 높게 추정하는 경향이 있습니다(강남이 보통 5% 낮게 나오는 이유)",
  ], { x: M + 3.85, y: 4.75, w: 8.2, h: 2.0, fontSize: 13 });  note(s, "* 실거래가는 시점 지수로 기준일(2026-10-06) 가격으로 환산한 값(신고 금액과 조금 다름) · 출처: docs/의사결정/1007_13_오차_분석.md, outputs/error_top_cases.csv");
}

// ---------------------------------------------------------------- 요약본 5. 자체 검증(검증표 + 신뢰도 + 크게 빗나간 사례)
if (SUMMARY) {
  const s = content("5  자체 검증", "학습에 쓰지 않은 632개 건물로 검증: **보통 오차 9%, 10건 중 8건이 ±20% 안**");
  plain(s, "최근 1년 거래가 있는 건물 3,159개 중 632개를 미리 떼어 두고, 건물마다 가장 최근 거래가를 맞혔습니다");
  const hi = (t) => ({ text: t, options: { bold: true, color: COL.navy, fill: { color: "E3EAF6" } } });
  table(s, [
    ["검증 상황(632건)", "보통 오차(중앙값)", "MAPE", "±20% 적중", "80% 범위 포함"],
    ["처음 보는 건물", hi("9.4%"), "13.7%", hi("78.5%"), "82.9%"],
    ["과거 거래가 있는 건물", hi("8.6%"), "13.0%", hi("80.1%"), "80.7%"],
    ["(비교) 기본 추정만 사용", "11.1% / 10.7%", "15.8% / 14.7%", "71.7% / 73.9%", "69.8% / 67.7%"],
  ], { x: M, y: Y0, w: 7.6, colW: [2.1, 1.45, 1.35, 1.35, 1.35], fontSize: 12, rowH: 0.5 });
  card(s, M + 7.9, Y0, W - 2 * M - 7.9, 2.0, COL.navy);
  text(s, "신뢰도가 높을수록 오차가 작음", { x: M + 8.15, y: Y0 + 0.15, w: 3.8, h: 0.35, fontSize: 13, bold: true, color: "C9D3E6" });
  text(s, "보통 오차 17% → 7%", { x: M + 8.15, y: Y0 + 0.55, w: 3.8, h: 0.55, fontSize: 24, bold: true, color: COL.white });
  text(s, "신뢰도 0.6 이하 → 0.8 초과, ±20% 적중 62% → 86%", { x: M + 8.15, y: Y0 + 1.2, w: 3.8, h: 0.6, fontSize: 12, color: "C9D3E6" });
  text(s, "오차가 컸던 사례와 원인", { x: M, y: 4.0, w: 6, h: 0.35, fontSize: 14, bold: true, color: COL.navy });
  table(s, [
    ["물건", "실거래가*", "추정", "차이", "추정 원인"],
    ["강남 청담동 37.2㎡ 2층", "3.89억", "7.41억", "+91%", "직거래, 공시가격보다 싸게"],
    ["관악 봉천동 60.09㎡ 3층", "2.10억", "3.82억", "+82%", "직거래"],
    ["강서 화곡동 30.00㎡ 7층", "1.24억", "2.19억", "+76%", "직거래, 공시가격보다 싸게"],
  ], { x: M, y: 4.4, w: 7.6, colW: [2.3, 1.1, 1.0, 0.8, 2.4], fontSize: 11, rowH: 0.42 });
  card(s, M + 7.9, 4.0, W - 2 * M - 7.9, 2.5);
  bullets(s, [
    "±20%를 벗어난 126건 중 78%가 공시가격 대비 유난히 싸거나 비싸게 거래된 집이었습니다",
    "오차 상위 15건 중 11건이 직거래로, 거래 사정은 주소만으로 알 수 없어 한계로 정리했습니다",
  ], { x: M + 8.15, y: 4.2, w: 3.75, h: 2.2, fontSize: 12 });
  note(s, "* 기준일 환산 실거래가 · 면적 입력 기준, 비교 행은 처음 보는 건물 / 과거 거래가 있는 건물 · 상세는 본편 13～16장과 부록 C");
}

// ---------------------------------------------------------------- 6. 예시 산출
{
  const s = content("6  예시 산출", "권역별 예시 3건: 호 입력, **면적 빈칸, 지하층**");
  plain(s, "강서구 화곡동·관악구·강남구에서 1건씩, 입력 조건을 다르게 골라 실제 출력을 옮겼습니다");
  const ex = [
    ["강서 화곡동 354-41", "2층 203호 · 34.01㎡", "2.41억", "1.99 ~ 2.84억", "0.83", "공시가격 1.34억 × 실거래 배율 1.78(같은 건물 거래 2건 + 동네) = 2.38억, 건물 특징 보정 +1%", "−13.4%"],
    ["관악 봉천동 898-9", "3층 · 면적 빈칸", "2.45억", "2.04 ~ 2.95억", "0.83", "공시가격 1.28억 × 배율 1.88 = 2.40억, 보정 +2%. 빈 면적은 공시가격 자료(39.76㎡)로 채움", "+6.3%"],
    ["강남 일원동 661-1", "지하 1층 · 49.08㎡", "5.45억", "4.00 ~ 7.95억", "0.58", "공시가격 2.05억 × 배율 2.42 = 4.96억, 보정 +10%. 지하·강남이라 신뢰도가 낮고 범위가 넓음", "−13.7%"],
  ];
  const cw = (W - 2 * M - 0.5) / 3;
  ex.forEach(([addr, cond, est, rng, conf, basis, err], i) => {
    const x = M + i * (cw + 0.25), y = Y0;
    card(s, x, y, cw, 4.95);
    text(s, addr, { x: x + 0.25, y: y + 0.2, w: cw - 0.5, h: 0.4, fontSize: 16, bold: true, color: COL.navy });
    text(s, cond, { x: x + 0.25, y: y + 0.6, w: cw - 0.5, h: 0.35, fontSize: 13, color: COL.ink2 });
    text(s, est, { x: x + 0.25, y: y + 1.0, w: cw - 0.5, h: 0.7, fontSize: 34, bold: true, color: COL.ink });
    text(s, `80% 범위 ${rng}`, { x: x + 0.25, y: y + 1.75, w: cw - 0.5, h: 0.35, fontSize: 13 });
    text(s, `신뢰도 ${conf}`, { x: x + 0.25, y: y + 2.1, w: cw - 0.5, h: 0.35, fontSize: 13, bold: true, color: conf < "0.7" ? COL.orange : COL.navy });
    text(s, "근거", { x: x + 0.25, y: y + 2.6, w: cw - 0.5, h: 0.3, fontSize: 11, color: COL.muted });
    text(s, basis, { x: x + 0.25, y: y + 2.9, w: cw - 0.5, h: 1.2, fontSize: 12, color: COL.ink });
    text(s, `참고: 이 집의 최근 실거래를 빼고 계산했을 때 오차 ${err}`, { x: x + 0.25, y: y + 4.2, w: cw - 0.5, h: 0.6, fontSize: 11, color: COL.ink2 });
  });
  note(s, "실제 출력의 근거 문장은 더 자세합니다(outputs/example_output.csv). 특정 물건의 답을 저장해 두는 방식은 쓰지 않았습니다");
}

// ---------------------------------------------------------------- 6. 실제 실행 화면(캡처)
if (!SUMMARY) {
  const s = content("6  예시 산출", "과제 명령 한 줄로 실행하며, **잘못된 입력은 사유를 남기고 넘어갑니다**");
  plain(s, "앞 장의 3건에 행정동 입력 1건과 잘못된 입력 6건을 섞어 실제로 실행한 화면입니다");
  const f = path.join(__dirname, "run_errors.png"), z = pngSize(f);
  const iw = 7.6, ih = (iw * z.h) / z.w;
  s.addImage({ path: f, x: M, y: Y0, w: iw, h: ih });
  const x2 = M + iw + 0.3, w2 = W - M - x2;
  table(s, [
    ["실패 사유(basis)", "입력 예"],
    ["권역 밖", "다른 구(마포구), 강서구의 화곡동 외 동"],
    ["주소 해석 불가: 동", "없는 동 이름"],
    ["주소 해석 불가: 지번", "숫자가 아닌 지번(abc)"],
    ["주소 해석 불가: 필지 없음", "존재하지 않는 지번(9999-99)"],
    ["층 해석 불가", "'옥탑'처럼 숫자가 아닌 층"],
  ], { x: x2, y: Y0, w: w2, colW: [2.2, w2 - 2.2], fontSize: 11, rowH: 0.4 });
  bullets(s, [
    "1～3번은 앞 장 예시와 같은 결과이고, 4번은 행정동 이름(낙성대동)을 법정동으로 바꿔 처리했습니다",
    "실패 행도 출력 파일에 입력과 같은 순서로 남아 입력과 1:1로 대응합니다",
    "값을 임의로 만들거나 실행이 멈추지 않습니다",
  ], { x: x2, y: Y0 + 2.7, w: w2, h: 2.2, fontSize: 12 });
  note(s, "Windows Terminal 실행 화면(2026-10-08) · 입력 tests/demo_errors_input.csv · 근거(basis) 전문은 outputs/example_output.csv");
}

// ---------------------------------------------------------------- 7. AI 활용 ①
if (!SUMMARY) {
  const s = content("7  AI 활용", "코드는 AI와 함께 작성했고, **방향과 검증은 제가 판단**했습니다");
  plain(s, "사용한 AI 도구는 Claude Code이며, 단계마다 역할을 나눠 활용했습니다");
  card(s, M, Y0, 4.1, 4.3);
  text(s, "AI 작업 규칙을 문서로 관리", { x: M + 0.3, y: Y0 + 0.15, w: 3.6, h: 0.4, fontSize: 16, bold: true, color: COL.navy });
  bullets(s, [
    "수치는 실제 실행 결과만 사용, 데이터 결합 때마다 건수 대조, 상용 시세 사용 금지",
    "결정마다 선택지와 근거를 기록(24건)",
    "작업 이력을 매일 기록해 다음 날 이어서 진행",
    "AI 결과는 직접 확인한 뒤 반영(PR 20건 이상)",
  ], { x: M + 0.3, y: Y0 + 0.7, w: 3.6, h: 3.5, fontSize: 13 });
  table(s, [
    ["단계", "AI가 한 일", "제가 판단·결정한 것"],
    ["설계", "과제 요약, 감정평가 방식을 모델에 연결", "마감·기준일 해석, 검증 물건의 과거 거래도 일반 비교사례로 사용(특정 물건 분기 금지)"],
    ["수집", "정부 API 응답 확인, 수집 코드", "수집 범위 결정, 약관 문제 데이터 교체"],
    ["다듬기", "중복·표기·이상한 거래를 걸러 내는 규칙", "제외 기준(낮은 이상치만 제외)"],
    ["모델", "검증 설계, 13가지 방법 비교, 신뢰도 계산", "여러 모델 비교 요구, 최종 모델·학습 3년 결정"],
    ["점검", "데이터 전수 점검, 문서와 코드 대조", "단계별 재검증 요청"],
    ["문서", "결정 기록·그림·발표 자료 초안", "공개 범위 결정, 최종 검토"],
  ], { x: M + 4.4, y: Y0, w: 7.73, colW: [0.95, 3.4, 3.38], fontSize: 12, rowH: 0.6 });
}

// ---------------------------------------------------------------- 7. AI 활용 ②
if (!SUMMARY) {
  const s = content("7  AI 활용", "AI의 오류는 **결과를 직접 확인하는 단계**에서 찾았습니다");
  plain(s, "AI의 결과를 그대로 쓰지 않고, 실행 결과·원본 데이터·과제 원문과 대조하는 단계를 따로 두었습니다");
  table(s, [
    ["확인 방법", "AI의 오류", "조치"],
    ["과제 원문·약관 확인", "지하철역 위치를 저장 금지 서비스(Kakao)에서 받아 저장", "정부 공공데이터로 교체"],
    ["과제 원문·약관 확인", "'모은 데이터에 없는 집은 그 자리에서 조회' 요구를 놓침", "실행 중 조회 기능 추가"],
    ["숫자 범위 점검", "정상 거래의 26%를 이상한 거래로 잘못 표시", "기준을 고쳐 0.4%로"],
    ["숫자 범위 점검", "건물 사용승인일을 잘못 읽어 연식이 2006년", "코드 수정"],
    ["직접 실행", "호수를 비교하는 버그로 20건 중 18건 오류", "코드와 검사 방법 수정"],
    ["하나씩 열어 보기", "정상 거래 133건까지 '묶음 거래'로 잘못 분류", "확인 후 12건만"],
    ["숫자 대조", "데이터를 보기 전에 쓴 그림 제목 6개가 실제와 다름", "결과 표와 맞춰 수정"],
    ["직접 질문", "근거 없이 '3년 치만 수집'을 제안", "6년 수집 후 검증으로 3년 결정"],
    ["과제 명령으로 실행", "엑셀로 저장한 입력 파일(CP949)을 못 읽어 전체가 멈춤", "두 인코딩 모두 읽기,\n시험 파일 추가"],
    ["직접 질문", "상용 시세 비교값을 약관 확인 없이 공개 저장소에 넣음", "약관 확인 후 요약만 공개"],
  ], { x: M, y: Y0, w: 8.3, colW: [1.75, 4.35, 2.2], fontSize: 11, rowH: 0.44 });
  card(s, M + 8.6, Y0, 3.53, 1.55);
  text(s, "배운 점", { x: M + 8.85, y: Y0 + 0.1, w: 3, h: 0.35, fontSize: 15, bold: true, color: COL.navy });
  text(s, "확인 단계를 따로 둘 때만 오류가 드러났습니다. 그래서 단계마다 점검을 요청했습니다", { x: M + 8.85, y: Y0 + 0.5, w: 3.05, h: 0.95, fontSize: 13 });
  card(s, M + 8.6, Y0 + 1.75, 3.53, 3.15, "FBEDE7");
  text(s, "AI 없이 했다면", { x: M + 8.85, y: Y0 + 1.85, w: 3, h: 0.35, fontSize: 15, bold: true, color: COL.orange });
  text(s, "약 2.5～3.5개월", { x: M + 8.85, y: Y0 + 2.2, w: 3.05, h: 0.5, fontSize: 22, bold: true, color: COL.ink });
  text(s, "본인 추정 · 파이썬 5개월 차 기준 · 같은 범위 · 실제 소요 3일", { x: M + 8.85, y: Y0 + 2.72, w: 3.05, h: 0.35, fontSize: 11, color: COL.ink2 });
  bullets(s, [
    "공공 API·데이터 처리·검증 방법을 익히는 시간이 대부분",
    "범위를 줄여도(방법 1개, 단순 신뢰도) 5～6주",
    "AI는 구현 시간을 줄였고, 선택과 검증은 직접 했습니다",
  ], { x: M + 8.85, y: Y0 + 3.15, w: 3.1, h: 1.65, fontSize: 12, color: COL.ink });
}

// ---------------------------------------------------------------- 요약본 7. AI 활용(단계별 역할 + 오류와 확인 + AI 없이)
if (SUMMARY) {
  const s = content("7  AI 활용", "코드는 AI와 함께 작성했고, **방향과 검증은 제가 판단**했습니다");
  plain(s, "사용한 AI 도구는 Claude Code이며, AI의 결과는 실행 결과·원본 데이터·과제 원문과 대조한 뒤 반영했습니다");
  table(s, [
    ["단계", "AI가 한 일", "제가 판단·결정한 것"],
    ["설계", "과제 요약, 감정평가 방식을 모델에 연결", "마감·기준일 해석, 검증 물건의 과거 거래도 일반 비교사례로 사용(특정 물건 분기 금지)"],
    ["수집", "정부 API 응답 확인, 수집 코드", "수집 범위 결정, 약관 문제 데이터 교체"],
    ["다듬기", "중복·표기·이상한 거래를 걸러 내는 규칙", "제외 기준(낮은 이상치만 제외)"],
    ["모델", "검증 설계, 13가지 방법 비교, 신뢰도 계산", "여러 모델 비교 요구, 최종 모델·학습 3년 결정"],
    ["문서", "결정 기록·그림·발표 자료 초안", "공개 범위 결정, 최종 검토"],
  ], { x: M, y: Y0, w: 7.3, colW: [0.9, 3.1, 3.3], fontSize: 11, rowH: 0.5 });
  table(s, [
    ["AI의 오류", "확인 방법 → 조치"],
    ["지하철역 좌표를 저장 금지 서비스에서 받아 저장", "약관 확인 → 공공데이터로 교체"],
    ["정상 거래의 26%를 이상 거래로 잘못 표시", "수치 점검 → 기준 수정(0.4%)"],
    ["엑셀(CP949) 입력 파일을 못 읽어 전체가 멈춤", "과제 명령으로 실행 → 두 인코딩 처리"],
    ["근거 없이 '3년 치만 수집'을 제안", "직접 질문 → 6년 수집 후 검증으로 3년 결정"],
  ], { x: M, y: 4.95, w: 7.3, colW: [3.9, 3.4], fontSize: 11, rowH: 0.36 });
  card(s, M + 7.6, Y0, W - 2 * M - 7.6, 2.0);
  text(s, "AI 작업 규칙을 문서로 관리", { x: M + 7.85, y: Y0 + 0.15, w: 4.2, h: 0.35, fontSize: 14, bold: true, color: COL.navy });
  bullets(s, [
    "수치는 실제 실행 결과만 사용, 데이터 결합 때마다 건수 대조",
    "결정마다 선택지와 근거 기록(24건), 직접 확인 후 반영(PR 20건 이상)",
  ], { x: M + 7.85, y: Y0 + 0.6, w: 4.1, h: 1.3, fontSize: 12 });
  card(s, M + 7.6, Y0 + 2.2, W - 2 * M - 7.6, 2.75, "FBEDE7");
  text(s, "AI 없이 했다면", { x: M + 7.85, y: Y0 + 2.35, w: 4, h: 0.35, fontSize: 14, bold: true, color: COL.orange });
  text(s, "약 2.5～3.5개월", { x: M + 7.85, y: Y0 + 2.75, w: 4, h: 0.5, fontSize: 22, bold: true, color: COL.ink });
  text(s, "본인 추정 · 파이썬 5개월 차 기준 · 같은 범위 · 실제 소요 3일", { x: M + 7.85, y: Y0 + 3.3, w: 4.1, h: 0.35, fontSize: 11, color: COL.ink2 });
  text(s, "공공 API·데이터 처리·검증 방법을 익히는 시간이 대부분입니다. AI는 구현 시간을 줄였고, 선택과 검증은 직접 했습니다",
    { x: M + 7.85, y: Y0 + 3.7, w: 4.1, h: 1.0, fontSize: 12 });
}

// ---------------------------------------------------------------- 8. 한계와 개선안
{
  const s = content("8  한계와 개선안", "남은 과제는 **사정이 있는 거래**와 호 단위 정보입니다");
  plain(s, "더 개선하기 위해서는 데이터 자동 갱신과 성능의 지속적인 재검증이 필요합니다");
  const colW = (W - 2 * M - 0.3) / 2;
  card(s, M, Y0, colW, 4.75);
  text(s, "한계", { x: M + 0.3, y: Y0 + 0.15, w: 4, h: 0.4, fontSize: 18, bold: true, color: COL.orange });
  bullets(s, [
    "직거래 등 사정이 있는 거래는 구별하지 못하고 신뢰도에도 반영하지 못함",
    "비싼 집은 조금 낮게, 싼 집은 조금 높게 추정하는 경향",
    "강남 안에서는 위험 물건을 신뢰도로 충분히 구분하지 못함",
    "실거래 자료에 호 정보가 없어, 호까지 넣은 입력의 정확도는 검증하지 못함",
    "공시가격이 없는 집은 정확도가 낮아 신뢰도를 0.10으로 표시",
    "갱신하지 않으면 1년 뒤 3～5% 낮게 추정",
    "시세 흐름은 3개월 평균이라 반응이 늦고, 신고가 덜 들어온 최근 2개월(9·10월)은 반영하지 못함",
    `하우스머치 참고 비교 9건에서는 하우스머치가 실거래가에 더 가까웠음${SUMMARY ? "" : "(부록 G)"}`,
  ], { x: M + 0.3, y: Y0 + 0.7, w: colW - 0.6, h: 3.9, fontSize: 13 });
  const x2 = M + colW + 0.3;
  card(s, x2, Y0, colW, 4.75);
  text(s, "개선안", { x: x2 + 0.3, y: Y0 + 0.15, w: 5, h: 0.4, fontSize: 18, bold: true, color: COL.navy });
  bullets(s, [
    "실거래가는 매월, 공시가격은 매년 자동 수집",
    "새 거래로 매월 성능을 재측정하고, 기준 미달 시 재학습",
    "사정이 있는 거래를 걸러 낼 추가 자료(등기부 등)",
    "호 단위 정보(방향·조망·내부 상태), 학교·공원·상권 거리",
    "주변 유사 거래를 근거로 함께 제시",
    "모델을 미리 학습해 두고 요청마다 즉시 응답",
  ], { x: x2 + 0.3, y: Y0 + 0.7, w: colW - 0.6, h: 3.2, fontSize: 13 });
}

// ---------------------------------------------------------------- 정리
if (!SUMMARY) {
  const s = pres.addSlide({ masterName: "DARK" });
  text(s, "정리", { x: M + 0.2, y: 0.9, w: 6, h: 0.5, fontSize: 18, color: COL.orange, bold: true });
  [["9%", "보통 오차(두 검증 상황 평균)"], ["79%", "실제 가격 ±20% 안(두 상황 평균)"], ["86%", "신뢰도 0.8 초과 물건의 ±20% 적중률"], ["0건", "표본 20건 실행 실패"]].forEach(([n, l], i) => {
    const x = M + 0.2 + i * 3.0;
    text(s, n, { x, y: 3.9, w: 2.8, h: 0.9, fontSize: 44, bold: true, color: i === 2 ? COL.orange : COL.white });
    text(s, l, { x, y: 4.8, w: 2.8, h: 0.4, fontSize: 13, color: "C9D3E6" });
  });
  bullets(s, [
    "공시가격에서 출발해 단순하고 설명하기 쉬운 추정을 만들었습니다(가격 차이의 87% 설명)",
    "공시가격이 덜 반영한 노후도·층·위치 차이를 머신러닝으로 보정해 오차를 줄였습니다(11% → 9%)",
    "과거 오차로 신뢰도를 계산해, 표시한 신뢰도와 실제 적중률이 거의 같습니다",
    "권역 밖이거나 해석할 수 없는 주소도 멈추지 않고, 해당 행에 실패 사유를 남깁니다",
  ], { x: M + 0.2, y: 1.5, w: 11.5, h: 2.9, fontSize: 18, color: COL.white });
  text(s, "코드·데이터·의사결정 기록: github.com/KimInSeok-DA/DA_Seoul_Villa_AVM  |  다음 장부터 부록(기술 상세)", { x: M + 0.2, y: 6.3, w: 12, h: 0.4, fontSize: 14, color: "C9D3E6" });
}

// ================================================================ 부록
if (!SUMMARY) {
  const s = pres.addSlide({ masterName: "DARK" });
  text(s, "부록", { x: M + 0.2, y: 2.6, w: 6, h: 0.5, fontSize: 18, color: COL.orange, bold: true });
  text(s, "기술 상세", { x: M + 0.2, y: 3.1, w: 11, h: 0.9, fontSize: 40, bold: true, color: COL.white });
  text(s, "용어 풀이 · 기술 스택과 데이터 상세 · 검증 상세표 · 모델 비교 방법 · 신뢰도 계산 방법 · 시점 지수 검증 · 하우스머치 참고 비교", { x: M + 0.2, y: 4.1, w: 11, h: 0.4, fontSize: 16, color: "C9D3E6" });
}

// 부록 A. 용어 풀이
if (!SUMMARY) {
  const s = content("부록 A", "용어 풀이");
  table(s, [
    ["용어", "뜻"],
    ["B1(기본 추정)", "공시가격 × 실거래/공시 비율. 비율은 같은 건물 → 법정동 → 구 순서로 가져오고, 거래가 적으면 동네 값 쪽으로 조정"],
    ["시점 지수(시점 보정)", "구별·월별 실거래/공시 비율의 중앙값(3개월 이동평균). 과거 거래가를 기준일 가격으로 환산"],
    ["XGBoost", "결정 나무를 여러 개 이어 붙여 앞 나무의 오차를 다음 나무가 줄이는 머신러닝 방법(그래디언트 부스팅)"],
    ["직접 / 잔차 / 평균", "직접: 건물 특징으로 log ㎡당 가격 예측 / 잔차: log(실거래 ÷ B1) 예측해 B1을 보정 / 평균: 두 추정의 기하평균"],
    ["PNU(지번)", "법정동코드 10자리 + 산 여부 1자리 + 본번 4자리 + 부번 4자리. 데이터를 합치는 열쇠"],
    ["홀드아웃", "학습에 쓰지 않고 검증용으로 떼어 둔 표본(건물 632개)"],
    ["GroupKFold", "교차검증을 건물(그룹) 단위로 나눠 같은 건물이 학습·검증에 섞이지 않게 함"],
    ["그리드서치", "하이퍼파라미터(나무 깊이·개수 등) 조합을 모두 시험해 교차검증 성적이 가장 좋은 것을 고름"],
    ["부트스트랩", "표본을 복원 추출로 2,000번 다시 뽑아 성적 차이의 95% 구간을 구함. 0을 포함하지 않으면 우연이 아니라고 판단"],
    ["MAPE / 중앙값 오차율", "|추정 − 실제| ÷ 실제의 평균 / 중앙값"],
    ["수정 Z-점수", "중앙값과 MAD로 계산한 이상치 점수. |z| > 3.5를 이상치로 봄(Iglewicz & Hoaglin 1993)"],
    ["결정계수 / VIF", "결정계수: 변수가 설명하는 분산 비율 / VIF: 변수끼리 얼마나 겹치는지(다중공선성)"],
  ], { x: M, y: 1.35, w: W - 2 * M, colW: [2.6, 9.533], fontSize: 12, rowH: 0.41 });
}

// 부록 B. 기술 스택·데이터 상세
if (!SUMMARY) {
  const s = content("부록 B", "기술 스택과 데이터 상세");
  table(s, [
    ["구분", "사용"],
    ["언어·환경", "Python 3.12+ (개발 3.14.5), uv + requirements.txt, 3.12·3.13·3.14 새 환경에서 같은 출력 확인"],
    ["라이브러리", "pandas 3.0.6, numpy 2.5.3, XGBoost 3.4.1, scikit-learn 1.9.1, requests, python-dotenv, Jupyter, matplotlib"],
    ["API 키", "DATA_GO_KR_API_KEY(실거래·건축물대장), VWORLD_API_KEY(공시가격·연속지적도), SEOUL_OPEN_API_KEY(폐쇄말소대장)·REB_API_KEY(부동산원 지수, 검증용). 환경변수로 받으며 predict.py는 키 없이도 실행"],
  ], { x: M, y: 1.35, w: W - 2 * M, colW: [1.8, 10.333], fontSize: 11, rowH: 0.36 });
  table(s, [
    ["데이터", "수집 방식", "기간·기준", "받은 건수", "정제 후 · 사용"],
    ["연립다세대 매매 실거래", "API, 구·월별 전수", "2020-10~2026-10", "36,997건", "33,363건 · 학습 최근 3년 14,401건"],
    ["연립다세대 전월세", "API", "2020-10~2026-10", "143,109건", "사용 안 함"],
    ["공동주택가격(호별)", "API, 거래 지번마다", "2026(없으면 최근 연도)", "9,928개 지번", "107,236호"],
    ["건축물대장 표제부", "API, 거래 지번마다", "수집일 현행", "9,928개 지번", "연식·승강기·층수·세대수·주차"],
    ["필지 좌표·공시지가", "API(연속지적도), 3개 구 전체", "2025 공시지가", "123,615필지", "좌표·땅값·역 거리"],
    ["지하철역", "공공데이터 파일", "2026-06-30", "367개", "275개 역"],
    ["법정동코드·행정동 연계", "공공데이터·행정안전부 파일", "2026-06-30 · 2026-09-30", "—", "30개 법정동 · 63개 행정동"],
    ["폐쇄말소대장 표제부", "API(서울 열린데이터광장), 서울 전체", "수집일 기준", "383,716건", "3개 구 49,074지번 · 철거 전 거래 523건 제외"],
    ["부동산원 연립/다세대 매매 지수", "API(R-ONE)", "월간", "873행", "시점 지수 검증에만(부록 F)"],
  ], { x: M, y: 3.0, w: W - 2 * M, colW: [2.5, 2.6, 2.35, 1.6, 3.083], fontSize: 11, rowH: 0.33 });
  text(s, "유형: 다세대 30,135 · 연립 3,097 · 혼합 표기 131건(정제 후). 정제: 해제 2,188 · 낮은 이상치(수정 Z < −3.5) 331 · 일괄 매매 합계 12 · 재건축 전 580 · 철거된 건물 523 제외",
    { x: M, y: 6.6, w: W - 2 * M, h: 0.35, fontSize: 11, color: COL.ink2 });
}

// 부록 C. 검증 상세표
if (!SUMMARY) {
  const s = content("부록 C", "자체 검증 상세(632개 건물, 입력: 호 없음)");
  table(s, [
    ["상황", "면적", "중앙값 오차", "MAPE", "±10% 적중", "±20% 적중", "80% 구간 포함"],
    ["A 처음 보는 건물", "있음", "9.4%", "13.7%", "52.7%", "78.5%", "82.9%"],
    ["A 처음 보는 건물", "비움", "11.0%", "16.2%", "46.4%", "73.3%", "80.1%"],
    ["B 같은 건물 과거 거래 있음", "있음", "8.6%", "13.0%", "55.7%", "80.1%", "80.7%"],
    ["B 같은 건물 과거 거래 있음", "비움", "10.5%", "15.6%", "48.6%", "74.1%", "77.2%"],
    ["기준선 B1 (A / B)", "있음", "11.1% / 10.7%", "15.8% / 14.7%", "45.3% / 48.1%", "71.7% / 73.9%", "69.8% / 67.7%"],
  ], { x: M, y: 1.35, w: W - 2 * M, colW: [3.2, 0.8, 1.6, 1.6, 1.6, 1.65, 1.683], fontSize: 12, rowH: 0.42 });
  table(s, [
    ["신뢰도 구간", "A 표본 / 평균 신뢰도 / 실제 ±20% 적중", "B 표본 / 평균 신뢰도 / 실제 ±20% 적중"],
    ["0.6 이하", "73 / 0.57 / 58.9%", "47 / 0.56 / 61.7%"],
    ["0.6~0.7", "120 / 0.67 / 70.8%", "94 / 0.66 / 70.2%"],
    ["0.7~0.8", "171 / 0.77 / 77.2%", "137 / 0.77 / 77.4%"],
    ["0.8 초과", "268 / 0.84 / 88.1%", "354 / 0.86 / 86.2%"],
  ], { x: M, y: 4.15, w: W - 2 * M, colW: [2.0, 5.07, 5.063], fontSize: 12, rowH: 0.4 });
  text(s, "분할: 최근 12개월 거래가 있는 평가 권역 건물 3,159개 중 20%(시드 42)를 건물 단위로 분리, 건물마다 최근 거래 1건. A는 그 건물 거래를 모두 빼고, B는 대상 거래 이전 거래만 남김. 구간·신뢰도 보정은 나머지 건물 1만 건으로",
    { x: M, y: 6.3, w: W - 2 * M, h: 0.55, fontSize: 11, color: COL.ink2 });
}

// 부록 D. 모델 비교 방법
if (!SUMMARY) {
  const s = content("부록 D", "모델 비교 방법과 학습 기간");
  bullets(s, [
    "후보 13개: Ridge · KNN · 랜덤포레스트 · XGBoost × {직접(log ㎡당 가격) / 잔차(log 실거래÷B1) / 둘의 기하평균} + B1",
    "Pipeline(결측 채움·표준화 → 모델) + GridSearchCV, 학습 세트 안에서만 GroupKFold(5, 그룹 = PNU), 기준 MAE(log)",
    "누수 방지: 학습 행의 B1 근거는 그 거래보다 앞선 같은 건물 거래와 자기 건물을 뺀 동네 통계로만 계산",
    "상황 A(처음 보는 건물) · B(같은 건물 앞선 거래 있음) · T(2025-08까지 학습해 그 뒤 1년 맞히기)",
    "선정 기준(±20% 적중·중앙값 오차·MAPE, 세 상황 순위, 부트스트랩 95% 구간, 단순성)을 결과 전에 문서로 고정",
    "결과: XGB-평균이 평균 순위 1위(1.8), 가장 나쁜 순위 기준으로도 1위(2.3). 직접 방식은 T에서, 잔차 방식은 A에서 약해 둘의 평균을 채택",
  ], { x: M, y: 1.35, w: 6.9, h: 5.3, fontSize: 13 });
  table(s, [
    ["학습 기간", "학습 거래", "A ±20% / 중앙값", "B ±20% / 중앙값"],
    ["3년(채택)", "14,520", "79.0% / 9.3%", "80.2% / 9.0%"],
    ["5년", "24,531", "79.0% / 9.7%", "78.5% / 9.3%"],
    ["6년", "33,886", "74.5% / 9.9%", "78.2% / 9.5%"],
  ], { x: M + 7.2, y: 1.35, w: 4.93, colW: [1.25, 1.08, 1.3, 1.3], fontSize: 12, rowH: 0.45 });
  text(s, "3년 − 6년: A ±20% 적중 +4.4%p [+2.2, +6.8], 평균 오차 A −1.1%p · B −0.9%p(부트스트랩 95% 구간). 최종 검증과 분리한 보정 표본에서도 같은 방향(72.5% → 75.9%)",
    { x: M + 7.2, y: 3.8, w: 4.93, h: 1.4, fontSize: 12, color: COL.ink2 });
  note(s, "출처: docs/의사결정/1007_10_ML_비교.md, 1007_13_오차_분석.md · 학습 기간 표는 철거된 건물 거래를 빼기 전(1008_02) 비교 당시 값");
}

// 부록 E. 신뢰도 계산 — 단계 그림 + 산식 표
if (!SUMMARY) {
  const s = content("부록 E", "80% 구간과 신뢰도 계산 방법");
  const steps = [["① 보정 표본", "최종 검증을 뺀 후보 중 표본이 만들어진\n2,524개 건물을 5묶음으로 나눠\n돌아가며 추정 → 오차 약 1만 건"],
    ["② 오차 점수", "예측할 때 알 수 있는 정보로\n'얼마나 틀릴지'를 회귀로 추정"],
    ["③ 10개 구간", "오차 점수 순으로 표본을\n10등분해 구간마다 오차 분포 저장"],
    ["④ 적용", "새 물건의 오차 점수가 속한\n구간의 값으로 범위·신뢰도 산출"]];
  const bw = 2.78, gx = 0.3;
  steps.forEach(([h, b], i) => {
    const x = M + i * (bw + gx);
    card(s, x, 1.35, bw, 1.75, i === 3 ? COL.navy : COL.tint);
    text(s, h, { x: x + 0.2, y: 1.48, w: bw - 0.4, h: 0.4, fontSize: 15, bold: true, color: i === 3 ? COL.white : COL.navy });
    text(s, b, { x: x + 0.2, y: 1.95, w: bw - 0.4, h: 1.1, fontSize: 12, color: i === 3 ? COL.white : COL.ink2 });
    if (i < 3) s.addShape(pres.shapes.LINE, { x: x + bw + 0.04, y: 2.22, w: gx - 0.08, h: 0, line: { color: COL.muted, width: 1.5, endArrowType: "triangle" } });
  });
  table(s, [
    ["항목", "계산", "설명"],
    ["로그 오차", "e = log(추정 ÷ 실제)", "0이면 정확, +면 높게, −면 낮게 추정"],
    ["오차 점수", "점수 = Σ 계수 × 변수 (|e|를 최소제곱 회귀)", "변수: 동네·같은 건물 비율의 흩어짐, 같은 건물 거래 수, 면적, 강남·화곡, 면적 빈칸,\nXGBoost 두 추정의 차이, 보정 배율, 지하층, 30년 초과"],
    ["80% 범위", "하한 = 추정 ÷ exp(q90),  상한 = 추정 ÷ exp(q10)", "q10·q90 = 그 구간 로그 오차의 10%·90% 분위수(정규분포 가정 없음)"],
    ["신뢰도", "그 구간에서 |추정 ÷ 실제 − 1| ≤ 0.2 인 비율", "점수가 클수록 낮아지도록 단조 보정(isotonic)"],
    ["예외", "공시가격 없음 → 신뢰도 0.10 고정", "보정 표본이 20건뿐이라 별도 처리. 수집에 없는 지번은 실행 중 공공 API 조회"],
  ], { x: M, y: 3.4, w: W - 2 * M, colW: [1.5, 4.3, 6.333], fontSize: 12, rowH: [0.4, 0.45, 0.75, 0.45, 0.45, 0.45] });
  note(s, "출처: docs/의사결정/1007_09_구간_신뢰도_보정.md, 1007_12_실행_중_조회.md, 1007_13_오차_분석.md · src/avm.py Calibrator");
}

// 부록 F. 시점 지수 검증
if (!SUMMARY) {
  const s = content("부록 F", "직접 만든 시점 지수를 한국부동산원 지수와 비교");
  const f = path.join(ROOT, "outputs", "figures", "reb_index_compare.png"), z = pngSize(f);
  const w = W - 2 * M, h = (w * z.h) / z.w;
  s.addImage({ path: f, x: M, y: 1.3, w, h });
  table(s, [
    ["최근 3년(모델 학습 기간)", "비교 대상", "수준 상관", "3개월 변화 같은 방향", "3년 변화(우리 / 부동산원)"],
    ["강서구", "서남권(주택가격동향조사)", "0.72", "56%", "+2.7% / +10.8%"],
    ["관악구", "서남권(주택가격동향조사)", "0.92", "69%", "+8.9% / +10.8%"],
    ["강남구", "동남권(주택가격동향조사)", "0.90", "72%", "+13.1% / +15.9%"],
  ], { x: M, y: 1.3 + h + 0.15, w: W - 2 * M, colW: [2.6, 2.9, 1.6, 2.3, 2.733], fontSize: 12, rowH: 0.36 });
  note(s, "감정평가 실무의 시점수정(구분건물은 다세대 매매가격지수)과 같은 역할입니다. 공식 지수는 권역 단위라 모델에는 구 단위인 자체 지수를 쓰고 공식 지수는 검증에만 썼습니다. 강서는 회복을 덜 반영하지만 검증에서 낮게 치우치지 않았습니다(치우침 −1%) · 출처: 한국부동산원 R-ONE, docs/의사결정/1008_03");
}

// 부록 G. 하우스머치 참고 비교 — 약관(추정시세 저작권·복제 금지) 때문에 건별 하우스머치 값은 싣지 않고 요약만(1008_04)
if (!SUMMARY) {
  const s = content("부록 G", "하우스머치 참고 비교 9건(입력·학습에는 사용하지 않음)");
  table(s, [
    ["", "우리", "하우스머치"],
    ["보통 오차(중앙값): 9건 / 중개거래 7건", "11.1% / 9.9%", "5.6% / 4.8%"],
    ["실거래가 ±20% 안 (9건)", "6건", "7건"],
    ["실거래가가 범위 안 (9건)", "7건 (80% 구간)", "3건 (상하한시세)"],
  ], { x: M, y: 1.35, w: W - 2 * M, colW: [5.333, 3.4, 3.4], fontSize: 14, rowH: 0.5 });
  table(s, [
    ["주소", "거래", "실거래가", "우리 추정 (신뢰도)", "우리 오차"],
    ["화곡동 362-79 6층", "중개 2026-09", "2.15억", "2.04억 (0.83)", "−5.0%"],
    ["화곡동 811-9 1층", "중개 2026-06", "2.60억", "2.31억 (0.78)", "−11.1%"],
    ["화곡동 1016-19 4층", "중개 2026-08", "2.70억", "2.97억 (0.69)", "+9.9%"],
    ["봉천동 218-42 1층", "중개 2026-08", "6.35억", "5.93억 (0.88)", "−6.6%"],
    ["신림동 98-242 3층", "직거래 2026-05", "1.20억", "1.86억 (0.78)", "+55.0%"],
    ["신림동 409-184 3층", "중개 2026-07", "3.75억", "3.34억 (0.64)", "−11.1%"],
    ["개포동 1195-3 3층", "중개 2026-08", "5.78억", "5.37억 (0.86)", "−7.0%"],
    ["청담동 69-19 2층", "직거래 2026-04", "3.87억", "7.41억 (0.74)", "+91.4%"],
    ["역삼동 751-8 5층", "중개 2026-01", "5.20억", "6.41억 (0.58)", "+23.3%"],
  ], { x: M, y: 3.6, w: 7.3, colW: [2.1, 1.5, 1.1, 1.6, 1.0], fontSize: 11, rowH: 0.3 });
  bullets(s, [
    "이 9건에서는 하우스머치가 실거래가에 더 가까웠습니다",
    "조건 차이: 우리 값은 해당 거래를 빼고 낸 추정입니다. 하우스머치는 9건 중 8건이 추정 기준일(09-01) 이전 거래이고, 화면을 저장한 811-9는 그 거래가 거래사례 목록에 있었습니다",
    "기준일 이후 거래(첫 줄)도 하우스머치가 더 가까웠습니다",
    "직거래 2건은 둘 다 높게 추정했고, 우리 오차가 더 컸습니다",
    "우리 신뢰도가 가장 낮았던 역삼동(0.58)이 중개거래 중 오차가 가장 컸습니다",
  ], { x: M + 7.6, y: 3.6, w: W - 2 * M - 7.6, h: 3.2, fontSize: 12 });
  note(s, "범위 안 건수는 성격이 다른 범위(80% 구간 vs 상하한시세)라 직접 비교가 어렵습니다 · 9건은 권역 × 신뢰도에서 무작위 선정(시드 7), 하우스머치는 직접 조회(2026-10-08, 기준일 2026-09-01). 건별 하우스머치 값은 이용약관(저작권·복제 금지)에 따라 싣지 않았습니다 · 출처: 하우스머치, docs/의사결정/1008_04");
}

// 한국어 줄바꿈: 단어 중간에서 끊지 않도록 문단에 eaLnBrk="0", 글자 언어를 한국어로(PowerPoint 렌더링으로 확인)
async function keepKoreanWords(file) {
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  for (const name of Object.keys(zip.files).filter((n) => /^ppt\/(slides|slideLayouts|slideMasters)\/[^/]+\.xml$/.test(n))) {
    const xml = (await zip.file(name).async("string"))
      .replace(/<a:pPr(?![^>]*eaLnBrk)/g, '<a:pPr eaLnBrk="0"')
      .replace(/<a:p>(?!<a:pPr)/g, '<a:p><a:pPr eaLnBrk="0"/>')
      .replace(/lang="en-US"/g, 'lang="ko-KR" altLang="en-US"'); // 언어가 영어로 표시되면 PowerPoint가 한글을 글자 단위로 끊는다
    zip.file(name, xml);
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}
pres.writeFile({ fileName: OUT }).then(async (f) => { await keepKoreanWords(f); console.log("작성:", f); });
