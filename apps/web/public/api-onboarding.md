# ProofBridge API 가입·키 발급 가이드

> 확인 기준일: 2026-08-12  
> 현재 클릭 데모는 합성 데이터만 사용하므로 외부 API 키가 필요 없다.

## 먼저 준비할 것

| 우선순위 | 서비스 | 사용 목적 | 가입·발급 절차 | 환경변수 |
|---:|---|---|---|---|
| 1 | 금융결제원 FIN MAP | 은행 지점·ATM, 현재 운영, 접근성·특화점포 검색 | 개발자 가입·이메일 인증 → FIN MAP 서비스 신청 → Client ID/Secret → Access Token | `KFTC_CLIENT_ID`, `KFTC_CLIENT_SECRET` |
| 1 | Kakao Local | 주변 무인프린트점·인쇄소 검색 | Kakao Developers 앱 생성 → 카카오맵 활성화 → REST API 키 | `KAKAO_REST_API_KEY` |
| 2 | NAVER Cloud CLOVA OCR | 한국어 사진·스캔 페이지만 OCR | NCP 가입·결제 → CLOVA OCR 이용 신청 → Domain 생성 → Secret Key·API Gateway Invoke URL | `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET_KEY` |

가입 링크:

- [FIN MAP API](https://developers.kftc.or.kr/dev/openapi/map/all) · [금융결제원 개발자 시작하기](https://developers.kftc.or.kr/dev/starter/starter)
- [Kakao Local 개발 가이드](https://developers.kakao.com/docs/latest/ko/local/dev-guide) · [쿼터·요금](https://developers.kakao.com/docs/ko/getting-started/quota)
- [CLOVA OCR 이용 신청](https://guide.ncloud-docs.com/docs/clovaocr-start) · [Domain·Secret 발급](https://guide.ncloud-docs.com/docs/clovaocr-domain) · [보안 FAQ](https://guide.ncloud-docs.com/docs/clovaocr-faq)

### 선택 이유

- FIN MAP은 은행 지점과 ATM이라는 금융 전용 데이터를 제공한다. 공개 문서에서 운영 쿼터·비용은 확인되지 않아 신청 후 금융결제원에 별도 확인한다.
- Kakao Local은 인쇄소 위치 탐색에만 사용한다. 인쇄 가능 여부나 영업시간을 검증하지 않았다면 확정 표현을 하지 않는다.
- CLOVA OCR은 한국어 합성 금융문서 벤치마크의 첫 후보다. 모든 페이지가 아니라 내장 텍스트가 부족한 페이지만 전송한다.

## 승인 후에만 가능한 공공 연계

| 서비스 | 실제 절차 | MVP 처리 |
|---|---|---|
| 공공 마이데이터 | 신청서 제출 → 환경조사 → 현장실사 → 심의 → 승인·보안저장소·인증서 등록 | 대상 여부와 공식 이용 경로만 안내 |
| 전자증명서·디지털서비스개방 | 수요기관 선정 → 약관 → 검증 승인 → 기관 연동 테스트 → 운영 키 | 정부24·전자문서지갑 링크아웃 |

공공 마이데이터는 일반 개발자가 즉시 발급받는 API 키형 서비스가 아니다. [이용기관 신청 절차](https://adm.mydata.go.kr/intro/addHelpPage.do?type=index)는 신청일부터 3개월 이내 결과 통보와 보안·현장 검토를 안내한다. 전자증명서도 [민간 서비스 연계 절차](https://openservice.go.kr/serviceProc)를 거친 뒤 운영 키가 발급된다.

## OCR 비교 후보

| 후보 | 판단 | 보존·보안 확인 사항 |
|---|---|---|
| NAVER CLOVA OCR | 첫 한국어 벤치마크 권고 | 공식 FAQ상 원본·결과를 저장하거나 모델 개선에 이용하지 않음 |
| Google Cloud Vision | CLOVA 비교 후보 | 온라인 요청은 메모리 처리 후 디스크에 저장하지 않고 학습에 사용하지 않음 |
| Azure Document Intelligence | 표·복잡한 구조가 실제로 필요할 때 | 입력·결과를 24시간 저장하므로 처리 직후 Delete Analyze Result 호출 필요 |
| AWS Textract | 제외 | 공식 지원 언어에 한국어가 없음 |

공식 문서: [Google Vision 데이터 사용](https://cloud.google.com/vision/docs/data-usage), [Vision 가격](https://cloud.google.com/vision/pricing), [Azure 데이터 보존](https://learn.microsoft.com/en-us/legal/cognitive-services/document-intelligence/data-privacy-security), [AWS Textract 언어 제한](https://docs.aws.amazon.com/textract/latest/dg/textract-best-practices.html).

## LLM은 나중에 하나만

합성 샘플과 규칙 엔진이 전체 흐름을 통과한 뒤, 낮은 신뢰도 문서 분류·필드 정규화·쉬운 설명 품질을 비교할 때 하나만 선택한다.

- OpenAI API: `OPENAI_API_KEY`
- HyperCLOVA X: `CLOVA_STUDIO_API_KEY`
- Google Vertex AI: 서비스 계정 또는 Application Default Credentials

LLM에는 원본 전체가 아니라 마스킹·최소화한 OCR 필드를 우선 전달하고, 최종 `준비 완료` 판정에는 사용하지 않는다.

## 키 없이 먼저 구현할 기능

- 브라우저 File API: 다중 선택·드래그앤드롭·MIME·크기 확인
- PDF.js: 텍스트 PDF 파싱과 내장 텍스트 추출
- `crypto.subtle`: 원본 해시와 불변성 확인
- JSZip: 원본·index·checklist 묶음 생성
- Browser Geolocation: HTTPS에서 사용자 동의 후 현재 위치 사용

새 의존성은 해당 기능을 실제로 구현하는 시점에만 추가한다.

## 비밀키 운영 체크리스트

- `.env.local` 또는 배포 서비스의 서버 전용 Secret에 저장
- 브라우저 번들·Git·README·스크린샷에 키를 넣지 않음
- 파일명·OCR 원문·주민번호·계좌번호·요청 본문을 로그에 남기지 않음
- 허용 도메인·최소 권한·키 회전 절차 설정
- 개발·운영 키 분리
- 외부 AI 호출은 사용자 동의·보존정책·삭제 동작을 검증한 뒤 활성화

복사 시작점은 [`apps/web/.env.example`](../apps/web/.env.example)이다.
