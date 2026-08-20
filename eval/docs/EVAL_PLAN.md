# 검증 계획

## 무엇을 검증하나

```
① OCR    이 파일이 무슨 문서인가
② 규칙   이 은행은 뭘 요구하는가   ← 틀리면 가장 치명적, 사람이 대조
③ 판정   그래서 준비가 됐는가      ← 사용자가 보는 결론
```

**두 오류의 무게는 다르다.**

- 필요한데 "불필요" → 은행에서 거절 (치명적)
- 불필요한데 "필요" → 서류 하나 더 (경미)

→ 단일 정확도 대신 **거짓 준비완료율**을 최우선으로 본다.

## 지표

**1순위**

| 지표 | 계산 | 목표 |
|---|---|---|
| 거짓 준비완료율 | 부족한데 준비완료라 한 비율 | 0 |
| 규칙 출처 커버리지 | source_url + checked_at 채워진 비율 | 100% |
| 문서 분류 정확도 | 종류별 + 혼동 쌍 기록 | — |
| 발급일 추출 정확도 | 정답 날짜 일치 비율 | — |
| 세션 종료 후 삭제 | 자동 테스트 통과 | 통과 |

**2순위** 엣지 케이스(0개/중복/비문서) · 규칙 원문 대조 · 판정 결정성 · LLM 환각 · **배포 URL 가용성(09-07 11:00 ~ 09-11 23:59)**

**3순위** 캘리브레이션 · 부하 · 마스킹 · 완주율 · 접근성 → 미측정, 인지만

## 더미 데이터

실제 증명서는 절대 사용 금지. 직접 만든다.

**만드는 법** — 기관 홈페이지 샘플 이미지에서 제목·항목명만 참고 → HTML 템플릿 → PDF. 디자인은 대충 해도 된다. OCR이 읽는 건 글자다.

**반드시 심을 것**
- 날짜 2개 이상 (발급일 + 조회기준일) ← 엉뚱한 날짜 집는지
- 날짜 형식 섞기 (`2026. 7. 20.` / `2026년 7월 20일`)
- 마스킹 주민번호 `900101-1******`
- 표 구조, 직인 자리

**품질 변형**
```bash
pdftoppm -png -r 150 원본.pdf scan
convert scan-1.png -rotate 7 tilted.png
convert scan-1.png -brightness-contrast -30x-15 dark.png
```
폰 사진은 모니터 띄우고 직접 촬영.

**구성 (20장)**
```
자격득실확인서 ×5   PDF/스캔/사진/기울어짐/어두움
주민등록등본   ×5   1장은 발급일 6개월 전
재직증명서     ×4
급여명세서     ×3
함정 ×3        유사명 문서 / 영수증 / 빈 페이지
```
함정 3장 없으면 검증이 의미 없다.

## 정답표

`eval/labels.csv`
```csv
file,doc_type,issued_date,holder
s01.pdf,건강보험자격득실확인서,2026-07-20,김철수
s10.jpg,주민등록등본,2026-02-15,김철수
s19.jpg,__NOT_A_DOCUMENT__,,
```

`eval/scenarios.csv`
```csv
id,bank,task,files,expected_status,expected_missing
sc1,kb,한도해제,"s01,s06,s11",준비완료,
sc2,kb,한도해제,"s01,s10,s11",기한만료,주민등록등본
sc3,kb,한도해제,"s01,s06",부족,재직증명서
sc5,kb,한도해제,"s01,s06,s11,s19",준비완료,
sc6,kb,한도해제,"",부족,전체
```

sc2가 가장 중요 (오래된 서류를 만료로 잡는가).

## 폴더

```
eval/
├── README.md
├── samples/       더미 문서
├── templates/     생성용 HTML
├── generate.py    템플릿 → PDF
├── degrade.sh     품질 변형
├── labels.csv
├── scenarios.csv
├── evaluate.py
└── reports/       일자별 결과
```

`evaluate.py`는 CSV 읽고 → API 호출 → 정답 비교 → 숫자 출력.
**매일 아침 돌리고 팀 채팅에 공유.**

## 브랜치

```
main            직접 push 금지
feat/ocr        feat/rules      feat/pipeline    feat/eval
```

접두사: `feat` `fix` `docs` `chore` `refactor`
소문자 + 하이픈, 한글 금지, 3단어 이내

## 커밋

```
<type>: <한글 요약>
```

`feat` `fix` `docs` `test` `chore` `refactor` `style`

```
feat: 더미 문서 생성 스크립트 추가
test: 함정 문서 3종 추가
fix: 발급일 파싱에서 조회기준일 오인식 수정
docs: 검증 계획서 추가
```

50자 이내, 마침표 없음. `update` `수정함` 금지.

## 팀원에게 받을 것

구현을 기다리지 말고 **스펙만 먼저** 받는다. 가짜 응답으로 스크립트를 완성해두고 나중에 주소만 바꾼다.

| 대상 | 스펙 |
|---|---|
| OCR | `POST /analyze` → `{doc_type, confidence, issuer, issued_date, holder}` |
| 규칙 | `{bank, task, required, alternatives, validity_days, source_url, checked_at}` |
| 판정 | `POST /judge` → `{status, missing[], reasons[]}` |

**규칙 JSON에 `source_url`·`checked_at`이 없으면 지금 요청할 것.** 나중에 넣으면 규칙을 전부 다시 조사해야 한다.

## 체크리스트

- [ ] API 스펙 3종 요청
- [ ] 더미 문서 20장 (함정 3장 포함)
- [ ] `labels.csv` / `scenarios.csv`
- [ ] `evaluate.py` (가짜 응답으로 먼저)
- [ ] 진짜 API 연결 후 첫 측정
- [ ] 매일 실행 → 공유
- [ ] 삭제 검증 테스트
- [ ] 배포 URL 가용성 확인
