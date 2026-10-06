# 서울 다세대(빌라) 자동 시세 산정 모델 (AVM)

서울 강서구 화곡동·강남구·관악구의 다세대주택에 대해 **지번 + 층 + 호**를 넣으면 매매 시세(추정값·하한·상한·신뢰도·근거)를 내는 모델.

> 작업 중. 설치·실행 방법과 사용 데이터 목록은 구현이 끝나면 채운다.

## 실행

```bash
python predict.py --input input.csv --output output.csv
```

- 입력 컬럼: `id, sigungu, dong, jibun, floor, ho, area_m2` (`ho`, `area_m2`는 비어 있을 수 있음)
- 출력 컬럼: `id, price_est, price_low, price_high, confidence, basis, status`

## 환경 변수

`.env.example`을 `.env`로 복사하고 키를 넣는다. 키는 저장소에 올리지 않는다.

| 변수 | 용도 |
|---|---|
| `DATA_GO_KR_API_KEY` | 공공데이터포털 — 연립다세대 매매 실거래가, 건축물대장 |
| `VWORLD_API_KEY` | (선택) 지오코딩 |
| `KAKAO_REST_API_KEY` | (선택) 지오코딩 |

## 폴더 구조

```text
├─ predict.py          실행 진입점 (예정)
├─ src/                수집·정제·모델 코드
├─ notebooks/          탐색·검증 노트북 (NN_주제.ipynb)
├─ data/
│  ├─ raw/             API 원본 응답 (저장소 제외, 다시 받을 수 있음)
│  └─ processed/       정제된 거래 데이터 (제출에 포함, predict.py가 읽음)
├─ outputs/            다시 만들 수 있는 표·그림
├─ milestones/         재현이 필요한 시점의 결과·모델 메타데이터 보존
└─ docs/
   ├─ AI_활용_기록.md
   └─ 의사결정/        MMDD_NN_주제.md
```
