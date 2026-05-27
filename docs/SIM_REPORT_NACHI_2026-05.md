# NACHI MZ07L Mech-Viz 사전 검증 결과 보고서 (2026-05)

> 작성일: 2026-05-22 (5/26 §5.2 최종 갱신)
> 작성자: 강우혁
> 상태: **시나리오 B 완료 — 로컬 시뮬레이션 기준 3개 부위 first5 사전 실행 PASS**
> 범위: 본사 NACHI MZ07L 실로봇 검증 전 단계의 로컬 시뮬레이션 사전 검증 1주차 결과
> 관련 일자별 dev log: [`SIM_REPORT_NACHI_2026-05-18.md`](SIM_REPORT_NACHI_2026-05-18.md)

---

## 1. 요약

5/18~5/22 진행분에 5/26 재검증 결과를 반영한, NACHI MZ07L 실로봇 연동을 위한 시뮬레이션 사전 검증 1주차 결과 보고. 핵심 결과는 다음과 같다.

- **모델 가용성 발견 — 진행 방향 변경**: 기존 가정과 달리 시뮬레이션 도구 라이브러리에 현장 모델(MZ07L)이 실제 설치되어 있음을 확인. 동일 시리즈 대체 모델(MZ12) 경유 계획을 폐기하고 실제 모델 기준으로 검증 재정렬.
- **도달 불가 원인 식별·해소**: 초기 사전 실행에서 발생한 도달 불가 오류 원인이 기존 대형 모델 기준 로봇 기준점 보정값이 그대로 적용된 데 있음을 확인. 모델별 보정값 분리 적용으로 해소.
- **자동 판정 도구 도입**: 사전 실행 로그를 정상·부분 완료·실패로 자동 판정하는 도구 추가. 사람에 의한 수동 로그 검토 없이 결과 분류 가능.
- **현재 상태**: MZ07L 기준 셀/pose 위치를 로봇 원점에서 이격하도록 보정한 뒤, U1/U2/S5 3개 부위 first5 경로가 모두 사전 실행 PASS(각 5/5 전달)됨. 기존 실패 원인은 self-loop나 서비스 등록 문제가 아니라, seam pose가 로봇 원점 근처에 배치되어 발생한 툴-로봇 충돌 문제였음.

본사 방문 일정 미정 상태에서도 로컬 환경에서 완결 가능한 검증 절차를 정리해 후속 작업의 재현성을 확보했다.

---

## 2. 목적 / 범위

### 목적
본사 NACHI MZ07L 실로봇에 실제로 경로를 전달하기 전, 로컬 환경에서 시뮬레이션 도구를 통해 다음 항목을 사전 확인한다.

- 카메라-로봇 좌표 변환 후 로봇 좌표계 경로의 작업 공간 적합성
- 시뮬레이션 도구가 제공하는 역기구학 계산(IK, 로봇 관절 각도 역산), 충돌 검사, 도달성 판정 결과
- 시뮬레이션 도구와 자체 코드(Python 어댑터, C# DTS) 간 통신 흐름의 정상 동작
- 본사 방문 시 즉시 실행 가능한 형태로 검증 절차 및 자료 정비

### 범위
- 검증 대상: NACHI MZ07L 모델, MZ07L 라이브러리(`nachi_mz07l_01`) 기반 시뮬레이션 도구 환경
- 입력 데이터: 사전 실행 전용 로봇 좌표계 기준 축소 경로 (5개 지점) — 실로봇 송신 금지
- 제외 사항: 실로봇 통신, 카메라-로봇 좌표 보정 측정(Hand-Eye Calibration) 적용, 현장 안전 절차 검증

### 적용 한계
- 현재 `T_robot_camera`는 임시 변환(z 축 -900mm)만 적용. 본사 현장에서 실측 후 교체 필요.
- 시뮬레이션 결과는 역기구학·충돌·통신 흐름 사전 점검 목적에 한정. 실로봇 동작 100% 보장이 아님.

---

## 3. 환경 / 전제 조건

### 시뮬레이션 도구
- Mech-Mind Mech-Viz (2.1.2)
- 로봇 라이브러리: `%APPDATA%\Mmind\Robot Library 2.0\nachi\nachi_mz07l_01\` (실제 설치 확인)

### 작업 위치
- 메인 작업 위치(WSL): `/home/hanmech/DTS/`
- 공유/검토용 복사본(WSL): `/home/hanmech/DTS_share/` (필요 시 동기화)
- 시뮬레이션 도구 프로젝트: `C:\Users\hanmech\Desktop\DTS_image\Mech-Viz-dCNwPT\`
- 원본 프로젝트 폴더는 별도 보존 (수정 금지)
- 시뮬레이션 도구 프로젝트는 폴더명과 `.viz` 파일명에 민감하므로 임의 변경 금지

### 입력 데이터
- 사전 실행 전용 로봇 좌표계 경로:
  - `data/battery_case/field_test/mechviz_dryrun_robot_frame/U1_right_phase3_first5_sim_robot_frame_pose.csv`
  - `data/battery_case/field_test/mechviz_dryrun_robot_frame/U2_left_phase3_first5_sim_robot_frame_pose.csv`
  - `data/battery_case/field_test/mechviz_dryrun_robot_frame/S5_long_bottom_steps_phase3_first5_sim_robot_frame_pose.csv`
- 원본(카메라 좌표계): `data/battery_case/field_test/phase3_poses/*_phase3_first5_pose.csv`
- 변환 방식: `(x, y, z) → (x + 300mm, y + 300mm, z − 900mm)`, 자세값 유지

### 실행 설정
- Runtime config: `data/battery_case/mechviz_runtime_config_nachi_mz07l_dryrun.json`
- 핵심 설정: `robot_base_m = [0.0, 0.0, 0.0]` (MZ07L 전용 보정값)

### C# DTS 측 설정
- `ROBOT_DELIVERY_MODE = mechviz_nachi` (실로봇 직접 송신 차단)
- 차단 검증 방법: 모의 로봇 수신측에서 1100 UDP 패킷 수신 0건 확인 + DTS 콘솔 송신 차단 사유 로그(`[SendGuard] Blocked`) 확인 (이중 증명)

---

## 4. 검증 방법론

### Phase 정의
| 단계 | 내용 | 본 보고 적용 |
|---|---|---|
| Phase 0 | 환경 구성 (작업본 오픈, 모델 적용, 입력 데이터 준비) | 포함 |
| Phase 1 | 통신 흐름 검증 (서비스 등록, 통신 허브 트리거, 경로 외부 전달 단계 진입) | 포함 |
| Phase 2 | 사전 실행 (사전 검사 → 역기구학 → 충돌 → 순차 전달) | 포함 |
| Phase 3 | 실로봇 수동 도달 확인 | 미포함 (현장 의존) |
| Phase 4 | 실로봇 저속 자동 실행 | 미포함 (현장 의존) |

### 사전 실행 데이터 생성
- 원본 phase3 first5 경로(카메라 좌표계) 활용
- 임시 변환(z−900mm) 및 MZ07L 작업영역 이격(+300mm X/Y)으로 로봇 좌표계 근사 — 실측 `T_robot_camera` 적용 전까지 사용

### 판정 기준
- **Workspace sanity** (`scripts/check_mz07l_workspace.py`): 좌표 형식, 작업 공간, 도달 범위(912 mm, MZ07LM 카탈로그 `MMZEN-327-001` 기준), 인접 지점 간 변동량
- **사전 실행 결과 판정** (`scripts/summarize_mechviz_dryrun_log.py`):
  - 정상(PASS): 전체 지점 전달 완료
  - 부분 완료(PARTIAL): 일부 지점만 전달
  - 실패(FAIL): 전달 미진행 또는 로딩 정보 부재

---

## 5. 검증 결과

### 5.1 Workspace sanity

| 입력 파일 | 지점 수 | 도달 거리 범위 | 결과 |
|---|---:|---:|---|
| `U1_right_phase3_first5_sim_robot_frame_pose.csv` | 5 | 522.8~533.8 mm | PASS |
| `U2_left_phase3_first5_sim_robot_frame_pose.csv` | 5 | 471.5~496.3 mm | PASS |
| `S5_long_bottom_steps_phase3_first5_sim_robot_frame_pose.csv` | 5 | 373.8~385.4 mm | PASS |

전 부위에 대해 사전 검사 통과.

### 5.2 사전 실행 결과

> **self-loop**: 시뮬레이션 도구 프로젝트 내부에서 경로 외부 전달 단계(도구 내 명칭: External Move step)가 다음 지점 요청을 다시 받기 위해 자기 자신으로 분기되는 단계 연결 구성. 누락 시 첫 지점만 전달되고 멈춤.

5/26 최종 재실행 결과 — **3개 부위 모두 first5 사전 실행 PASS**.

| 부위 | 상태 | 전달 지점 | 비고 |
|---|---|---:|---|
| `U1_right` | PASS | 5/5 | MZ07L 작업영역 이격 후 전체 지점 전달 |
| `U2_left` | PASS | 5/5 | 동일 조건에서 전체 지점 전달 |
| `S5_long_bottom_steps` | PASS | 5/5 | 동일 조건에서 전체 지점 전달 |

자동 판정 결과:

```text
U1_right: mechviz_dryrun=PASS delivered=5/5 reason=all_poses_delivered
U2_left: mechviz_dryrun=PASS delivered=5/5 reason=all_poses_delivered
S5_long_bottom_steps: mechviz_dryrun=PASS delivered=5/5 reason=all_poses_delivered
```

#### 확인된 정상 동작
- 서비스 등록 및 통신 허브 등록 (`Registered 'DTS Weld Seam Outer Move' with hub at 127.0.0.1:5308`)
- 시뮬레이션 도구 프로젝트 열기
- 경로 외부 전달 단계 진입
- self-loop 연결 구성 정상 확인
- 경로 전달 함수(`getMoveTargets`)가 각 부위별로 5개 지점을 모두 순차 반환
- 마지막 추가 호출에서 `all 5 poses delivered` 및 `Returning 0 targets` 확인

#### 실패 원인 정정 및 해소

본 주 사전 실행은 시점별로 두 차례 실패를 거쳤다.

| 차수 | 시점 | 증상 | 1차 가설 | 정정된 원인 / 조치 |
|---|---|---|---|---|
| 1차 | 5/18~5/19 | 도달 불가(`unreachable`) | 모델 좌표 부적합 | 기존 대형 모델 기준 로봇 기준점 보정값이 MZ07L에 그대로 적용. 모델별 보정값 분리(§5.3)로 해소 |
| 2차 | 5/24~5/25 | 부분 완료(PARTIAL 1/5) | self-loop 누락 또는 자세 기반 역기구학 실패 | 5/26 재검토 결과 self-loop는 정상. seam pose가 로봇 원점 근처에 배치되어 충돌 — 작업영역 이격으로 해소 |

5/26 재검토 결과 2차 정정 사항:

1. **self-loop 연결은 정상**
   - 경로 외부 전달 단계가 자기 자신으로 다시 연결되어 있음을 GUI에서 확인
   - 첫 지점 이후 다음 지점 요청이 정상 발생함

2. **seam pose가 로봇 원점 근처에 배치되어 툴-로봇 충돌 발생**
   - 기존 U1 첫 지점은 MZ07L 원점 기준 약 315 mm 위치에 있어, 토치 모델(`torch_thin`)과 로봇 위팔 간 충돌 발생
   - 이는 오프셋 단독 문제가 아니라, 기존 HS-180 기준 셀에서 가져온 pose를 MZ07L 원점 근처에 그대로 둔 배치 문제

3. **MZ07L 작업영역 기준으로 pose와 작업물을 함께 이격 후 해소**
   - U1/U2/S5 사전 실행 pose를 +300 mm X/Y 방향으로 이동
   - 시뮬레이션 도구의 `battery_case` 모델도 동일 방향으로 이동
   - 이격 후 3개 부위 모두 first5 사전 실행 PASS

#### 결론
- **시나리오 B 로컬 재현 검증 완료** — 현장 의존 없이 현재 코드·설정·시뮬레이션 프로젝트만으로 3개 부위 first5 사전 실행 재현
- 실로봇 검증은 제외 상태이며, 본 결과는 로컬 시뮬레이션 기준의 경로 전달·역기구학·충돌 검사 사전 검증 결과
- 향후 본사 방문 또는 실제 셀 구축 시에는 실측 `T_robot_camera`, 툴 중심점(TCP), 실제 지그/작업물 위치를 적용해 재검증 필요

### 5.3 로봇 기준점 보정값 보완 사례 (5/18~5/19 1차 실패 정정)

5/18~5/19 1차 사전 실행에서 도달 불가 오류 발생.

```text
Waypoint: (1.27194, -0.471724, 0.312822) → unreachable
```

분석:
- 시뮬레이션 도구 측 `viz_outer_move_service.py` 기본값이 기존 대형 모델 프로젝트 가정(`robot_base = (1.3, -0.5, 0.0)`)으로 설정됨
- MZ07L 사전 실행에서도 동일 보정값이 적용되어 첫 지점이 로봇 기준점에서 약 1.39 m 위치로 이동
- MZ07L 도달 거리(912 mm)를 초과하므로 도달 불가 판정이 정상

조치:
- `scripts/mechviz_runtime.py`에 runtime config 기반 `robot_base_m` 설정 추가
- MZ07L 사전 실행용 config: `robot_base_m = [0.0, 0.0, 0.0]`

결과:
- 도달 불가 원인 해소 확인 — 위 좌표는 보정값 분리 적용 *전* 기준이며, 분리 후 부록 B의 좌표(0.27, 0.34, 0.31)처럼 MZ07L 작업영역 내 좌표로 정정됨
- 보정값 분리 적용 구조 확보 — 다른 모델 추가 시 동일 방식으로 확장 가능

### 5.4 자동 판정 도구 도입 효과

도입 전:
- 사전 실행 로그를 사람이 직접 읽고 `[gather_targets]` 호출 수를 수동으로 카운트
- 결과를 보고서·일일업무일지에 옮길 때마다 재현 부정확

도입 후:
- `scripts/summarize_mechviz_dryrun_log.py`로 단일 명령 판정
- 출력: `PASS / PARTIAL / FAIL`, 전달 지점 수, 마지막 호출 회차, 입력 경로 파일
- 단위 테스트 6건 통과로 동작 보증
- 현장 빠른 실행 가이드 및 패키지 문서에 사용 절차 반영 완료

---

## 6. 남은 이슈 / 미해결 항목

### 시뮬레이션 흐름 — 5/26 최종 진단 결과
- self-loop 연결 구성: **정상 (확인 완료)** — 초기 추정 원인 폐기
- 툴-로봇 충돌: **해소 완료** — seam pose가 로봇 원점 근처에 있던 배치 문제로 확인, MZ07L 작업영역 이격 후 해결
- 3개 부위 first5 사전 실행: **PASS 3/3**

### 후속 점검·해소 절차
1. **실제 셀 기준 좌표 재정의** (세부 항목은 §6.1)
2. **카메라-로봇 좌표 보정 측정(Hand-Eye Calibration) 적용**
   - 본사 방문 시 실측 → `T_robot_camera` 입력 → 자세 데이터 변환 재생성
3. **변환 후 사전 실행 재검증**
   - 동일 입력 경로(테스트용 부위 한 곳, 다른 부위 포함)로 다시 시뮬레이션 도구 사전 실행
   - 자동 판정 도구로 전체 지점 전달 확인

### 6.1 시뮬레이션 셀 정교화 항목

현재 5/26 PASS 상태는 작업물과 pose를 임시로 +300 mm X/Y 이격한 상태이며, 실제 데모 셀 기준으로 옮기려면 다음 항목들의 실측·정의가 필요하다. 우선순위는 본사 방문 시점에 즉시 측정 가능 여부 기준.

| 항목 | 현재 (5/26 임시 셀) | 정교화 작업 | 측정/입력 출처 | 우선순위 |
|---|---|---|---|---|
| 작업물(`battery_case`) 위치 | 시뮬레이션 도구 안에서 +300 mm X/Y 이격 | 실 데모 셀에서 작업물 mount 위치 측정 후 시뮬에 동일 좌표로 배치 | 본사 셀 도면 또는 실측 (작업 좌표계 원점 ↔ 작업물 기준점) | 높음 (Hand-Eye Calibration 직전 필요) |
| 지그(jig) 모델 | 미포함 | 작업물 고정 지그 형상을 단순 박스/메시로 충돌체 추가 | 본사 지그 도면 또는 사진 + 캘리퍼 실측 | 중간 (충돌 검사 정확도) |
| 작업 테이블 | 미포함 | 테이블 상판 평면 + 높이를 충돌체로 추가, 작업물 기준 평면 정의 | 본사 셀 실측 (높이/폭/길이) | 중간 |
| TCP(`torch_thin` 끝점) | 시뮬레이션 도구 기본 `torch_thin` 모델, TCP 오프셋 미정밀화 | 실 토치 모델 등록(또는 `torch_thin` 치수 보정) + TCP 등록값 실측 후 입력 | 본사 토치 spec + 티치펜던트 등록값 | 높음 (도달성/충돌 모두 영향) |
| 주변 장애물(차폐벽/와이어 송급기 등) | 미포함 | 셀 내 주요 정적 장애물을 단순 충돌체로 추가 | 본사 셀 사진 + 실측 | 낮음 (1차 dry-run 영향 작음) |
| 사용자 좌표계(workobject) | 로봇 기준점과 작업물이 동일 좌표계 | 작업 좌표계를 별도 정의해 pose 변환 일관성 확보 | 본사 셀 정의 합의 | 중간 |

> 적용 순서 권고: 작업물 위치 → TCP → 지그/테이블 → 사용자 좌표계 → 주변 장애물. 작업물 위치와 TCP가 잡히면 §D-2 절차로 다시 사전 실행해 PASS 확인 가능. 지그/테이블은 충돌 검사 정밀도를 위해, 주변 장애물은 안정성 단계에서 추가.

### 현장 측정 필요 항목 (본사 방문 시 처리)
- 카메라-로봇 좌표 변환 행렬(`T_robot_camera`) 실측 — 현재 임시 변환 적용 중
- 로봇 컨트롤러 IP, PC 할당 IP
- 툴 중심점(TCP) 등록값, 사용자 좌표계 정의
- 안전 속도 합의값, 비상 정지 절차, 용접 토치 차단 절차

### 일정 종속 항목
- 본사 방문 가능 시점 (회사 결정 대기)

---

## 7. M3 시나리오 판정

| 시나리오 | 조건 | 본 시점 상태 |
|---|---|---|
| A — 실로봇 검증 | 본사 방문 일정 확정 + 현장 측정 항목 회신 수령 | 일정 미정, 진입 불가 |
| B — 로컬 재현 검증 | 현장 의존 없이 현재 패키지·코드·시뮬레이션 환경만으로 사전 검증 절차 재현 가능 | **완료** — 3개 부위 first5 사전 실행 PASS |

**본 시점 판단**: 시나리오 A 진입 조건 미충족 상태가 지속되어 시나리오 B로 진행했고, 본 보고서 시점에 로컬 시뮬레이션 기준 3개 부위 first5 사전 실행을 모두 통과했다. 실로봇 검증은 제외하며, 실제 셀 기준 재검증은 본사 방문 또는 실제 데모 셀 구성 이후 별도 단계로 진행한다.

---

## 8. 후속 계획

### 즉각 (5/22~5/29)
- 로컬 재현 기준 검증 절차 보존 — 3개 부위 first5 PASS 결과와 실행 순서 유지
- 시뮬레이션 셀 구성 보완 범위 검토 — 지그, 작업 테이블, 주변 장애물 모델 추가 범위 정리
- 정합 한계 부위 CAD 기준선 재검토 착수

### 중기 (6월, M4 진입 준비)
- 시뮬레이션 환경 정교화 — 셀 구성(지그, 작업 테이블, 주변 장애물), 툴 중심점(TCP) 오프셋 정밀화
- 반복 측정 환경 구성 — 정합 결과 안정성 검증을 위한 5회 반복 측정 절차
- 정합 한계 부위 CAD 기준선 재정의 — 자세 오차가 한계 수준에 근접한 부위 원인 규명

### 본사 방문 일정 확정 시
- 카메라-로봇 좌표 보정 측정(Hand-Eye Calibration) 후 `T_robot_camera` 적용
- Phase 3 수동 도달 확인 (수동 이동 검증용 경로 사용)
- Phase 4 저속 자동 실행 (사전 실행 결과 동일 부위, first5 경로)
- 전체 경로 1회 실행은 수동·저속 자동 검증 완료 후 별도 합의 단계로 진행

---

## 부록 A — 자동 판정 도구 사용법

```bash
# 텍스트 출력
python3 scripts/summarize_mechviz_dryrun_log.py \
  --log <서비스 로그 경로>

# JSON 출력
python3 scripts/summarize_mechviz_dryrun_log.py \
  --log <서비스 로그 경로> \
  --format json
```

출력 예 (PARTIAL):
```text
mechviz_dryrun=PARTIAL delivered=1/5 reason=delivered_1_of_5
last_call=1
delivered_pose_indices=1
source_pose_csv=C:\Users\hanmech\AppData\Local\Temp\dts_robot_frame_pose_*.csv
```

종료 코드:
- 0: PASS
- 1: PARTIAL / FAIL

## 부록 B — 주요 로그 샘플

서비스 정상 등록 및 5개 지점 전체 전달 (파일명의 `*`는 실행 시 자동 생성되는 UUID 부분):

```text
Loaded 5 poses from C:\Users\hanmech\AppData\Local\Temp\dts_robot_frame_pose_*.csv
first: world (0.2716, 0.3380, 0.3113)  qw=0.0655
last:  world (0.2872, 0.3095, 0.3159)  qw=0.0853
Registered 'DTS Weld Seam Outer Move' with hub at 127.0.0.1:5308
Ready. Run Mech-Viz simulation — poses will be served at External Move step.
getMoveTargets: di=0
[gather_targets] call #1, pose 1/5: x=0.2716 y=0.3380 z=0.3113
Returning 1 targets
...
[gather_targets] call #5, pose 5/5: x=0.2872 y=0.3095 z=0.3159
Returning 1 targets
[gather_targets] all 5 poses delivered. Returning 0 targets to finish.
```

## 부록 C — 참고 명령

워크스페이스 사전 검사:
```bash
python3 scripts/check_mz07l_workspace.py \
  --input <pose csv> \
  --max-poses 5
```

사전 실행 데이터 생성:
```bash
python3 scripts/extract_phase3_poses.py \
  --input output/rehearsal_978/<seam>_pose.csv \
  --output data/battery_case/field_test/phase3_poses/<seam>_phase3_first5_pose.csv \
  --count 5 \
  --strategy first \
  --summary-json data/battery_case/field_test/phase3_poses/<seam>_phase3_first5_summary.json
```

수동 도달 검증용 후보 지점 추출:
```bash
python3 scripts/extract_phase3_poses.py \
  --input output/rehearsal_978/<seam>_pose.csv \
  --output data/battery_case/field_test/phase3_poses/<seam>_phase2_jog5_pose.csv \
  --count 5 \
  --strategy jog
```

## 부록 D — 로컬 사전 실행 재현 체크리스트

> 5/26 PASS 상태(3개 부위 first5 사전 실행)를 로컬에서 재현하는 최단 절차.
> 실로봇 미접속, 시뮬레이션 도구 단독 동작 전제.

### D-1. 사전 준비 (1회)

- [ ] Windows에서 시뮬레이션 도구 작업본 폴더 확인 — `C:\Users\hanmech\Desktop\DTS_image\Mech-Viz-dCNwPT\` (폴더명/`.viz` 파일명 변경 금지)
- [ ] DTS `appsettings.json` 또는 환경변수에서 `ROBOT_DELIVERY_MODE = mechviz_nachi` 확인 — `udp_1100` 상태라면 변경 후 DTS 재시작
- [ ] runtime config 경로 확인 — `data/battery_case/mechviz_runtime_config_nachi_mz07l_dryrun.json`, `robot_base_m = [0.0, 0.0, 0.0]`

### D-2. 부위별 실행 루프 (U1_right → U2_left → S5_long_bottom_steps 각 1회)

1. **워크스페이스 사전 검사** — 부록 C `check_mz07l_workspace.py` 실행, PASS 확인
   - 예상 결과: 도달 거리 범위가 §5.1 표 값 (U1=522.8~533.8, U2=471.5~496.3, S5=373.8~385.4 mm)에 일치
2. **시뮬레이션 도구 작업본 열기** — `Mech-Viz-dCNwPT.viz` 더블클릭
3. **외부 서비스 시작** — Windows PowerShell에서 `scripts/start_mechviz_service.ps1` 호출. 예시 (U1_right 기준):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start_mechviz_service.ps1 `
     -PythonExe C:\Python311\python.exe `
     -ServiceScript scripts\viz_outer_move_service.py `
     -CsvPath data\battery_case\field_test\mechviz_dryrun_robot_frame\U1_right_phase3_first5_sim_robot_frame_pose.csv `
     -ServiceName "DTS Weld Seam Outer Move" `
     -MotionType lin -Velocity 0.05 -Acceleration 0.05 -BlendRadius 0.0
   ```
   다른 부위는 `-CsvPath`만 `U2_left_*` / `S5_long_bottom_steps_*`로 교체
4. **시뮬 트리거** — 시뮬레이션 도구 GUI에서 `Simulate` 실행. External Move 단계 진입 확인 (로그에 `Registered '...' with hub at 127.0.0.1:5308`)
5. **로그 자동 판정** — 부록 A 명령으로 서비스 stdout 로그 분석. 기대값:
   ```text
   mechviz_dryrun=PASS delivered=5/5 reason=all_poses_delivered
   ```
6. **종료 코드 0 확인** — `echo $LASTEXITCODE` (PowerShell) 또는 `echo $?` (bash)

### D-3. 막힐 때 분기 표

| 증상 | 1차 확인 | 참조 |
|---|---|---|
| 워크스페이스 사전 검사 FAIL | 입력 csv가 robot frame인지(`*_sim_robot_frame_pose.csv`) 확인 | §3 입력 데이터 |
| 외부 서비스 등록 로그 없음 | 시뮬레이션 도구 통신 허브 포트(5308) 사용 중 프로세스 확인 | §5.2 확인된 정상 동작 |
| 1점만 전달되고 멈춤(`PARTIAL 1/5`) | 시뮬레이션 도구 GUI에서 External Move 단계 self-loop 연결 확인 (5/26 시점에는 정상이었음) | §5.2 self-loop 정의 |
| `unreachable` 오류 | runtime config `robot_base_m` 값 확인. MZ07L은 `[0.0, 0.0, 0.0]` | §5.3 |
| 도달은 되지만 충돌 발생 | 입력 pose가 로봇 원점 근처(<400 mm)인지 확인. 작업물·pose 동시 이격 필요 | §5.2 #2~#3 |
