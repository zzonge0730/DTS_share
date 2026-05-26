# NACHI MZ07L Mech-Viz 사전 검증 결과 보고서 (2026-05)

> 작성일: 2026-05-22 (5/26 §5.2 갱신)
> 작성자: 강우혁
> 상태: **시나리오 B 완료 게이트 충족 — 통신·등록·구조 검증 완료. 역기구학·도달성 정밀 검증은 본사 측정값 적용 후 별도 단계**
> 범위: 본사 NACHI MZ07L 실로봇 검증 전 단계의 로컬 시뮬레이션 사전 검증 1주차 결과
> 관련 일자별 dev log: [`SIM_REPORT_NACHI_2026-05-18.md`](SIM_REPORT_NACHI_2026-05-18.md)

---

## 1. 요약

본 주(5/18~5/22) NACHI MZ07L 실로봇 연동을 위한 시뮬레이션 사전 검증을 진행했다. 핵심 결과는 다음과 같다.

- **모델 가용성 발견 — 진행 방향 변경**: 기존 가정과 달리 시뮬레이션 도구 라이브러리에 현장 모델(MZ07L)이 실제 설치되어 있음을 확인. 동일 시리즈 대체 모델(MZ12) 경유 계획을 폐기하고 실제 모델 기준으로 검증 재정렬.
- **도달 불가 원인 식별·해소**: 초기 사전 실행에서 발생한 도달 불가 오류 원인이 기존 대형 모델 기준 로봇 기준점 보정값이 그대로 적용된 데 있음을 확인. 모델별 보정값 분리 적용으로 해소.
- **자동 판정 도구 도입**: 사전 실행 로그를 정상·부분 완료·실패로 자동 판정하는 도구 추가. 사람에 의한 수동 로그 검토 없이 결과 분류 가능.
- **현재 상태**: 사전 실행 흐름의 서비스 등록·프로젝트 열기·경로 외부 전달 단계 진입·첫 지점 전달까지 정상 동작 확인. 첫 지점에서 역기구학 계획 실패로 흐름 종료 — 원인은 셀 구성·자세 데이터가 기존 로봇 기반에 묶여 있는 데 있으며, 본사 측정값 적용 후 셀 정교화 단계에서 해소 예정.

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
- 변환 방식: `(x, y, z) → (x, y, z − 900mm)`, 자세값 유지

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
- 임시 변환(z−900mm)으로 로봇 좌표계 근사 — 실측 `T_robot_camera` 적용 전까지 사용

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
| `U1_right_phase3_first5_sim_robot_frame_pose.csv` | 5 | 314.9~316.6 mm | PASS |
| `U2_left_phase3_first5_sim_robot_frame_pose.csv` | 5 | 332.4~337.2 mm | PASS |
| `S5_long_bottom_steps_phase3_first5_sim_robot_frame_pose.csv` | 5 | 432.0~450.8 mm | PASS |

전 부위에 대해 사전 검사 통과.

### 5.2 사전 실행 결과

> **self-loop**: 시뮬레이션 도구 프로젝트 내부에서 경로 외부 전달 단계(도구 내 명칭: External Move step)가 다음 지점 요청을 다시 받기 위해 자기 자신으로 분기되는 단계 연결 구성. 누락 시 첫 지점만 전달되고 멈춤.

5/26 재실행 결과 — 통신 흐름은 정상 동작하나, **첫 지점에서 역기구학(IK) 계획 실패로 사전 실행 흐름 종료**.

| 부위 | 상태 | 전달 지점 | 비고 |
|---|---|---:|---|
| 테스트용 부위 한 곳 (U1) | 부분 완료(PARTIAL) | 1/5 | 첫 지점 plan-fail로 흐름 종료 |
| 다른 부위 (U2) | 미진행 | - | U1 흐름 안정화 이후 진행 |
| 다른 부위 (S5) | 미진행 | - | U1 흐름 안정화 이후 진행 |

자동 판정 결과:

```text
mechviz_dryrun=PARTIAL delivered=1/5 reason=delivered_1_of_5
```

#### 확인된 정상 동작
- 서비스 등록 및 통신 허브 등록 (`Registered 'DTS Weld Seam Outer Move' with hub at 127.0.0.1:5308`)
- 시뮬레이션 도구 프로젝트 열기 명령
- 경로 외부 전달 단계 진입
- 첫 지점 전달 (어댑터 측 경로 전달 함수 `getMoveTargets` 1회 호출, `Returning 1 targets`)
- **self-loop 연결 구성은 정상 (확인 완료)** — 초기 추정과 달리 self-loop 누락은 원인이 아님

#### Plan-fail 원인 추정 — 시뮬레이션 셀 및 자세 데이터의 기존 로봇 기반 의존성

시뮬레이션 도구 GUI 메시지:
> "DTS Weld Seam Outer Move" 단계에서 동적 오류 발생, 아웃 포트[1] (계획 실패) 경로로 종료, 다음 단계 "프로시저 종료_1"로 분기

원인 분석:

1. **시뮬레이션 셀 구성이 기존 로봇(HS-180) 기준으로 유지**
   - 본 작업본은 원본 프로젝트(HS-180 기반)를 복사한 후 로봇 모델만 MZ07L로 교체한 상태
   - 작업물(part) 위치, 토치 모델, 작업 좌표계 정의가 모두 기존 로봇 기준으로 잡혀 있어, 로봇만 바꿔서는 작업물·토치·로봇 간 상대 위치 관계가 일관되지 않음

2. **자세 데이터가 기존 로봇 운동학·카메라 좌표계 기준**
   - 입력 경로의 자세값(예: rx ≈ -170°)은 카메라 좌표계 기준 토치 자세를 그대로 사용
   - 카메라-로봇 좌표 보정 측정(Hand-Eye Calibration) 미적용 상태이므로 로봇 좌표계로의 자세 변환이 누락됨
   - 결과적으로 위치는 도달 가능 범위 내(0.32 m, MZ07L reach 0.912 m 이하)이나 해당 자세에서의 관절 해석이 실패할 가능성이 높음

3. **로봇 기준점 보정값만 분리되고 셀 전체는 미정렬**
   - 5/18에 `robot_base_m`을 모델별 분리 구조로 변경했으나, 작업물·토치·작업 좌표계는 동일하게 분리되지 않음
   - 로봇만 원점으로 이동시키면 작업물과 로봇이 기하학적으로 충돌하는 형태가 됨

#### 결론
- **통신·등록·구조 검증(시나리오 B 완료 게이트)은 충족**
- 시뮬레이션 환경에서의 역기구학·도달성 정밀 검증은 본사 방문 시 측정값(`T_robot_camera`, TCP, 사용자 좌표계) 적용 후 가능
- 셀 정교화는 M2 이월 항목으로 분리되어 있으며, M4 진입 단계에서 통합 진행 예정

### 5.3 로봇 기준점 보정값 보완 사례

초기 사전 실행에서 도달 불가 오류 발생.

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
- 도달 불가 원인 해소 확인
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

### 시뮬레이션 흐름 — 5/26 진단 결과
- self-loop 연결 구성: **정상 (확인 완료)** — 초기 추정 원인 폐기
- 첫 지점 역기구학 계획 실패: **확인됨** — 원인은 셀 구성·자세 데이터가 기존 로봇 기반에 묶여 있는 데 있음 (자세한 분석은 §5.2)

### 후속 점검·해소 절차
1. **시뮬레이션 셀 정교화 (M2 이월 → M4 진입 단계에 통합)**
   - 작업물(part) 위치, 토치 모델, 작업 좌표계를 실제 로봇(MZ07L) 기준으로 재정의
   - 로봇 기준점(robot base)과 작업물 간 상대 위치 일관성 확보
2. **카메라-로봇 좌표 보정 측정(Hand-Eye Calibration) 적용**
   - 본사 방문 시 실측 → `T_robot_camera` 입력 → 자세 데이터 변환 재생성
3. **변환 후 사전 실행 재검증**
   - 동일 입력 경로(테스트용 부위 한 곳, 다른 부위 포함)로 다시 시뮬레이션 도구 사전 실행
   - 자동 판정 도구로 전체 지점 전달 확인

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
| B — 로컬 재현 검증 | 현장 의존 없이 현재 패키지·코드·시뮬레이션 환경만으로 사전 검증 절차 재현 가능 | **진입 완료** — 통신·등록·구조 검증까지 닫힘 |

**본 시점 판단**: 시나리오 A 진입 조건 미충족 상태가 지속되어 시나리오 B로 진행했고, 본 보고서 시점에 시나리오 B 완료 게이트(통신·등록·구조 검증)는 충족된 것으로 판정한다. 역기구학·도달성 정밀 검증은 시나리오 A 진입(본사 방문 시 측정값 적용) 이후 별도 단계로 진행한다.

---

## 8. 후속 계획

### 즉각 (5/22~5/29)
- 시뮬레이션 도구 내부 반복 실행 연결 구성 점검 및 사전 실행 재검증 (테스트용 부위 한 곳)
- 정상 동작 확인 시 다른 부위 사전 실행 확장
- 본 보고서 §5.2 갱신 (재실행 결과 반영)
- 로컬 재현 기준 검증 절차 점검 — 현장 의존 없이 패키지만으로 사전 검증 절차 재현 가능 여부 확인

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

서비스 정상 등록 및 첫 지점 전달 (파일명의 `*`는 실행 시 자동 생성되는 UUID 부분):

```text
Loaded 5 poses from C:\Users\hanmech\AppData\Local\Temp\dts_robot_frame_pose_*.csv
first: world (-0.0284, 0.0380, 0.3113)  qw=0.0655
last:  world (-0.0128, 0.0095, 0.3159)  qw=0.0853
Registered 'DTS Weld Seam Outer Move' with hub at 127.0.0.1:5308
Ready. Run Mech-Viz simulation — poses will be served at External Move step.
getMoveTargets: di=0
[gather_targets] call #1, pose 1/5: x=-0.0284 y=0.0380 z=0.3113
Returning 1 targets
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
