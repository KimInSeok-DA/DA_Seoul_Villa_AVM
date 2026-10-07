# 서울 다세대(빌라) 자동 시세 산정 모델 (AVM)

서울 강서구 화곡동·강남구·관악구의 다세대·연립주택에 대해 **지번 + 층 + 호**를 넣으면 매매 시세(추정값·하한·상한·신뢰도·근거)를 내는 모델.

> 작업 중. `predict.py` 동작(최종 모델 + 구간·신뢰도 보정). 현재 진행 상황은 [`HANDOFF.md`](HANDOFF.md).
>
> **무엇을 어떻게 왜 했는지 처음부터 따라가려면 [`docs/진행_과정.md`](docs/진행_과정.md)** — 단계별 요약과 흐름도, 각 단계의 의사결정 문서 연결.

## 모델 한 줄 요약

**공시가격 × 시점 보정한 실거래/공시 비율(B1)** 을 기준으로, **XGBoost 두 모델**(건물·입지로 직접 추정 / B1이 빗나간 정도를 보정)의 기하평균으로 건물 특성을 더 반영한다.
Ridge·KNN·랜덤포레스트·XGBoost를 처음 보는 건물·같은 건물 거래 있음·1년 뒤(시점 밖) 세 상황에서 비교해 골랐다 → [`1007_10`](docs/의사결정/1007_10_ML_비교.md)

## 설치

Python 3.12 이상(3.12·3.13·3.14에서 같은 결과 확인). 둘 중 하나로 설치한다.

**pip**
```bash
python -m venv .venv
.venv\Scripts\activate          # macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**uv**
```bash
uv sync
.venv\Scripts\activate          # macOS·Linux: source .venv/bin/activate
```

## 실행

가상환경을 켠 상태에서 과제 명령 그대로 실행한다(`uv run python predict.py ...`도 같다).

```bash
python predict.py --input input.csv --output output.csv
```

- 입력 컬럼: `id, sigungu, dong, jibun, floor, ho, area_m2` (`ho`, `area_m2`는 비어 있을 수 있음)
- 출력 컬럼: `id, price_est, price_low, price_high, confidence, basis, status`
- 저장소의 정제 데이터로 실행할 때마다 모델을 다시 맞춘다(20건 약 23초). 입력 지번이 수집 데이터에 없을 때만 공시가격·건축물대장을 실행 중에 조회한다([1007_12](docs/의사결정/1007_12_실행_중_조회.md)) — 키가 없으면 조회 없이 추정을 계속하고 `basis`에 적는다. 새 거래를 정제 데이터에 더하고 다시 실행하면 그대로 반영된다
- `price_low`~`price_high`는 80% 구간, `confidence`는 검증에서 비슷한 조건의 추정이 실거래가 ±20% 안에 든 비율이다. 둘 다 검증 오차로 만든 보정표 `data/processed/calibration.json`(`src/build_calibration.py`)으로 정한다
- 규격 검사: `python tests/check_output.py --input tests/sample_input.csv --output output.csv --expect-ok`
- 예외 입력 예시: `tests/edge_input.csv`(권역 밖, 주소 해석 불가, 지하 표기, 면적 없음 등)

## 환경 변수

**`predict.py`는 키 없이도 돈다**(필요한 데이터를 미리 받아 저장소에 넣어 둠). 키가 있으면 수집 데이터에 없는 지번의 공시가격(`VWORLD_API_KEY`)·건축물대장(`DATA_GO_KR_API_KEY`)을 실행 중에 조회해 더 정확하게 추정한다(없으면 ㎡당 가격 방식으로 낮은 신뢰도). 데이터를 다시 받을 때(`src/collect_*.py`)도 같은 키를 쓴다. `.env.example`을 `.env`로 복사하고 키를 넣는다(환경변수로 줘도 된다). 키는 저장소에 올리지 않는다.

| 변수 | 발급처 | 용도 |
|---|---|---|
| `DATA_GO_KR_API_KEY` | 공공데이터포털(data.go.kr) 활용신청 | 연립다세대 매매·전월세 실거래가, 건축HUB 건축물대장 |
| `VWORLD_API_KEY` | 브이월드(vworld.kr) 인증키 발급 | 공동주택가격(호별 공시가격), 연속지적도(필지 좌표·공시지가) |
| `KAKAO_REST_API_KEY` | Kakao Developers 앱 → 플랫폼 키 → REST API 키 | API 응답 확인용(`src/probe_apis.py`)만. 약관상 결과 저장이 금지라 데이터 수집·예측에 쓰지 않음 |

## 데이터

| 데이터 | 출처 | 수집 코드 |
|---|---|---|
| 연립다세대 매매·전월세 실거래(2020-10~2026-10) | 국토교통부, data.go.kr | `src/collect_trades.py` |
| 건축물대장 표제부 | 국토교통부 건축HUB, data.go.kr | `src/collect_buildings.py` → 정제 `src/build_bld_title.py` |
| 공동주택 공시가격(호별, 2026년 기준·없는 지번은 2020~2025년 최근 연도로 보충) | 국토교통부, VWorld | `src/collect_buildings.py` → 정제 `src/build_apt_price.py` |
| 법정동코드 | 국토교통부 전국 법정동(2026-06-30), data.go.kr | 파일 다운로드 → `data/reference/` |
| 필지 좌표(중심점)·개별공시지가 | 국토교통부 연속지적도, VWorld 데이터 API(data.go.kr 15056910) | `src/collect_parcels.py` |
| 지하철역 좌표 | 전국도시철도역사정보 표준데이터(2026-06-30), data.go.kr | 파일 다운로드 → `src/build_stations.py` |

`data/raw/`(API 원본)는 용량 때문에 올리지 않는다. 위 스크립트로 다시 받을 수 있다. `predict.py`가 읽는 정제 데이터는 `data/processed/`에 함께 올린다(구간·신뢰도 보정표 `calibration.json`은 `src/build_calibration.py`가 정제 데이터로 만든다).

## 폴더 구조

```text
├─ predict.py          실행 진입점
├─ src/                수집·정제 코드, avm.py(B1·검증 공용), ml.py(XGBoost 보정·ML 비교)
├─ tests/              입력 표본, 출력 규격 검사
├─ notebooks/          검증·분석 노트북 (NN_주제.ipynb, make_NN_*.py가 생성)
├─ data/
│  ├─ raw/             API 원본 응답 (저장소 제외, 다시 받을 수 있음)
│  ├─ reference/       법정동코드표, 지하철역 좌표, 필지 좌표·공시지가
│  └─ processed/       정제 데이터 (저장소에 포함, predict.py가 읽음)
├─ outputs/            다시 만들 수 있는 표·그림
├─ milestones/         재현이 필요한 시점의 결과·모델 메타데이터 보존
└─ docs/
   ├─ 진행_과정.md      단계별 요약·흐름도 (처음 볼 문서)
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
