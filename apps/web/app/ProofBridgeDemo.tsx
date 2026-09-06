"use client";

import { useState } from "react";

import { completionOf, loadResult, toRows } from "./classifyResult";

const steps = ["업무 고르기", "공공 경로 나누기", "남은 서류 모으기", "준비 키트 확인"];

// 화면은 더 이상 결과를 직접 적지 않는다. 분류 모듈의 출력 계약(v1.0)을 읽어 그린다.
// 지금은 합성 샘플 JSON이고, 백엔드가 생기면 classifyResult.ts의 loadResult()만 바꾼다.
const classifyResult = loadResult();
const resultItems = toRows(classifyResult);

const completion = completionOf(resultItems);
const missingNames = resultItems
  .filter((item) => item.status === "추가 필요")
  .map((item) => item.name);

const kitCopy = {
  public: {
    title: "공공 제출 목록",
    body: "정부24 또는 지원 기관에서 주민등록등본을 선택하고, 수취기관을 확인한 뒤 전송하세요.",
    action: "공식 경로 열기",
    href: "https://plus.gov.kr/portal/custcntr/utztngd/elprdocgd",
  },
  digital: {
    title: "디지털 제출 키트",
    body: "현재 주소의 관리비 고지서를 보완하면 원본, 안전한 파일명, 업로드 순서와 체크리스트를 묶을 예정이에요.",
    action: "보완 항목 보기",
    href: "#results",
  },
  print: {
    title: "일괄인쇄 키트",
    body: "카카오뱅크 공식 안내처럼 출력 후 촬영이 필요할 때, 출력 대상·순서·부수를 한 장으로 정리해요.",
    action: "공식 안내 확인",
    href: "https://blog.kakaobank.com/posts/service-limit-account",
  },
  branch: {
    title: "영업점 방문 키트",
    body: "신분증, 원본 지참물, 창구에서 말할 업무명과 접근성 조건을 한 화면에 모을 예정이에요.",
    action: "지점 기능은 다음 단계",
    href: "#roadmap",
  },
} as const;

type KitKey = keyof typeof kitCopy;

export function ProofBridgeDemo() {
  const [step, setStep] = useState(1);
  const [furthestStep, setFurthestStep] = useState(1);
  const [sampleLoaded, setSampleLoaded] = useState(false);
  const [kit, setKit] = useState<KitKey>("public");
  const [largeText, setLargeText] = useState(false);

  const go = (next: number) => {
    setStep(next);
    setFurthestStep((current) => Math.max(current, next));
  };

  const resetDemo = () => {
    setStep(1);
    setFurthestStep(1);
    setSampleLoaded(false);
    setKit("public");
  };

  return (
    <div className={largeText ? "site-shell large-text" : "site-shell"}>
      <a className="skip-link" href="#main">본문으로 바로가기</a>

      <header className="topbar">
        <a className="brand" href="#top" aria-label="ProofBridge 처음으로">
          <span className="brand-mark" aria-hidden="true"><i /><i /></span>
          <span>ProofBridge</span>
        </a>
        <nav aria-label="주요 메뉴">
          <a href="#difference">차별점</a>
          <a href="#demo">데모</a>
          <a href="#roadmap">구현 로드맵</a>
        </nav>
        <button
          className="text-size-button"
          type="button"
          aria-pressed={largeText}
          onClick={() => setLargeText((value) => !value)}
        >
          {largeText ? "기본 글자" : "글자 크게"}
        </button>
      </header>

      <main id="main">
        <section className="hero" id="top">
          <div className="hero-copy">
            <p className="eyebrow"><span />2026 금융 AI Challenge · 합성 샘플 기획 데모</p>
            <h1>서류를 몰라도,<br /><em>업무는 끝까지.</em></h1>
            <p className="hero-lead">
              공공 마이데이터로 보낼 것은 공식 경로로 보내고, 남은 사진·사문서·원본만 골라
              디지털 제출·인쇄·방문에 맞는 준비 키트로 완성합니다.
            </p>
            <p className="core-copy">“모르면 그냥 다 넣으세요. 필요한 것만 챙겨드릴게요.”</p>
            <div className="hero-actions">
              <a className="button primary" href="#demo">합성 샘플로 체험하기</a>
              <a className="button secondary" href="#difference">왜 다른지 보기</a>
            </div>
            <div className="trust-line" aria-label="데모 안전 안내">
              <span>로그인 없음</span><span>실제 개인정보 업로드 없음</span><span>공식 출처 우선</span>
            </div>
          </div>

          <div className="bridge-scene" role="img" aria-label="흩어진 서류가 세 가지 실행 키트로 정리되는 입체적인 다리">
            <div className="scene-label"><span>PROOFBRIDGE SYSTEM</span><b>3 documents · 1 clear route</b></div>
            <div className="paper-stack input-stack" aria-hidden="true">
              <div className="paper paper-a"><small>사문서</small><b>관리비 고지서</b><i /></div>
              <div className="paper paper-b"><small>공공 증빙</small><b>주민등록등본</b><i /></div>
              <div className="paper paper-c"><small>현장 지참</small><b>신분증</b><i /></div>
            </div>
            <div className="bridge-rail" aria-hidden="true">
              <span>공공 경로</span><span>남은 증빙</span><span>현장 준비</span>
            </div>
            <div className="kit-stack" aria-hidden="true">
              <div><small>01</small><b>디지털 제출</b></div>
              <div><small>02</small><b>일괄인쇄</b></div>
              <div><small>03</small><b>영업점 방문</b></div>
            </div>
            <p className="scene-caption">전달은 공공 인프라가, 남은 준비의 완성은 ProofBridge가.</p>
          </div>
        </section>

        <section className="evidence-strip" aria-label="문제 근거">
          <p><b>확인된 문제</b> 금융위원회는 증빙 안내 부족으로 영업점을 여러 번 방문하는 문제와 공공 마이데이터를 통한 실물서류 축소 필요를 공개했습니다.</p>
          <a href="https://www.fsc.go.kr/po010101/82205" target="_blank" rel="noreferrer">공식 근거 보기 <span aria-hidden="true">↗</span></a>
        </section>

        <section className="section difference" id="difference">
          <div className="section-heading">
            <p className="eyebrow"><span />겹치지 않고 이어 붙이기</p>
            <h2>공공 마이데이터를<br />경쟁자가 아닌 <em>첫 번째 레일</em>로.</h2>
            <p>차별점은 데이터 전송도, OCR 자체도 아닙니다. 서로 끊긴 공식 경로와 생활 서류, 마지막 행동을 한 흐름으로 잇는 데 있습니다.</p>
          </div>

          <div className="role-map">
            <article>
              <span className="role-number">공공 01</span>
              <h3>공식 데이터 전달</h3>
              <p>정보주체의 동의로 행정정보를 본인이나 지정한 곳에 안전하게 보냅니다.</p>
              <strong>공공 마이데이터·전자증명서의 역할</strong>
            </article>
            <div className="role-connector" aria-hidden="true">+</div>
            <article>
              <span className="role-number">은행 02</span>
              <h3>기관 안의 접수·심사</h3>
              <p>각 은행 앱이나 영업점이 자기 업무에 맞는 증빙을 받고 심사합니다.</p>
              <strong>금융기관의 역할</strong>
            </article>
            <div className="role-connector" aria-hidden="true">+</div>
            <article className="proofbridge-role">
              <span className="role-number">연결 03</span>
              <h3>남은 준비를 완성</h3>
              <p>사문서·사진·원본과 채널 조건을 대조해 사용자의 다음 행동까지 정리합니다.</p>
              <strong>ProofBridge의 역할</strong>
            </article>
          </div>

          <div className="claim-note">
            <b>공공 마이데이터 위의 금융업무 완성 계층</b>
            <p>공식 경로 우선 분리 → 남은 문서의 AI 이해 → 출처 기반 규칙 판정 → 디지털·인쇄·방문 키트를 한국 금융 초보자용 한 흐름으로 결합합니다.</p>
            <span>동일 서비스의 부재나 국내 최초를 주장하지 않습니다.</span>
          </div>
        </section>

        <section className="section demo-section" id="demo">
          <div className="demo-intro">
            <div>
              <p className="eyebrow light"><span />클릭 가능한 청사진</p>
              <h2>설명 없이도 끝까지 가는<br />한 번의 준비 경험</h2>
            </div>
            <div className="demo-safety">
              <b>현재는 UI·규칙 흐름 데모</b>
              <p>AI 분석과 실제 전송은 연결하지 않았습니다. 아래 파일과 판정은 모두 합성 예시입니다.</p>
            </div>
          </div>

          <div className="demo-frame">
            <ol className="stepper" aria-label="데모 진행 단계">
              {steps.map((label, index) => {
                const number = index + 1;
                return (
                  <li key={label} className={number === step ? "active" : number < step ? "done" : ""}>
                    <button
                      type="button"
                      onClick={() => go(number)}
                      disabled={number > furthestStep}
                      aria-current={number === step ? "step" : undefined}
                    >
                      <span>{number < step ? "✓" : number}</span>{label}
                    </button>
                  </li>
                );
              })}
            </ol>

            <div className="demo-panel">
              {step === 1 && (
                <div className="step-content">
                  <div className="step-copy">
                    <span className="step-kicker">1 / 4</span>
                    <h3>서류 이름 말고,<br />하려는 일부터 알려주세요.</h3>
                    <p>이번 데모는 공개 기준이 가장 또렷한 한 가지 합성 시나리오만 완주합니다.</p>
                  </div>
                  <div className="form-card">
                    <label htmlFor="bank">어느 은행 업무인가요?</label>
                    <select id="bank" defaultValue="kakao">
                      <option value="kakao">카카오뱅크</option>
                      <option disabled>KB국민은행 · 규칙 검증 예정</option>
                      <option disabled>우리은행 · 최신 근거 확인 예정</option>
                    </select>
                    <label htmlFor="task">무엇을 하려 하나요?</label>
                    <select id="task" defaultValue="limit">
                      <option value="limit">한도계좌 해제 준비</option>
                    </select>
                    <label htmlFor="purpose">통장을 주로 어디에 쓰나요?</label>
                    <select id="purpose" defaultValue="utility">
                      <option value="utility">생활비·공과금</option>
                      <option disabled>급여 수령 · 다음 시나리오</option>
                      <option disabled>사업 · 다음 시나리오</option>
                    </select>
                    <fieldset>
                      <legend>도움이 필요한 방식도 골라주세요.</legend>
                      <label className="check-row"><input type="checkbox" defaultChecked /> 쉬운 문장으로 설명</label>
                      <label className="check-row"><input type="checkbox" /> 큰 글자·영업점 방문 중심</label>
                    </fieldset>
                    <button className="button primary full" type="button" onClick={() => go(2)}>무엇을 준비할지 보기</button>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="step-content split-step">
                  <div className="step-copy">
                    <span className="step-kicker">2 / 4</span>
                    <h3>먼저 세 갈래로<br />나눠드릴게요.</h3>
                    <p>공공 증빙을 다시 내려받게 하지 않고, 사용자가 실제로 보완할 것만 남깁니다.</p>
                  </div>
                  <div className="split-board">
                    <article className="lane public-lane">
                      <span>공공 경로</span><b>주민등록등본</b><p>정부24·전자문서지갑에서 발급·제출</p><i>다시 업로드하지 않아요</i>
                    </article>
                    <article className="lane direct-lane">
                      <span>직접 준비</span><b>관리비 고지서</b><p>현재 주소가 보이는 원본 출력·사진</p><i>내용과 주소를 확인해요</i>
                    </article>
                    <article className="lane onsite-lane">
                      <span>현장 지참</span><b>신분증</b><p>방문하거나 본인 확인할 때 준비</p><i>파일로 위장하지 않아요</i>
                    </article>
                    <div className="split-actions">
                      <button className="button ghost" type="button" onClick={() => go(1)}>이전</button>
                      <button className="button primary" type="button" onClick={() => go(3)}>남은 서류 모으기</button>
                    </div>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="step-content upload-step">
                  <div className="step-copy">
                    <span className="step-kicker">3 / 4</span>
                    <h3>서류명을 몰라도<br />있는 것을 한꺼번에.</h3>
                    <p>실제 업로드·OCR은 다음 개발 단계입니다. 지금은 합성 묶음으로 결과 화면을 검토합니다.</p>
                  </div>
                  <div className="upload-card">
                    {!sampleLoaded ? (
                      <>
                        <div className="upload-symbol" aria-hidden="true"><span>PDF</span><span>JPG</span><span>PNG</span></div>
                        <h4>실제 개인정보 문서는 넣지 마세요.</h4>
                        <p>이 버튼은 이름·주소·날짜를 모두 지어낸 합성 샘플 {classifyResult.documents.length}개를 불러옵니다.</p>
                        <button className="button primary" type="button" onClick={() => setSampleLoaded(true)}>합성 샘플 불러오기</button>
                        <button className="future-button" type="button" disabled>직접 파일 넣기 · AI 연결 후 제공</button>
                      </>
                    ) : (
                      <>
                        <div className="loaded-head"><div><span aria-hidden="true">✓</span><b>합성 샘플 {classifyResult.documents.length}개를 불러왔어요.</b></div><button type="button" onClick={() => setSampleLoaded(false)}>비우기</button></div>
                        <ul className="file-list">
                          {classifyResult.documents.map((doc) => (
                            <li key={doc.file_id}>
                              <span>{doc.media.kind.toUpperCase()}</span>
                              <div>
                                <b>{doc.source_name}</b>
                                <small>{doc.media.pages}쪽 · 아직 무슨 문서인지 모르는 상태</small>
                              </div>
                            </li>
                          ))}
                        </ul>
                        <div className="split-actions">
                          <button className="button ghost" type="button" onClick={() => go(2)}>이전</button>
                          <button className="button primary" type="button" onClick={() => go(4)}>예시 분석 결과 보기</button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}

              {step === 4 && (
                <div className="result-view" id="results">
                  <div className="result-summary">
                    <div>
                      <span className="step-kicker">4 / 4 · 공개 기준 사전 점검 예시</span>
                      <h3>
                        {missingNames.length > 0
                          ? <>{missingNames[0]}<br />{missingNames.length > 1 ? `외 ${missingNames.length - 1}건이 ` : ""}더 필요해요.</>
                          : <>가진 문서를<br />모두 확인했어요.</>}
                      </h3>
                      <p>은행의 승인·통과를 보장하는 결과가 아닙니다. 공개된 예시 기준으로 다음 행동을 정리한 화면입니다.</p>
                    </div>
                    <div className="score-ring" aria-label={`이번 업무 필요 항목 ${completion.total}건 중 ${completion.have}건 확보`}><b>{completion.percent}</b><span>%</span><small>{completion.have}/{completion.total} 확보</small></div>
                  </div>

                  <div className="result-grid">
                    <div className="documents-card">
                      <h4>문서와 준비물 <span>{resultItems.length}</span></h4>
                      <ul>
                        {resultItems.map((item) => (
                          <li key={item.key}>
                            <div className="doc-title"><span className={`status-dot ${item.tone}`} /><div><b>{item.name}</b><small>{item.meta}</small></div></div>
                            <div className="doc-result"><strong className={item.tone}>{item.status}</strong><p>{item.note}</p></div>
                          </li>
                        ))}
                      </ul>
                      <details>
                        <summary>다섯 가지 상태 모두 보기</summary>
                        <p><b>준비 완료 · 추가 필요 · 기한 만료 · 정보 불일치 · 이번 업무에는 불필요</b></p>
                        <p>기한 만료는 실제 공식 규칙에 유효기간 근거가 있을 때만 표시합니다.</p>
                        <p>위 화면은 <b>문서 분류 모듈의 실제 출력 스키마(v{classifyResult.schema_version})</b>를 읽어 그립니다. <b>준비 완료</b>와 <b>정보 불일치</b>는 규칙 엔진이 판정하는 상태라 아직 표시하지 않습니다.</p>
                      </details>
                    </div>

                    <div className="kit-card">
                      <h4>채널별 준비 키트</h4>
                      <div className="kit-tabs" role="tablist" aria-label="준비 키트 종류">
                        {([
                          ["public", "공공"], ["digital", "디지털"], ["print", "인쇄"], ["branch", "방문"],
                        ] as [KitKey, string][]).map(([key, label]) => (
                          <button key={key} type="button" role="tab" aria-selected={kit === key} onClick={() => setKit(key)}>{label}</button>
                        ))}
                      </div>
                      <div className="kit-content" role="tabpanel">
                        <span className="kit-index">READY KIT / {String(Object.keys(kitCopy).indexOf(kit) + 1).padStart(2, "0")}</span>
                        <h5>{kitCopy[kit].title}</h5>
                        <p>{kitCopy[kit].body}</p>
                        <a href={kitCopy[kit].href} target={kitCopy[kit].href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">{kitCopy[kit].action} <span aria-hidden="true">→</span></a>
                      </div>
                      <div className="source-box"><b>판정 근거</b><p>카카오뱅크 공식 안내 · 2026.01.22 확인</p><a href="https://blog.kakaobank.com/posts/service-limit-account" target="_blank" rel="noreferrer">원문 보기 ↗</a></div>
                    </div>
                  </div>

                  <div className="result-actions">
                    <button className="button secondary" type="button" onClick={resetDemo}>데모 처음부터</button>
                    <a className="button primary" href="/proofbridge-project-proposal.pdf" target="_blank">프로젝트 제안서 보기</a>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="section roadmap" id="roadmap">
          <div className="section-heading compact">
            <p className="eyebrow"><span />개발 순서</p>
            <h2>키를 많이 모으기보다,<br /><em>검증 한 번씩</em> 쌓습니다.</h2>
            <p>AI 모델은 전체 흐름과 정답 샘플이 준비된 뒤 하나만 비교합니다. 지금 만든 것은 그 실험을 끼워 넣을 자리입니다.</p>
          </div>

          <div className="roadmap-grid">
            <article className="roadmap-now">
              <span>NOW · 키 없음</span>
              <h3>흐름과 규칙의 뼈대</h3>
              <ul><li>합성 샘플 완주 화면</li><li>공공 경로·사문서·지참물 분리</li><li>공식 출처가 붙는 다섯 상태</li></ul>
            </article>
            <article>
              <span>NEXT · 한 개만 비교</span>
              <h3>문서 읽기 벤치마크</h3>
              <ul><li>PDF 내장 텍스트 우선</li><li>CLOVA OCR 합성 샘플 평가</li><li>낮은 신뢰도 사용자 확인</li></ul>
            </article>
            <article>
              <span>THEN · 필요한 연결</span>
              <h3>마지막 행동 연결</h3>
              <ul><li>FIN MAP 지점·접근성</li><li>Kakao Local 인쇄 장소</li><li>원본 보존 ZIP·즉시 삭제</li></ul>
            </article>
          </div>

          <div className="api-board">
            <div className="api-board-head"><div><span>API 준비표</span><h3>회원가입은 이 순서면 충분해요.</h3></div><a href="/api-onboarding.md" target="_blank" rel="noreferrer">상세 체크리스트 ↗</a></div>
            <div className="api-row"><b>공공 마이데이터</b><p>키 발급이 아니라 이용기관 신청·현장실사·심의</p><span className="badge approval">MVP 링크 안내</span></div>
            <div className="api-row"><b>FIN MAP</b><p>개발자 가입 후 서비스 신청, Client ID·Secret</p><span className="badge later">지점 기능 때</span></div>
            <div className="api-row"><b>Kakao Local</b><p>앱 생성 후 REST API 키, 인쇄소 검색에 사용</p><span className="badge later">지도 기능 때</span></div>
            <div className="api-row"><b>CLOVA OCR</b><p>도메인·Invoke URL·Secret Key, 합성 문서부터 비교</p><span className="badge next">첫 벤치마크</span></div>
            <div className="api-row"><b>LLM</b><p>쉬운 설명 품질을 평가할 때 하나만 선택</p><span className="badge skip">지금 불필요</span></div>
          </div>
        </section>

        <section className="closing">
          <p className="eyebrow light"><span />ProofBridge</p>
          <h2>문서를 많이 아는 AI가 아니라,<br />사람이 업무를 <em>끝내게 하는 AI</em>.</h2>
          <p>다음 회의에서는 이 데모를 기준으로 지원 은행 한 곳, 합성 샘플 한 묶음, 거짓 준비 완료율 0%라는 세 가지를 먼저 합의하면 됩니다.</p>
          <a className="button light-button" href="#demo">데모 다시 보기</a>
        </section>
      </main>

      <footer>
            <div className="brand"><span className="brand-mark" aria-hidden="true"><i /><i /></span><span>ProofBridge</span></div>
        <p>금융기관의 심사나 승인을 보장하지 않습니다. 현재 사이트는 합성 데이터만 사용하는 기획 데모입니다.</p>
        <div><a href="https://www.mydata.go.kr/" target="_blank" rel="noreferrer">공공 마이데이터</a><a href="https://daker.ai/public/hackathons/2026-finance-ai-challenge" target="_blank" rel="noreferrer">대회 공식 페이지</a></div>
      </footer>
    </div>
  );
}
