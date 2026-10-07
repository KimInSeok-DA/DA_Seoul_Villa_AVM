# 서울 다세대(빌라) 자동 시세 산정 모델 (AVM)

서울 강서구 화곡동·강남구·관악구의 다세대·연립주택에 대해 **지번 + 층 + 호**를 넣으면 매매 시세(추정값·하한·상한·신뢰도·근거)를 내는 모델.

> 작업 중. 설치 방법과 `predict.py`는 구현이 끝나면 채운다. 현재 진행 상황은 [`HANDOFF.md`](HANDOFF.md).

## 실행

```bash
python predict.py --input input.csv --output output.csv
```

- 입력 컬럼: `id, sigungu, dong, jibun, floor, ho, area_m2` (`ho`, `area_m2`는 비어 있을 수 있음)
- 출력 컬럼: `id, price_est, price_low, price_high, confidence, basis, status`

## 환경 변수

`.env.example`을 `.env`로 복사하고 키를 넣는다. 키는 저장소에 올리지 않는다.

| 변수 | 발급처 | 용도 |
|---|---|---|
| `DATA_GO_KR_API_KEY` | 공공데이터포털(data.go.kr) 활용신청 | 연립다세대 매매·전월세 실거래가, 건축HUB 건축물대장 |
| `VWORLD_API_KEY` | 브이월드(vworld.kr) 인증키 발급 | 공동주택가격(호별 공시가격), 지오코더(실시간 조회만, 저장하지 않음) |
| `KAKAO_REST_API_KEY` | Kakao Developers 앱 → 플랫폼 키 → REST API 키 | 예측 중 입력 주소를 실시간 조회(법정동코드·좌표). 약관상 결과는 저장하지 않음 |

## 데이터

| 데이터 | 출처 | 수집 코드 |
|---|---|---|
| 연립다세대 매매·전월세 실거래(2020-10~2026-10) | 국토교통부, data.go.kr | `src/collect_trades.py` |
| 건축물대장 표제부 | 국토교통부 건축HUB, data.go.kr | `src/collect_buildings.py` |
| 공동주택 공시가격(2026, 호별) | 국토교통부, VWorld | `src/collect_buildings.py` |
| 법정동코드 | 국토교통부 전국 법정동(2026-06-30), data.go.kr | 파일 다운로드 → `data/reference/` |
| 지하철역 좌표 | 전국도시철도역사정보 표준데이터(2026-06-30), data.go.kr | 파일 다운로드 → `src/build_stations.py` |

`data/raw/`(API 원본)는 용량 때문에 올리지 않는다. 위 스크립트로 다시 받을 수 있다. `predict.py`가 읽는 정제 데이터는 `data/processed/`에 함께 올린다.

## 폴더 구조

```text
├─ predict.py          실행 진입점 (예정)
├─ src/                수집·정제·모델 코드
├─ notebooks/          탐색·검증 노트북 (NN_주제.ipynb)
├─ data/
│  ├─ raw/             API 원본 응답 (저장소 제외, 다시 받을 수 있음)
│  ├─ reference/       법정동코드표, 지하철역 좌표
│  └─ processed/       정제 데이터 (저장소에 포함, predict.py가 읽음)
├─ outputs/            다시 만들 수 있는 표·그림
├─ milestones/         재현이 필요한 시점의 결과·모델 메타데이터 보존
└─ docs/
   ├─ AI_활용_기록.md
   ├─ 작업일지/        YYYY-MM-DD.md
   └─ 의사결정/        MMDD_NN_주제.md
```

## AI 협업 방식

이 프로젝트는 AI 코딩 도구(Claude Code)와 함께 만들었다. AI에게 무엇을 맡기고, 어떤 규칙으로 지시하고, 결과를 어떻게 검증했는지를 아래 파일에 남겼다.

| 보는 순서 | 파일 | 내용 |
|---|---|---|
| 1 | [`AGENTS.md`](AGENTS.md) | AI에게 주는 작업 지시: 수치 지어내기 금지, 법정동코드·지번 조인과 건수 대조, 상용 시세 사용 금지, 작업 난이도별 모델 선택. `CLAUDE.md`는 이 파일을 불러오는 한 줄 |
| 2 | [`docs/AI_활용_기록.md`](docs/AI_활용_기록.md) | 작업 단위마다 **AI가 한 것 / 내가 판단한 것 / AI가 틀린 것과 잡은 방법** |
| 3 | [`docs/의사결정/`](docs/의사결정/) | AI가 제시한 안과 내가 내린 결정, 그 근거 |
| 4 | [`HANDOFF.md`](HANDOFF.md), [`docs/작업일지/`](docs/작업일지/) | 세션이 바뀌어도 AI가 이어서 일하도록 남기는 현재 상태와 날짜별 기록 |
| 5 | [`src/probe_apis.py`](src/probe_apis.py) | AI가 알려준 API 주소·필드를 그대로 믿지 않고 실제 응답으로 확인한 스크립트 |

- 커밋에는 AI 공동 작성자 표시를 넣지 않는다(`.claude/settings.json`, `.githooks/`). 대신 AI가 한 일은 위 기록에 따로 남긴다
- 과제 원문·회사 정보·API 키·개인 학습 자료는 `.gitignore`로 저장소에서 뺐다
