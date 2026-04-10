# Mech-Vision 연동 명세서 (DTS 기준)

## 1. 목적
- 현재 DTS(`Vision TCP -> DTS -> Robot UDP`) 구조를 유지하면서 Mech-Vision/Mech-Viz를 연동하기 위한 구현 명세를 정의한다.
- 목표는 다음 3가지다.
- `READY` 기반 사이클 유지
- 포즈 전달 포맷 표준화(`1100,<cnt>,x,y,z,rx,ry,rz,...`)
- NG/예외 시 안전 차단(`StopLatch`, 상태코드) 유지

## 2. 범위
- 포함
- DTS(C#)와 외부 Vision 엔진 사이 인터페이스 계약
- Mech-Vision/Mech-Viz 명령 매핑(로컬 HS-180 샘플 JOB 근거)
- 상태코드/예외 처리 정책
- 단계별 구현 순서
- 제외
- CAD 곡률 기반 리샘플링/위빙 억제 알고리즘 상세 구현
- 현장 캘리브레이션 파라미터 튜닝

## 3. 기준 코드 및 근거
- DTS 수신/판정/전송: `DTS/DTS/Workspace/DTS/DTS/Form1.cs`
- DTS 설정: `DTS/DTS/Workspace/DTS/DTS/App.config`
- Vision 샘플 명령(101/102/103): `DTS/DTS/HS-180문서/Hi5/9801_COM101.JOB`, `DTS/DTS/HS-180문서/Hi5/9802_COM102.JOB`, `DTS/DTS/HS-180문서/Hi5/9803_COM103.JOB`
- Viz 샘플 명령(201~205): `DTS/DTS/HS-180문서/Hi5/9804_COM201.JOB`, `DTS/DTS/HS-180문서/Hi5/9805_COM202.JOB`, `DTS/DTS/HS-180문서/Hi5/9806_COM203.JOB`, `DTS/DTS/HS-180문서/Hi5/9807_COM204.JOB`, `DTS/DTS/HS-180문서/Hi5/9808_COM205.JOB`
- 공통 송수신: `DTS/DTS/HS-180문서/Hi5/9823_SEND.JOB`, `DTS/DTS/HS-180문서/Hi5/9824_RECV.JOB`

## 4. 현재 시스템 요약
- 로봇이 `READY`를 UDP로 송신한다.
- DTS는 `READY`를 Vision TCP로 전달한다.
- Vision은 DTS로 `1100,<cnt>,x,y,z,rx,ry,rz,...`를 송신한다.
- DTS는 Gap 판정 후 OK면 UDP로 로봇 전송, NG면 `StopLatch`로 차단한다.
- 상태코드는 별도 UDP 포트로 송신 가능(`2002`, `2100`, `1004`).

## 5. 권장 연동 아키텍처
### 5.1 권장안: Adapter 계층 추가
- `Robot <-> DTS` 구간은 변경하지 않는다.
- DTS의 Vision peer를 Mech-Vision/Mech-Viz 직접 연결 대신 `Adapter`로 둔다.
- Adapter가 Mech 명령을 수행한 뒤 DTS 계약 포맷(`1100`)으로 변환해 전달한다.

### 5.2 이유
- DTS/로봇 계약(`1100`, 패킷 분할, Latch)은 이미 동작 검증됨.
- Mech 버전 변경 시 Adapter만 수정하면 된다.
- 향후 `102(비전 결과)`와 `205(Viz 경로)`를 같은 출력 포맷으로 통합할 수 있다.

## 6. 인터페이스 계약
### 6.1 DTS <-> Adapter
- Transport: TCP (DTS 기준 기존 Vision 포트 사용)
- DTS -> Adapter
- `READY`
- Adapter -> DTS
- `1100,<cnt>,x,y,z,rx,ry,rz,...`
- DTS 상태코드 송신(기존 유지)
- `2100,OK,<max_gap>,<avg_gap>,<ts>`
- `2002,<reason>,<max_gap>,<avg_gap>,<ts>`
- `1004,<reason>,<ts>`

### 6.2 Adapter <-> Mech (샘플 JOB 기준)
- 명령 의미는 로컬 HS-180 샘플 기준이며, 실제 장비 SW 버전에서 필드 정의 차이가 있을 수 있으므로 사전 검증이 필요하다.

| Cmd | 용도 | 기대 상태코드(샘플) |
|---|---|---|
| `101` | Vision Trigger | `1102` |
| `102` | Vision Result 조회 | `1100` |
| `103` | Vision Recipe 변경 | `1107` |
| `201` | VIZ 시작 | `2103` |
| `202` | VIZ 종료 | `2104` |
| `203` | VIZ Branch 설정 | `2105` |
| `204` | VIZ Index 설정 | `2106` |
| `205` | VIZ Path 조회 | `2100` |
| `701` | Robot Calibration | `7100`/`7101` |

## 7. 시퀀스 정의
### 7.1 비전 결과 기반(기본)
1. Robot -> DTS: `READY`
2. DTS -> Adapter: `READY`
3. Adapter -> Mech: `101`(Trigger)
4. Adapter -> Mech: `102`(Result)
5. Adapter: 결과 파싱/변환
6. Adapter -> DTS: `1100,...`
7. DTS: Gap 판정 후 Robot 전송 또는 차단

### 7.2 Viz 경로 기반(확장)
1. Adapter -> Mech: `201`(Start)
2. 필요 시 `203/204`(Branch/Index)
3. Adapter -> Mech: `205`(Path)
4. Adapter: TCP pose 추출 -> DTS 포맷 변환
5. Adapter -> DTS: `1100,...`
6. 종료 시 `202`

## 8. 데이터 포맷 규칙
### 8.0 결정사항 (확정)
- 본 프로젝트의 1차 전송 기준은 **로봇 좌표계(Base/User 기준, 현장 셋업값 적용)** 로 고정한다.
- DTS 입력 포맷은 **Euler 6필드**(`x,y,z,rx,ry,rz`)를 사용한다.
- quaternion은 내부 계산/보관에서만 허용하며, DTS 전송 직전에 Euler로 변환한다.

### 8.1 DTS 입력 포맷(고정)
- 헤더: `1100,<cnt>`
- 바디: Pose 1개당 6필드
- 필드 순서: `x,y,z,rx,ry,rz`
- 수치 포맷: 소수점 `.` 사용, 권장 3자리

### 8.2 Adapter 변환 규칙
- Mech 응답에서 pose type이 TCP인 경우 우선 사용한다.
- 추가 필드(예: label/tool)는 DTS 전송에서는 제거하고 내부 로그로만 보관한다.
- 쿼터니언 입력만 존재하면 아래 Euler 변환 규칙을 따른다:
  - **축 순서: ZYX** (Rz → Ry → Rx 순서 적용, 내인성 회전)
  - **Singularity(gimbal lock) 처리**: `|cos(ry)| < 1e-6`이면 rx=0으로 고정 후 rz 계산
  - **출력 단위: 도(degree)** 고정. rad 입력은 Adapter에서 변환
- 좌표계 변환은 `Mech 기준 -> 로봇 좌표계` 4x4 변환행렬(캘리브레이션 결과)로 적용한다.
- 단위는 `mm`/`deg`로 고정하며, rad 입력은 Adapter에서 deg로 변환한다.

### 8.3 카운트 규칙
- DTS의 `CNT_FIELD_MODE`가 `packet`일 때는 배치 개수로 헤더를 채운다.
- `total` 모드는 수신측 파서가 지원할 때만 사용한다.

### 8.4 포즈 유효 범위 (POSE_OUT_OF_RANGE 기준)
HS-180 기준 로봇 좌표계 유효 범위 (현장 캘리브레이션 후 재확인 필요):
- X: [-200, +1200] mm
- Y: [-800, +800] mm
- Z: [-100, +800] mm
- rx/ry/rz: [-180, +180] deg

범위 외 포즈 수신 시 → `POSE_OUT_OF_RANGE` → `2002,POSE_OUT_OF_RANGE,...` 처리 + StopLatch 활성화

## 9. 오류 및 안전 정책
- Mech 결과 없음/타임아웃
  - Adapter → DTS: 빈 `1100` 전송 대신 실패 상태를 내부 로그에 남기고, DTS가 `1004`를 송신하도록 유도
- Gap NG
  - DTS가 `StopLatch`를 활성화하고 READY를 무시한다.
- 통신 단절
  - Adapter는 재연결 백오프를 적용하고 마지막 정상 세션 ID를 로그에 남긴다.
- 재시도 한계 초과
  - 작업 중단 후 운영자 확인(수동 RESET) 절차로 전환

### 9.4 StopLatch Reset 절차
1. Gap NG / 오류 발생 → DTS StopLatch 자동 활성화
2. 운영자: DTS 로그에서 NG 사유 + 타임스탬프 확인
3. 원인 분석 완료 후 DTS 재시작 (Adapter 프로세스 포함)
4. 로봇 READY 신호 재수신 시 정상 재개
- 주의: READY를 무시하는 상태이므로 DTS 재시작 없이 로봇 재기동만으로는 해제 불가

### 9.5 Adapter 타임아웃 / 재시도 기준
- Trigger(101) 응답 타임아웃: **10초**
- 재시도 횟수: 최대 **3회**
- 재시도 간격: **2초** (지수 백오프 적용)
- 한계 초과 시: 작업 중단 → DTS `1004` 송신 → 운영자 확인(§9.4 Reset 절차 적용)

## 10. 구현 체크리스트
### 10.1 P0 (필수)
- DTS 데이터 계약 확정
- `x,y,z,rx,ry,rz` 단일 포맷으로 문서 고정
- Adapter 프로세스 추가
- `READY` 수신 시 `101 -> 102` 실행 후 `1100` 반환
- 파서 단위 테스트
- 정상/누락/필드수 불일치 케이스 테스트
- 로그 스키마 통일
- `session_id`, `cmd`, `status`, `pose_count`, `reason`

### 10.2 P1 (강력 권장)
- 실제 Gap 연동
- 현재 난수 Gap(`uniform/random`) 제거, `gab.py` 기반 실측 지표 연결
- 좌표/자세 검증
- TCP pose 축 방향, 단위(mm/deg), 기준좌표계 검증
- 장비 전원 OFF dry-run
- Mock + 실제 응답 재생 테스트

### 10.3 P2 (확장)
- `205` 기반 경로 수신 모드 추가
- `203/204`로 분기/인덱스 제어 UI 추가
- 제품별 recipe/profile 테이블 운영

## 11. 즉시 다음 작업 리스트
1. 포즈 계약서 확정 (완료)
- 기준: 로봇 좌표계
- 전송: `xyz + rx/ry/rz` (Euler 6필드)
- quaternion: 내부 보관 후 전송 직전 변환
2. Adapter 최소구현
- `READY` 입력, `101/102` 호출, `1100` 출력만 우선 구현
3. 파서 테스트 데이터셋 작성
- 정상 10개, 누락 5개, 오염 5개 payload 고정 샘플 준비
4. DTS 설정값 고정
- `CNT_FIELD_MODE=packet`, `POSES_PER_PACKET=3`, `PAD_LAST_PACKET=true`
5. Gap 더미 제거 계획 수립
- `gab.py` 출력을 DTS 판정식에 연결하는 I/O 계약 작성
6. 현장 리허설
- Mock 1회, 실장비 1회, 실패 로그 회수 후 임계값 재설정

## 12. 현재 리스크
- `mapping.py`의 절대경로 하드코딩으로 재현성 저하
- Python 산출 포맷(7필드 quaternion)과 DTS 입력(6필드 Euler) 불일치
- Gap 판정이 아직 실측이 아닌 더미 모드

## 13. 승인 기준(Go/No-Go)
- Mock 100회 연속에서 파싱 실패 0회
- NG 발생 시 `StopLatch` 100% 동작
- 실장비 30사이클에서 통신 타임아웃 0회
- 자세 오차/경로 오차가 현장 허용치 이내
