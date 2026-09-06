<div align="center">

<br>

# 🗂️ ProofBridge

### 흩어진 증빙과 금융 업무 사이를 연결합니다

**모르면 그냥 다 넣으세요. 필요한 것만 챙겨드릴게요.**

<br>

[![2026 금융 AI Challenge](https://img.shields.io/badge/2026_금융_AI_Challenge-참가_프로젝트-173F5F?style=for-the-badge)](https://daker.ai/public/hackathons/2026-finance-ai-challenge)
[![Service Planning](https://img.shields.io/badge/서비스_기획-Notion에서_보기-FFFFFF?style=for-the-badge&logo=notion&logoColor=black)](https://www.notion.so/3baf95a7decf80c98d38c63c8e80b66e)

<br>

[공개 데모](https://proofbridge-finance-2026.ryuky0896.chatgpt.site) · [프로젝트 제안서 PDF](output/pdf/proofbridge-project-proposal.pdf) · [차별화 조사](docs/DIFFERENTIATION.md) · [API 가입 체크리스트](docs/API_ONBOARDING.md)

> 현재 데모는 링크를 아는 누구나 접속할 수 있습니다. 실제 개인정보 문서는 업로드하지 말고 합성 샘플만 사용해 주세요.

</div>

---

## 서류는 이미 있는데, 무엇을 내야 할지 모를 때

ProofBridge는 먼저 **공공 마이데이터로 제출할 수 있는 증빙은 공식 경로로 안내**하고, 그 밖의 사문서·사진·원본은 한꺼번에 올려 목적·은행별 요건과 대조한 뒤 **디지털 제출·일괄인쇄·영업점 방문에 맞는 준비 완료 키트**로 만드는 AI 금융업무 준비 웹서비스입니다.

| 🏛️ 보낼 것은 보내고 | 🗂️ 나머지만 채우고 | ✅ 준비 완료로 만듭니다 |
| :--: | :--: | :--: |
| 공공 마이데이터 대상은 공식 제출 경로로 안내 | 사문서·사진을 분석해 누락·만료·불일치를 판정 | 디지털·인쇄·방문 채널에 맞는 실행 키트 생성 |

<p align="center">
  <b>업무 선택</b>　→　<b>마이데이터 가능분 분리</b>　→　<b>나머지 문서 검증</b>　→　<b>준비 완료</b>
</p>

### 결과는 다섯 가지로 단순하게

`준비 완료`　·　`추가 필요`　·　`기한 만료`　·　`정보 불일치`　·　`이번 업무에는 불필요`

> 첫 MVP는 **금융거래 목적 증빙 및 한도제한계좌 해제 준비**를 끝까지 완주하는 데 집중합니다.

### 현재 만들어진 데모

이 브랜치에는 **자연어 은행 업무 찾기**를 추가했습니다. 사용자의 상황을 LLM으로
해석해 등록된 은행·서비스에 연결합니다. 은행 미지정·모호한 업무는 사용자에게
확인받으며, 상속 업무는 공식 안내만 제공합니다. 서버의 `OPENAI_API_KEY`가 필요합니다.
설정·API 계약·검증 범위는 [자연어 업무 찾기](docs/TASK_INTENT.md)를 참고하세요.

기존 합성 문서 데모 범위:

- 로그인 없이 `카카오뱅크 · 생활비/공과금` 합성 시나리오를 클릭해 완주
- 공공 경로·직접 준비 문서·현장 지참물 분리
- `준비 완료`·`추가 필요`·`정보 불일치`·`이번 업무에는 불필요` 예시와 공식 근거 표시
- 공공·디지털·인쇄·방문 키트 미리보기, 큰 글자 전환, 제안서 PDF 열기

자연어 업무 찾기는 웹 서버에서 LLM을 호출합니다. 파일 분석·결과 삭제·ZIP 다운로드는
별도 분석 서버가 필요하며, 이 브랜치에는 그 서버 구현이 포함되어 있지 않습니다.
분석 서버 없이도 내장 합성 결과로 문서 데모를 체험할 수 있습니다. 지도 API는 미연결입니다.

<br>

<div align="center">

## Team ProofBridge

<table>
  <tr>
    <td align="center" width="200">
      <a href="https://github.com/bbcc1017">
        <img src="https://github.com/bbcc1017.png?size=140" width="110" height="110" alt="류연우 GitHub 프로필 사진"><br>
        <b>류연우</b>
      </a><br>
      <sub><a href="https://github.com/bbcc1017">@bbcc1017</a></sub><br>
      <sub><a href="mailto:bbcc1017@inha.edu">bbcc1017@inha.edu</a></sub>
    </td>
    <td align="center" width="200">
      <a href="https://github.com/oymin2001">
        <img src="https://github.com/oymin2001.png?size=140" width="110" height="110" alt="오영민 GitHub 프로필 사진"><br>
        <b>오영민</b>
      </a><br>
      <sub><a href="https://github.com/oymin2001">@oymin2001</a></sub><br>
      <sub><a href="mailto:oymin2001@inha.edu">oymin2001@inha.edu</a></sub>
    </td>
    <td align="center" width="200">
      <a href="https://github.com/chanbro0524">
        <img src="https://github.com/chanbro0524.png?size=140" width="110" height="110" alt="이찬형 GitHub 프로필 사진"><br>
        <b>이찬형</b>
      </a><br>
      <sub><a href="https://github.com/chanbro0524">@chanbro0524</a></sub><br>
      <sub><a href="mailto:dlcksgud208@naver.com">dlcksgud208@naver.com</a></sub>
    </td>
    <td align="center" width="200">
      <a href="https://github.com/grrlkk">
        <img src="https://github.com/grrlkk.png?size=140" width="110" height="110" alt="장찬우 GitHub 프로필 사진"><br>
        <b>장찬우</b>
      </a><br>
      <sub><a href="https://github.com/grrlkk">@grrlkk</a></sub><br>
      <sub><a href="mailto:grrlkk@inha.edu">grrlkk@inha.edu</a></sub>
    </td>
  </tr>
</table>

</div>

<br>

---

<details>
<summary><b>🎯 목표 MVP 범위와 판정 원칙</b></summary>

### 지원 범위

- **대상 금융기관**: KB국민은행, 우리은행, 카카오뱅크
- **대표 거래 목적**: 급여 수령, 생활비·공과금, 사업, 해외 사용
- **공공 증빙**: 공공 마이데이터·전자증명서로 처리 가능한 자료와 공식 경로 안내
- **입력**: 여러 PDF·JPG·PNG 파일의 일괄 업로드
- **처리**: 문서 종류·발급기관·명의·발급일·유효기간·핵심 필드 인식
- **결과**: 판정 근거, 부족 서류 발급 안내, 디지털 제출용 ZIP, 일괄인쇄 순서, 영업점 방문 체크리스트

### 다섯 가지 판정 상태

| 상태 | 의미 |
| :--: | :-- |
| 준비 완료 | 공개된 공식 기준에서 사용할 수 있는 것으로 확인된 서류 |
| 추가 필요 | 필수 또는 현재 조건에서 필요한 서류가 없는 상태 |
| 기한 만료 | 발급일 또는 유효기간 조건을 충족하지 못한 상태 |
| 정보 불일치 | 이름·주소·사업자번호·기간 등 확인 필드가 서로 다른 상태 |
| 이번 업무에는 불필요 | 인식은 됐지만 선택한 업무의 제출 묶음에서는 제외할 서류 |

문서 분류와 쉬운 설명에는 AI를 활용하지만, 최종 준비 상태는 **공식 출처를 구조화한 규칙**으로 판정합니다. 근거가 부족하면 준비 완료로 추측하지 않고 `확인 필요`로 남깁니다.

</details>

<details>
<summary><b>🧭 시스템 아키텍처</b></summary>

아래 구조는 기능 중심의 초기 설계이며, 구현 기술은 MVP 개발 과정에서 확정합니다.

```mermaid
graph LR
    A[사용자] --> B[웹서비스]
    B --> C[은행 업무 및 사용자 조건]
    C --> D[공공 마이데이터 가능분 분리]
    D --> E[공식 제출 경로 안내]
    C --> F[나머지 문서 일괄 업로드]
    F --> G[AI 문서 분류 및 정보 추출]
    G --> H[공식 규칙 기반 요건 대조]
    I[(은행별 업무·채널 규칙)] --> H
    E --> J[전체 준비 상태]
    H --> J
    J --> K[디지털 제출 키트]
    J --> L[일괄인쇄 키트]
    J --> M[영업점 방문 키트]
    B --> N[즉시 삭제 및 세션 종료 삭제]
```

</details>

<details>
<summary><b>🛠️ 현재 기술 스택</b></summary>

<br>

- React 19 + TypeScript
- Next.js 16
- CSS 기반 반응형·접근성 UI
- Next.js 서버 API와 OpenAI Responses API 기반 업무 의도 해석

업무 찾기 서버는 이 브랜치에 구현되어 있습니다. OCR·문서 판정·ZIP·삭제를 담당하는
외부 분석 서버의 통합과 배포 검증은 별도 작업입니다.

</details>

<details>
<summary><b>🚀 시작하기</b></summary>

```bash
git clone https://github.com/bbcc1017/finance2026.git
cd finance2026
cd apps/web
npm install
npm run dev
```

Node.js `>=22.13.0`이 필요합니다. `http://localhost:3000`에서 확인하고, 전체 검증은
`npm test`로 실행합니다. 합성 문서 데모에는 환경변수가 필요하지 않습니다.
자연어 업무 찾기는 서버의 `OPENAI_API_KEY` 설정이 필요합니다.

</details>

<details>
<summary><b>📁 저장소 구조</b></summary>

```text
finance2026/
├─ apps/web/                 # 웹 화면과 업무 찾기 서버
│  ├─ app/                   # 화면·스타일·메타데이터·API 경로
│  ├─ server/task-intent/    # 자연어 해석·은행/서비스 카탈로그
│  ├─ public/                # 제안서 PDF·소셜 이미지
│  └─ tests/                 # 업무 찾기·API·서버 렌더 검사
├─ docs/                     # 차별화 조사·API 가입 가이드
├─ output/pdf/               # 검수 완료 제안서
└─ scripts/                  # 제안서 재생성 스크립트
```

업무 카탈로그는 서비스 연결용이며 서류 요건 판정 규칙과 구분합니다.

</details>

<details>
<summary><b>🗓️ 개발 로드맵</b></summary>

- [x] 서비스 문제 정의 및 MVP 범위 설정
- [x] 공개 서비스 차별화 조사와 공공 마이데이터 역할 구분
- [x] 클릭 가능한 프론트엔드 청사진과 제안서 PDF
- [ ] 금융기관별 최신 공식 제출 요건 확정
- [ ] 문서 분류·정보 추출 방식 검증
- [ ] 제출 요건 판정 규칙 구현
- [ ] 원본 보존 제출용 ZIP과 FIN MAP 안내 구현
- [ ] 개인정보 삭제·마스킹 및 접근성 검증
- [ ] 사용자 테스트와 문서화

</details>

<details>
<summary><b>🔒 개인정보 보호와 서비스 한계</b></summary>

- 원본 문서는 변경하지 않으며 사용자가 분석 결과와 함께 즉시 삭제할 수 있도록 합니다.
- 세션 종료 후 원본과 파생 데이터를 삭제하고, 로그에 민감한 원문을 남기지 않습니다.
- 민감 문서를 제3자 인쇄소로 자동 전송하지 않습니다.
- ProofBridge는 금융기관의 심사나 승인 여부를 보장하지 않습니다.
- 공공 마이데이터 이용기관 승인을 받기 전에는 실제 연동·전송이 아니라 공식 이용 경로를 안내합니다.
- 결과는 `승인 가능`이 아니라 **공개 기준 사전 점검 결과**로 안내합니다.

</details>

<br>

<div align="center">

<sub>ProofBridge · 2026 금융 AI Challenge</sub>

</div>
