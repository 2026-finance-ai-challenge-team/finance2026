# 검증 하네스 작업 지시서

> 담당: 찬우 · 브랜치 `feat/eval` · 대상: 하나은행 법인계좌 개설 / 대면 / 본인
> 지금은 조합이 하나뿐이므로 **채널 비교(Q2)는 범위 밖**이다.

## 목표

파이프라인이 **"이거 부족해요"를 제대로 말하는지** 자동으로 채점한다.

가장 위험한 실패는 **부족한데 부족하다고 안 하는 것**이다.
사용자가 그 말을 믿고 은행에 갔다가 거절당한다. 반대(과잉 요구)는 훨씬 덜 심각하다.
→ 전체 정확도가 아니라 **틀린 방향**을 본다.

## 만들 것

```
eval/
├── generate.py        합성 문서 PDF + labels.csv 생성
├── degrade.sh         PDF → 이미지·회전·저조도 변환
├── make_scenarios.py  scenarios.csv 생성 (하나씩 빼기 자동 + 함정 수동)
├── evaluate.py        채점기
├── templates/         문서 HTML 템플릿
├── samples/           생성 결과
├── labels.csv         자동 생성
├── scenarios.csv      자동 생성 + 손으로 함정 추가
└── reports/           일자별 결과
```

---

## 문서 10종 (찬형 DB `documents` 테이블)

합성 문서에는 아래 **제목**과 **필수 앵커**가 실제 텍스트로 들어가야 한다.
분류 모듈이 이 문자열을 찾는다.

| doc_type | 한글명 | 발급기관 | 제목 | 필수 앵커 | 발급일 라벨 | 문서번호 라벨 |
|---|---|---|---|---|---|---|
| `business_registration_certificate` | 사업자등록증 | 국세청 | 사업자등록증 | 사업자등록번호, 상호, 대표자 | — | 사업자등록번호 |
| `business_registration_verification` | 사업자등록증명 | 국세청 | 사업자등록증명 | 사업자등록번호, 상호, 대표자 | 발급일자 | 발급번호 |
| `corporate_registry_certificate` | 법인등기사항전부증명서 | 대한민국 법원 | 등기사항전부증명서 | 법인등록번호, 상호, 본점 | 발행일 | 발행번호 |
| `corporate_seal_certificate` | 법인인감증명서 | 대한민국 법원 | 법인인감증명서 | 법인등록번호, 상호, 인감 | 발행일 | 발행번호 |
| `power_of_attorney` | 법인 위임장 | 해당 법인 | 위임장 | 위임인, 수임인, 위임사항 | 작성일 | — |
| `shareholder_registry` | 주주명부 | 해당 법인 | 주주명부 | 주주, 주식수 | 작성일 | — |
| `share_change_statement` | 주식등변동상황명세서 | 해당 법인 | 주식등변동상황명세서 | 사업연도, 주주, 주식수 | 작성일 | — |
| `articles_of_incorporation` | 정관 | 해당 법인 | 정관 | 총칙, 목적, 상호 | 작성일 | — |
| `vat_tax_base_certificate` | 부가가치세과세표준증명 | 국세청 | 부가가치세 과세표준증명 | 사업자등록번호, 과세기간, 과세표준 | 발급일자 | 발급번호 |
| `standard_financial_statement_certificate` | 표준재무제표증명 | 국세청 | 표준재무제표증명 | 사업자등록번호, 사업연도, 재무제표 | 발급일자 | 발급번호 |

### 헷갈리는 쌍 (negative pair)

DB에 `negative_anchors`로 방어가 걸려 있다. **그게 실제로 작동하는지가 검증 대상.**

1. 사업자등록증 ↔ 사업자등록증**명**
2. 주주명부 ↔ 주식등변동상황명세서 (동시에 **대체 관계**이기도 함)
3. 법인인감증명서 ↔ **개인**인감증명서 (개인은 10종에 없음 → `판단 불가`가 정답)

---

## 1. `generate.py`

HTML 템플릿을 PDF로 렌더링하고, 동시에 `labels.csv`를 쓴다.

**요구사항**

- 템플릿은 `templates/{doc_type}.html`, Jinja2 등으로 이름·날짜·번호를 치환
- 제목은 **본문의 1.5배 이상 크기, 문서 상단 30% 이내**에 배치
  (분류 모듈이 글자 좌표로 높이를 재서 제목을 찾는다)
- 표 구조로 필드 배치 (실제 증명서가 대부분 표)
- 날짜는 **한 문서에 2개 이상** 넣는다 — 발급일 + 조회기준일/작성일
  엉뚱한 날짜를 집는지 확인하는 함정
- 날짜 형식을 문서마다 다르게: `2026. 7. 20.` / `2026년 7월 20일` / `2026-07-20`
- 개인정보는 전부 가상값. 사업자번호 `123-45-67890`, 법인등록번호 `110111-1234567`,
  주민번호가 필요하면 `900101-1******` 형태로 마스킹
- PDF 출력은 wkhtmltopdf 또는 Playwright

**생성 목록**

```
정상본        10종 각 1장
기한만료      corporate_registry_certificate (발급일 1년 전)
함정          개인인감증명서 (10종에 없음 → 판단 불가가 정답)
무관          취업후기.pdf (아무 산문)
불량          빈페이지.pdf (내용 없는 1쪽)
```

**동시에 `labels.csv` 출력**

```csv
file,expected_doc_type,expected_relevance
사업자등록증.pdf,business_registration_certificate,관련
사업자등록증명.pdf,business_registration_verification,관련
법인등기부.pdf,corporate_registry_certificate,관련
법인등기부_기한만료.pdf,corporate_registry_certificate,관련
개인인감증명서.pdf,,판단 불가
취업후기.pdf,,판단 불가
빈페이지.pdf,,판단 불가
```

- `expected_doc_type`이 비면 → `판단 불가`가 정답
- **명의·주소 등 내용 필드는 넣지 않는다.** 분류 모듈이 안 뽑기로 한 값이다

---

## 2. `degrade.sh`

**현재 합성 PDF는 텍스트 레이어가 있어 pypdf에서 끝난다. CLOVA 경로를 전혀 안 탄다.**
실제 사용자는 사진을 올리므로 이미지 버전이 반드시 필요하다.

```bash
pdftoppm -png -r 150 입력.pdf scan
convert scan-1.png -rotate 7 기울어짐.png
convert scan-1.png -brightness-contrast -30x-15 어두움.png
convert scan-1.png -blur 0x1.5 흐림.png
```

최소 3종(사업자등록증, 법인등기부, 주주명부)은 이미지 버전을 만든다.
`labels.csv`에 **같은 `expected_doc_type`으로** 추가한다.

> PDF에선 맞히고 이미지에선 틀리면, 그게 찾아야 할 문제다.

### 페이지 혼합 함정

"8쪽 중 1쪽만 스캔본"이 실물에서 실제로 나왔다. 1건은 이렇게 만든다.

```bash
qpdf 원본.pdf --pages . 1 -- p1.pdf
pdftoppm -png -r 150 p1.pdf p1img
img2pdf p1img-1.png -o p1_scan.pdf
qpdf --empty --pages p1_scan.pdf 원본.pdf 2-z -- 혼합.pdf
```

---

## 3. `make_scenarios.py`

**필수 서류 목록은 DB에서 읽는다.** 못 읽으면 아래 하드코딩으로 폴백하고, 폴백했음을 콘솔에 출력한다.

```sql
SELECT d.doc_type, rd.issued_within_days, rd.choice_group, rs.requirement_level
FROM requirement_documents rd
JOIN documents d ON d.id = rd.document_id
JOIN requirement_sets rs ON rs.id = rd.requirement_set_id
WHERE rs.channel = 'branch' AND rs.visitor_type = 'representative';
```

**폴백용 하드코딩** (DB 확인 전 임시. 확인되면 이 블록만 지운다)

```python
FALLBACK_REQUIRED = [
    "business_registration_certificate",
    "corporate_registry_certificate",
    "corporate_seal_certificate",
    "articles_of_incorporation",
]
FALLBACK_CHOICE_GROUPS = {
    "beneficial_owner_evidence": ["shareholder_registry", "share_change_statement"],
}
```

### 자동 생성 — 하나씩 빼기

```
sc0        : 필수 전부            → 부족 없음
sc_{doc}   : 필수에서 doc 하나 제외 → doc만 부족
```

필수가 4개면 5줄. **뺐는데 부족으로 안 나오면 그 서류는 목록에만 있고 실제로는 안 보는 것이다.**

### 손으로 추가할 함정

```csv
id,files,expect
t1,"필수전부+주주명부",대체서류 충족
t2,"필수전부+주식등변동상황명세서",대체서류 충족
t3,"필수전부",대체서류 부족
t4,"필수전부+주주명부+주식등변동상황명세서",둘 다 요구하지 않음
t5,"사업자등록증.pdf,사업자등록증.pdf",중복을 2개로 세지 않음
t6,"법인등기부_기한만료.pdf",기한 만료로 표시
t7,"취업후기.pdf",전부 부족 · 안 죽음
t8,"",파일 0개 · 안 죽음
t9,"사업자등록증명.pdf",사업자등록증으로 오인하지 않음
```

**t3과 t4가 가장 중요하다.** 대체서류 로직이 잘못되면
둘 다 없는데 통과하거나(치명), 하나만 냈는데 둘 다 요구한다(과잉).

---

## 4. `evaluate.py`

`labels.csv` + `scenarios.csv`를 읽고 파이프라인을 호출해 채점한다.

### 파이프라인 호출부는 어댑터로 분리

**호출 방식이 아직 확정 전이다. 반드시 함수 하나로 격리해서 나중에 여기만 갈아끼우게 한다.**

```python
# ─── 어댑터: 파이프라인 확정되면 여기만 수정 ───
def classify_one(path: str) -> dict:
    """returns {"doc_type": str|None, "confidence": float, "relevance": str}"""
    ...

def judge(file_paths: list[str]) -> dict:
    """returns {"missing": [doc_type], "expired": [doc_type], "notes": [...]}"""
    ...
# ──────────────────────────────────────────
```

우선순위: ① 파이썬 함수 직접 import → ② CLI `python -m modules.doc_classify.cli --report` 파싱 → ③ HTTP
저장소 코드를 읽고 가능한 방식을 택한다. **웹 서버는 띄우지 않는다.**

### 출력

```
[분류]
  정확도             14/16
  판단불가 정답      3/3
  [치명] 실패→불필요  0건
  [치명] 유사쌍 혼동  0건
  [혼동] 등기부_사진.png : corporate_registry_certificate → 판단 불가

[판정]
  누락 탐지 재현율   4/4
  [치명] 부족 미탐지  0건
  [실패] t3 — 대체서류 둘 다 없는데 부족으로 안 나옴
  [실패] t5 — 중복 파일을 2개로 셈

[규칙]
  출처 커버리지      14/14 (100%)
```

### 채점 규칙

- **`[치명]` 항목은 0이 아니면 종료 코드 1** (CI에서 바로 실패)
- 분류 정확도는 참고 숫자. 통과선 두지 않음
- 결과를 `reports/YYYY-MM-DD.md`로도 저장

### 출처 커버리지

```sql
SELECT COUNT(*) FILTER (WHERE source_url IS NOT NULL AND checked_at IS NOT NULL) * 100.0 / COUNT(*)
FROM documents;
```

`requirement_documents`, `policy_conditions`도 같은 방식으로 센다.

---

## 지금은 휴리스틱, 나중에 교체

아래 세 곳은 임시다. 코드에 `# TODO(swap)` 주석을 남긴다.

| 위치 | 지금 | 나중 |
|---|---|---|
| `make_scenarios.py` 필수 목록 | 하드코딩 폴백 | DB 조회 |
| `evaluate.py` 어댑터 | CLI 파싱 or 직접 import | 배포용 API |
| 채널·방문자 | `branch` / `representative` 고정 | 파라미터화 |

---

## 주의

- **실제 개인·법인 서류를 절대 쓰지 않는다.** 전부 합성.
- 합성 문서는 저장소에 커밋해도 되지만, 실물이 섞이지 않도록 `samples/`만 쓴다.
- 커밋 규칙: `<type>: <한글 요약>` — `test:` `feat:` `fix:` `docs:` `chore:`
  예) `test: 합성 법인서류 10종 추가`

## 완료 기준

```bash
python eval/generate.py          # PDF + labels.csv 생성
bash   eval/degrade.sh           # 이미지 버전 생성
python eval/make_scenarios.py    # scenarios.csv 생성
python eval/evaluate.py          # 채점 결과 출력
```

네 줄이 순서대로 돌고 마지막에 숫자가 나오면 끝.
