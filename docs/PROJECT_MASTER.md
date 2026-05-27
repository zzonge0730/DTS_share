# DTS 프로젝트 마스터 문서

## 1. 프로젝트 목표

**미션**: 수작업 교시(사람이 포인트를 찍는 방식) 대신, CAD + 비전 기반으로 용접 경로를 자동 생성/보정하고, 품질(Gap) 판정을 거친 뒤 로봇에 안전하게 전송하는 시스템을 완성한다.

| 구분 | Before | After |
|------|--------|-------|
| 경로 생성 | 사람이 포인트를 찍어서 교시 | CAD로 용접 트레이스(경로)를 미리 생성 |
| 품질 판별 | 없음 또는 별도 공정 | 카메라로 실제 제품 촬영 → CAD와 오차 판별 → 정상/불량 먼저 판별 |
| 실제 경로 | 교시한 포인트 그대로 사용 | 오차 보정 후 실제 용접 경로를 새로 생성해 로봇에 전달 |

### 핵심 가치 구분 (A vs B)

| 구분 | 설명 | 담당 | 비고 |
|------|------|------|------|
| **A. 경로 생성** (제품 핵심) | 용접선(seam) 정의/추출, 균일 리샘플링, 자세 생성, 실물 보정 | Python CAD/PCD 파이프라인 (`FINAL_PJT/`, `gab.py`) | 회사의 제품 경쟁력. 이것이 메인 |
| **B. 안전 실행** (실행 기반) | 통신(legacy 1100 UDP), 상태머신, StopLatch, Gap 판정, 전송 차단/허용 | DTS (C#) + Adapter | A를 현장에서 안전하게 돌리기 위한 기반. NACHI MZ07L 실로봇 경로는 Mech-Viz 경유로 전환 중 |

- 2월까지의 작업은 **B(안전 실행 기반)**을 확보한 것이다. 이 덕분에 A의 결과를 넣자마자 바로 안전하게 검증할 수 있는 하네스가 갖춰져 있다.
- **3월부터는 A(경로 생성)가 메인 개발 축**이 된다.

## 2. 시스템 구조

### 2.1 3개 레이어

| 레이어 | 기술 | 역할 |
|--------|------|------|
| **(A) Python 알고리즘 + Adapter** | Python | CAD/PCD 정합, ICP, Gap 측정, 경로 생성, 프로토콜 정규화(Mech → 1100), Quat→Euler 변환 |
| **(B) DTS (C# WinForms)** | C# .NET 4.8 | Vision TCP 수신 → Gap JSON 판정(OK/NG/STALE) → legacy Robot UDP 전송, 상태머신/StopLatch/안전 제어 |
| **(C) Robot / Mech-Viz** | JOB / Mech-Mind | 기존 mock/HS-180 경로: 1100 포즈 수신. NACHI MZ07L 경로: Mech-Viz IK/충돌검사 → 공식 Nachi adapter → MOVEX-J |

### 2.2 역할 분담

- **Python CAD/PCD 파이프라인** (A — 제품 핵심): seam 추출, 균일 리샘플링, 자세 생성, ICP 정합/Gap 측정, Rigid 보정
- **DTS (C#)** (B — 안전 실행): Vision TCP ↔ legacy Robot UDP 중계, 상태머신, StopLatch, Gap JSON 기반 전송 차단/허용. NACHI MZ07L에서는 `ROBOT_DELIVERY_MODE` 토글로 기존 UDP 직접 송신과 Mech-Viz 경유 모드를 분리
- **Adapter** (B): 외부 시스템 응답을 DTS 계약 포맷(`1100,<cnt>,x,y,z,rx,ry,rz,...`)으로 변환, Quat→Euler 변환
- **Mech-Mind 제품군** (외부, 단계적 대체 대상):
  - **Mech-Eye API**: 카메라 SDK — 3D 포인트클라우드/Depth 취득
  - **Mech-Vision**: 노코드 비전 파이프라인 — 물체 인식, 포즈 추정, (옵션) Path Planning Step
  - **Mech-Viz**: 모션 플래닝 — 충돌검출, 경로계획, 시뮬레이션

### 2.3 데이터 흐름

```
Legacy/mock 경로:
Robot READY → DTS → Adapter → Mech(101/102) → Adapter(정규화) → DTS(Gap 판정) → Robot(UDP 전송)

NACHI MZ07L 목표 경로:
DTS Python pose.csv → Workspace sanity gate → Mech-Viz(IK/충돌/Joint 변환) → Mech-Mind 공식 Nachi adapter → MZ07L(MOVEX-J)
```

상태코드는 별도 UDP 포트(기본 2002)로 전송:
- `2100,OK,...` : 전송 허용(정상)
- `2002,<reason>,...` : NG/차단(StopLatch)
- `1004,<reason>,...` : 결과 없음/입력 불가

## 3. 현재 상태 (2026-05-27 기준)

### 3.1 완료 항목

**안전 실행 기반 (B) — 2월 완료**
- Adapter 최소 구현 완료 (`READY → 101/102 → 1100` 변환)
- Quaternion→Euler 변환 (`quat_to_euler`, stride=7 자동 감지)
- Gap 실측 JSON 연동 (더미 제거), Mech 응답 이상 시 fail-safe
- ICP 품질 게이트 (`ICP_QUALITY_ENFORCE`, quality_gate_v2: BLOCK fitness<0.50, WARNING fitness<0.55). fitness는 파이프라인 설정 종속 상대 지표이므로 seam NN/RMSE/corridor와 함께 판단. 현재 임계값은 12-capture baseline 기반 운영 초기값이며 향후 재보정 대상
- C# fail-closed 강화 — Config 검증, StopLatch 가드, pose bounds ±5000mm
- C# 빌드 환경 복구 완료
- 범위 정정(2026-05): 위 통신 완료 범위는 **mock/legacy 1100 UDP 경로** 기준이다. 본사 NACHI MZ07L 실로봇 통신은 Mech-Viz 공식 Nachi adapter 경유로 전환 중이며, C# `ROBOT_DELIVERY_MODE` 토글과 Windows mock 검증은 완료했다. 실기 통신 검증은 본사 방문 일정 확정 후 진행한다.

**경로 자동 생성 파이프라인 (A) — 3월 완료**
- Battery-case seam 파이프라인 (`battery_seam_pipeline.py`): seam 정의 → surface snap → local normal → Euler ZYX pose → 1100 format
- Spot weld 파이프라인 (`spot_weld_pipeline.py`): STEP에서 344 circles → 232 unique → 82 ROI 내 spot 좌표 추출
- `transforms.py` 공유 모듈 — 4개 파일의 Euler/Quat 중복 제거
- Edge-snap 실험 파이프라인: curvature edge 검출 + snap + safety gates (`min_valid_ratio=0.8`)
- 시각화 도구: RGB overlay, 3D PCD overlay, ICP alignment, seam 비교 이미지

**Mech-Viz 시뮬레이션 — 3월 완료**
- U1/U2 seam (50+41 poses) Mech-Viz External Move로 HS-180 시뮬 검증 — 충돌 0, 오류 0
- `pose_to_viz.py`: Euler ZYX/mm → Mech-Viz quaternion/m 변환
- `viz_outer_move_service.py`: OuterMoveService gRPC adapter (1-pose-per-call loop)
- `mechviz_runtime.py`: WSL에서 Mech-Viz 서비스 시작/중지/프로젝트 열기/시뮬 트리거

**GUI 데모 — 3월 완료**
- `battery_case_gui.py`: 촬영→ICP 등록→경로 생성→보정 비교→DTS E2E→Mech-Viz export/시뮬 한 화면
- Mech-Eye SDK 연동: 카메라 촬영, organized PLY 저장 (overlay pixel mapping 보존)
- Canvas 기반 overlay 확대/축소/드래그, thread 완료 시 UI 상태 자동 복원
- DTS E2E 결과 파싱 (verdict, gap mode, log sections)

**Cross-validation — 3월 완료**
- 978 (HDR, historical `30°` label; re-measured later as ~`75°` class): U1 mean NN=0.599mm, U2 mean NN=0.697mm — **기준 캡처**
- 741 (Reflective): U1=1.072mm, U2=1.059mm
- 763 (historical `30°`-class clean capture): U1=1.070mm, U2=0.853mm
- 473 (90° raw): U1=5.804mm, U2=7.748mm — out-of-window
- 데이터 오염 검토 완료: capture-conditioned bias 문서화, MVP/데모용 수용 가능 판정

**정합 사전 차단 + 자동 진단 — 4월 완료**
- `alignment_precheck()`: ICP 전 4단계 early-exit 차단 (raw point count → ROI count/ratio → bbox sanity → seed-aware coarse overlap). 실패 캡처는 ICP를 건너뜀
- `diagnose_alignment()`: ICP 후 결과를 자동 분류 (GOOD / ACCEPTABLE / LOW_OVERLAP / SEED_UNSTABLE / CORRIDOR_FAIL / NN_WARNING / REFINEMENT_REJECTED). seam metrics 없는 경우 graceful handling
- Diagnosis spot-check: 45° fail → `precheck_failed` (ROI 849 < 5000), REG_R → `LOW_OVERLAP` + `NN_WARNING` (fitness 0.466), 978 → `GOOD` (fitness 0.570)
- Report JSON에 `status` / `precheck` / `diagnosis` 필드 추가, GUI에서 한 줄 원인 표시

**Capture Condition / Transfer Policy — 4월 반영**
- historical `30°` baseline은 실측 기준으로 약 `75°` class로 재정의
- `45°` 블록은 현재 setup에서 ICP fail / out-of-window로 기록
- `75° + HDR On + Ambient Off` 5회 반복촬영 결과:
  - ICP fitness mean `0.56223`, std `0.00023`
  - ICP RMSE mean `0.95458mm`, std `0.00096mm`
  - `U1 mean NN` mean `0.40052mm`, std `0.01242mm`
  - `U2 mean NN` mean `0.52340mm`, std `0.00774mm`
- REG 실험 결과:
  - 제품이 FOV 안에 완전히 들어오는 조건에서는 ±20mm translation, ±2° yaw 수준 변동에 대해 registration basin이 충분
  - partial FOV clipping 시 seam NN가 급격히 악화
- seam transfer 정책(현재):
  - `U1_right` → `no_snap`
  - `U2_left` → `constrained_k5`
  - `S4_right_step` → `no_snap` candidate
  - `S5_long_bottom_steps` → `no_snap`
  - `S3_complex_bottom` → overlay review 후 `review_needed`

**Batch 검증 — 4월 완료**
- 21개 캡처 일괄 진단: GOOD 17건, ACCEPTABLE 4건, BLOCK/FAIL 0건
- ACCEPTABLE 4건(361, 703, 806, codex)은 전부 refinement 도입 전후 과도기 샘플. 공통 코드: `NN_WARNING` + `REFINEMENT_REJECTED`. refinement가 시도되었지만 holdout 개선이 없어 미적용된 것이며, 캡처 자체의 품질 문제가 아님
- 21개 캡처는 3개 클러스터로 분류:
  - **A. NEW (refined)** 13건: 현재 운영 기준 파이프라인. seam-local refinement 적용, seam NN/RMSE 기준 가장 안정적
  - **B. NEW (rejected)** 5건: refinement 시도되었으나 holdout 개선 없어 미적용. 전역 정합은 성립하나 seam-local 품질은 A보다 불리
  - **C. OLD (no refinement)** 3건: 과거 파이프라인 결과. 현재 운영 기준과 직접 수치 비교 대상이 아니라 참고 이력으로 취급
- 클러스터 A와 B/C는 평가 창(max_corr)과 파이프라인 설정이 달라 fitness 값끼리 직접 비교 불가. 최종 품질은 seam NN/RMSE/corridor로 판단
- Report JSON에 `pipeline_metadata` 블록 추가 (quality_gate_version, icp_stages, seam_threshold_version) — 향후 baseline 변경 시 추적 가능

**NACHI MZ07L Mech-Viz 통합 — 5월 진행**
- Nachi 통합 방향 확정 — Mech-Viz / Mech-Mind 공식 adapter 경유 (MZ07L). 직접 1100 UDP 송신은 mock/legacy 경로로 한정
- MZ07L workspace sanity gate (`scripts/check_mz07l_workspace.py`), `T_robot_camera` transform 적용 경로 (mechviz_runtime 진입부에서 robot frame 변환)
- Mech-Viz GUI blocked-state 안정화 — gate fail 시 false progress 방지
- C# `ROBOT_DELIVERY_MODE` 토글 (`udp_1100` / `mechviz_nachi` / fail-closed), Windows 빌드 3-mode 동작 검증 완료
- 본사 현장 패키지 구성 — `NACHI_MZ07L_FIELD_PACK_20260520` (quickstart, pose 세트, adapter, config, log template)
- MZ07L 모델 실제 존재 확인 (2026-05-18) — MZ12 대체 가정 폐기, 실제 모델 기준으로 재정렬
- MZ07L 전용 robot base offset 분리 (대형 모델용 offset이 MZ07L에도 적용되던 문제 보완) — `4ebb297`
- Mech-Viz OuterMoveService 로그 자동 PASS/PARTIAL/FAIL 판정 도구 (`scripts/summarize_mechviz_dryrun_log.py`) — `d154c3b`
- 로컬 시뮬 dry-run 3개 부위 phase3_first5 PASS (2026-05-26) — `U1_right` / `U2_left` / `S5_long_bottom_steps` 각 5/5 pose 전달 OK. 현재 임시 +300mm X/Y 이격 셀 기준이며, 실 데모 셀(작업물 위치/지그/테이블/TCP/장애물) 정교화는 별도 항목으로 잔존
- 월간 보고서 `docs/SIM_REPORT_NACHI_2026-05.md` (+ `.docx`) 마감 — 본사 방문 일정 미확정 구간의 로컬 사전 검증 진행을 정리

### 3.2 검증 결과
- **Python 테스트**: 223 tests PASS (2026-05-27, `python3 -m pytest tests/`)
- **C# 빌드**: Build succeeded
- **E2E 9케이스**: OK/NG/NG_AVG/STALE/INVALID/ICP_LOW/ICP_HIGH/ICP_BAD/ICP_MISSING 전부 PASS
- **Mech-Viz 시뮬**: U1+U2 smooth motion, 충돌 0

### 3.3 남은 이슈
1. **생산 seam 정의 대기** — 운영 세트 `U1_right/U2_left/S5` 확정, S1/S2 deprecated. Drawing-confirmed production seam는 아직 미확인
2. **U2_left ~1.0mm 한계** — CAD seam 정의 문제 의심, CloudCompare 검증 필요
3. **로봇 확보 진행 (부분 해소)** — 본사 NACHI MZ07L로 검증 대상 확정 (2026-05, Hyundai HS-180 가정 폐기). Mech-Viz 라이브러리에 MZ07L 모델 실제 설치 확인 (2026-05-18). 로컬 시뮬 사전 검증은 시나리오 B로 진행 중 (`SIM_REPORT_NACHI_2026-05.md`). Hand-Eye Calibration과 현장 테스트는 본사 방문 일정 확정까지 보류
4. **Mech-Viz cell 정교화** — TCP, 토치 충돌 모델, 지그/테이블 장애물이 아직 임시
5. **measured centerline 부재** — 현재 `centerline/tangent`는 CAD nominal seam 기준 transfer metric이며, 실제 measured seam 중심선과의 비교는 아직 없음
6. **운영 Golden PCD / 설치 기준 확정 전** — 현재 ref PCD는 개발 기준이며, 현장 운영 기준(Golden PCD) 확정이 필요
7. **시뮬 셀 임시 설정** — 5/26 3-seam PASS는 작업물을 +300mm X/Y 이격한 임시 셀 기준. 실제 데모 셀(작업물 위치, 지그, 테이블, TCP, 장애물 모델)로 옮기는 작업 잔존
8. **본사 방문 일정 미확정** — 2026-05-19 방문 연기 이후 재확정 전. Hand-Eye Calibration·실로봇 통신 검증은 일정 확정 후 진행, 그동안은 로컬 사전 검증 보완

## 4. 전략 원칙

1. **Safety First** — Fail-dangerous 가능성이 있으면 기능 개발보다 우선 수정한다. 의도치 않은 더미/오염 데이터가 로봇에 들어갈 가능성을 원천 차단한다.
2. **MVP First** — 고급 기능(위빙, 고급 리샘플링, 실시간 트래킹)은 MVP 실장비 검증 이후 단계적으로 착수한다.
3. **Evidence First** — 모든 판정(OK/NG)은 로그/지표/테스트로 근거를 남긴다. Gap 수치뿐 아니라 ICP 정합 품질(신뢰도)을 함께 본다.
4. **Config First** — 하드코딩을 제거하고 App.config/CLI 기반으로 환경 전환 가능하게 유지한다.

## 5. 6개월 로드맵

### Phase 요약

| Phase | 시기 | 목표 | Go/No-Go 게이트 |
|-------|------|------|-----------------|
| **Phase 1**: MVP 확정 + 실환경 준비 | M1~M2 (3~4월) | Windows E2E 재현, Euler/ICP 기준 확정 | G1~G7 전항목 충족 |
| **Phase 2**: 실장비 검증 | M3 (5월) | 실 Mech-Vision 연결, 실장비 검증 | Mock 100회 파싱 실패 0, StopLatch 100%, 실장비 1회 검증 후 연속 30사이클 타임아웃 0 |
| **Phase 3**: 안정화 + 카메라 선정 + 파이프라인 확정 | M4 (6월) | 5회 반복 안정성, 카메라 A/B 최종 선정, 단일 파이프라인 확정 | RMS ≤ 0.5mm, 카메라 선정 문서, E2E 재현 |
| **Phase 4**: 인수인계 + 문서화 | M5 (7/1~7/24) | 운영 매뉴얼, 인수인계 패키지, 리허설 | 30분 내 재현 가능, 계약 종료일 7/24 준수 |

### 월별 상세

> **참고**: 2월에 이미 완료된 항목 — fail-safe(더미 전송 제거), StopLatch thread-safety, 상태 포트 분리, IP 외부화, Quat→Euler 변환, ICP 품질 게이트 옵션, pose 범위 가드

| 월 | 단계 | 핵심 목표 | 완료 기준 |
|---|---|---|---|
| M1 (3월) | Windows MVP 확정 + 재현성 확보 | GAP_JSON Windows/WSL 공용 경로 고정, Windows E2E 자동 실행, 안전 케이스 증적(PROTOCOL_UNKNOWN/POSE_OUT_OF_RANGE), 배포 가이드 | Windows E2E OK/NG/STALE 3/3 PASS, 안전 케이스 2개 증적, 배포 가이드 완성 |
| M2 (4월) | 실환경 준비 (자세/ICP 기준 확정) | ICP 임계값 quality_gate_v2 확정 (12-capture baseline), alignment precheck + diagnosis 자동화, batch 검증 | ICP 임계값 확정 ✅, precheck/diagnosis ✅, batch 검증 ✅ |
| M3 (5월) | NACHI 실장비 검증 Go/No-Go | Mech-Viz 경유 MZ07L dry-run 준비, ROBOT_DELIVERY_MODE 토글, full transform 구조, 현장 패키지 | 실로봇 1회 실행 성공(또는 현장 패키지 30분 내 재현) + Mech-Viz/Nachi 경로 통신 검증 + StopLatch 100% |
| M4 (6월) | 안정성 확인 + 카메라 선정 + 파이프라인 확정 | 5회 반복 RMS ≤ 0.5mm, 카메라 A/B 최종 선정, 단일 파이프라인 E2E 재현 | RMS ≤ 0.5mm, 카메라 선정 문서, E2E 통과 |
| M5 (7/1~7/24) | 인수인계 + 문서화 (**계약 종료 7/24**) | 운영 매뉴얼, 인수인계 패키지(`sample_bundle/`), 30분 재현 리허설 | 30분 내 재현 가능, 7/24 내 완료 |

### Go/No-Go 게이트 (4주 MVP 완성 판정)

| # | 항목 | Go 기준 |
|---|------|---------|
| G1 | Windows E2E OK/NG/STALE | 3/3 PASS |
| G2 | Form1.cs 하드코딩 IP | grep 결과 0줄 |
| G3 | GAP_JSON_PATH 경로 불일치 | E2E 중 경로 오류 0건 |
| G4 | Quat→Euler 변환 테스트 | 14개 PASS |
| G5 | StopLatch 안전 동작 | NG→무시→Reset→재정상 1회 PASS |
| G6 | Fallback fail-safe | Adapter fallback 시 로봇 전송 0회 |
| G7 | 전체 단위 테스트 | pytest exit code 0 |

## 6. 즉시 실행 계획 (3월, 4주)

> 2월에 이미 완료: fail-safe, StopLatch volatile, IP 외부화, Quat→Euler 변환, ICP 게이트, pose 범위 가드, 24 tests PASS

### Week 1~2: Windows MVP 재현성 확보
- GAP_JSON Windows/WSL 공용 경로 고정 + STALE 기준 검증
- Windows에서 E2E 자동 실행(scripts 기반) + 결과 자동 assertion
- 안전 케이스 2개를 `TEST_REPORT_E2E.md`에 증적 추가
  - `VISION_PROTOCOL_UNKNOWN` → 2002 + LATCHED
  - `POSE_OUT_OF_RANGE` → 2002 + LATCHED

### Week 3: 배포 가이드 + 버퍼
- 배포 가이드 1페이지 (필수 config 키 + 실행 순서 + 방화벽)
- 미해결 항목 수정 버퍼

### Week 4: Go/No-Go 판정
- Go/No-Go 게이트 전 항목 판정 실행
- 4월 실환경 준비 계획 확정

## 7. 기술 참조 문서

| 문서 | 역할 |
|------|------|
| [`MECH_VISION_INTEGRATION_SPEC.md`](MECH_VISION_INTEGRATION_SPEC.md) | Mech-Vision/Viz 연동 명세서 (인터페이스 계약, 시퀀스, 오류 정책, Go/No-Go 기준) |
| [`GAP_IO_CONTRACT.md`](GAP_IO_CONTRACT.md) | Gap JSON I/O 계약서 (입력 스키마, 판정 규칙, 상태코드 매핑) |
| [`TEST_REPORT_E2E.md`](TEST_REPORT_E2E.md) | E2E 테스트 증적 (OK/NG/STALE 케이스 결과) |

## 8. Mech-Vision/Viz 의존성 전략

### 8.1 Mech-Mind 제품별 역할 (정확한 구분)

| 제품 | 역할 | 우리 프로젝트 관련성 |
|------|------|---------------------|
| **Mech-Eye API** | 카메라 SDK — 3D 포인트클라우드/Depth/이미지 취득 | PCD 획득 소스. 자체 비전 전환 시 이 SDK를 직접 사용 |
| **Mech-Vision** | 노코드 비전 파이프라인 — 물체 인식, 포즈 추정, (옵션) Path Planning | 현재 101/102 명령으로 포즈 결과를 받는 주요 연동 대상 |
| **Mech-Viz** | 모션 플래닝 — 충돌검출, 경로계획, 시뮬레이션 | 201~205 명령. 현재 미사용, 확장용 |

**중요 구분**: Mech는 "seam(용접선) 자체를 생성"하는 게 아니라, 주어진 포즈/점열을 기반으로 **충돌 없는 로봇 모션 경로를 계획**하는 데 강점이 있다. **용접선 정의/추출은 우리 CAD 파이프라인의 핵심 역할**이며, 이것이 제품 경쟁력이다.

### 8.2 전략 방향: 자체 비전 파이프라인으로 대체

우리는 비전 카메라 판매 회사이므로, 경쟁사(Mech-Mind) 의존성을 줄이고 자체 구현으로 가는 것이 전략적으로 바람직하다.

**이미 보유한 부품:**
- `gab.py` — ICP 정합 (CAD vs 실물 포인트클라우드 정렬) → 변환행렬을 이미 계산
- `FINAL_PJT/` — CAD 기반 경로 생성 (Edge → Normal → Pose)
- `Adapter` — 프로토콜 변환 계층 (Mech를 다른 소스로 교체 가능한 구조)

**Mech를 대체하려면 필요한 3단계:**

| 단계 | 작업 | 자체 구현 난이도 |
|------|------|-----------------|
| 1 | 자사 카메라 SDK로 촬영 → 포인트클라우드(PCD) 취득 | 중 (SDK 연동) |
| 2 | ICP 정합으로 변환행렬(T) 추출 | **낮음** (`gab.py`에 이미 ICP 구현됨) |
| 3 | `FINAL_PJT` 경로에 T 적용 → 실물 좌표 경로로 보정 | **낮음** (행렬 곱 적용) |

### 8.3 실행 계획

- **Phase 1~2 (M1~M3)**: 현장의 Mech로 MVP 검증을 먼저 완료한다 (Adapter 계층 덕분에 DTS/Robot 수정 불필요)
- **Phase 3~4 (M4~M5)**: 자체 비전 파이프라인을 병행 개발하여 Mech를 대체한다
- **Adapter 구조**가 외부 시스템을 추상화하고 있으므로, 자체 비전으로 교체 시 DTS/Robot 쪽 코드 수정 없이 Adapter만 교체하면 된다

## 9. 의사결정 로그 (핵심)

| 결정 | 이유 |
|------|------|
| **Mech-Vision 의존성 단계적 제거** | 경쟁사 의존성 축소 전략. ICP/경로 생성은 이미 자체 구현 보유. MVP는 Mech로 검증 후 자체 비전으로 교체 |
| **Seam Tracking → M5 이후 연기** | 8인주 H리스크, 기존 READY→1100→FINISH 배치 계약 변경 필요, 실장비 통신 지연 확인 전 착수 불가 |
| **Non-Rigid 정합 → M4 이후 연기** | 처리시간 >3초 시 현장 사이클 내 처리 불가, ICP 기반 안정화 선행 필요 |
| **Viz 자동 선택 → M5 배치** | DTS→Adapter 모드 전환 채널 신규 개발 필요, MVP 계약 구조 변경 수반 |
| **Fallback → fail-safe 즉시 수정** | Unknown Mech 응답 시 더미 좌표 전송은 안전 사고 위험. 타협 없음 |
| **StopLatch volatile 즉시 수정** | 멀티스레드 race condition 가능성, 안전 정책의 핵심 기제이므로 타협 없음 |
| **아키텍처 전면 재설계 보류** | E2E 3케이스 통과로 현재 아키텍처 동작 확인됨. 재설계는 M4 이후 장기 과제로 검토 |
| **기준 좌표계: 로봇 좌표계 + Euler 6필드 고정** | DTS 입력 포맷 통일, quaternion은 내부 계산/보관에서만 허용 |
