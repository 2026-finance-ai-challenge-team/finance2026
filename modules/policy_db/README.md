# ProofBridge policy DB

하나은행 법인계좌 개설 한 사례를 SQLite에 저장한다. 자동 크롤링이나 다른
은행 정책은 이 모듈의 현재 범위가 아니다.

## 생성

저장소 루트에서 다음 명령을 실행한다.

    python -m modules.policy_db.database --replace

기본 출력 파일은 data/proofbridge.db다. 입력 정본은
data/seeds/hana_corporate_account.json, 스키마는 schema.sql이다.

## 조회

    from modules.policy_db.database import connect_database
    from modules.policy_db.repository import find_requirements

    connection = connect_database()
    result = find_requirements(
        connection,
        channel="branch",
        visitor_type="representative",
    )
    connection.close()

문서 분류 모듈이 사용할 시그니처는 list_document_signatures()로 가져온다.
현재 시그니처는 문서 이름과 초안 패턴만 입력한 상태라 모두
verified = false다. 실제 표본 검증 전에는 준비 완료 판정 근거로 사용하지 않는다.

documents 테이블과 시드 JSON은 같은 필드명을 사용한다. 문서 식별자는
doc_type, 한글 표시는 label_ko이며 배열 필드도 issuer_aliases,
title_patterns, required_anchors, negative_anchors, issued_at_labels라는
합의된 이름을 그대로 사용한다. SQLite에서는 배열 값만 JSON 문자열로 저장한다.

## 데이터 원칙

- 영업점 대표자·대리인의 공식 최소서류를 분리한다.
- 추가 권장자료를 공식 최소서류와 섞지 않는다.
- 비대면 준비물과 조건은 영업점 규칙과 분리한다.
- 인정기간은 문서 사전이 아니라 requirement_documents에 저장한다.
- 실제 개인정보나 사용자 문서는 이 DB에 저장하지 않는다.
