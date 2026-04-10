# Gap I/O 계약서 (DTS 연동)

## 1. 목적
- `Form1.cs`의 더미 Gap 판정(`EvaluateGap`)을 실측 기반 판정으로 교체하기 위한 인터페이스를 고정한다.
- 1차 목표는 `max/avg/rms` 지표를 DTS 상태코드(`2100/2002`)에 일관되게 반영하는 것이다.

## 2. 적용 범위
- 생산 경로 전송 직전 품질 판정 단계
- 입력: CAD/PCD 정합 결과 지표
- 출력: `OK/NG`, `reason`, `max_gap`, `avg_gap`, `rms_gap`

## 3. 입력 스키마
### 3.1 파일 입력(JSON) 권장
```json
{
  "session_id": "string",
  "part_id": "string",
  "timestamp": "2026-02-13T10:00:00.000",
  "metrics": {
    "max_gap_mm": 0.0,
    "avg_gap_mm": 0.0,
    "rms_gap_mm": 0.0,
    "samples": 0
  },
  "quality": {
    "source": "gab.py",
    "confidence": 0.0
  }
}
```

### 3.2 최소 필수 필드
- `metrics.max_gap_mm`
- `metrics.avg_gap_mm`
- `metrics.rms_gap_mm`
- `metrics.samples`

## 4. 판정 규칙(1차)
- `samples <= 0` -> `NG`, `reason=NO_RESULT`
- `max_gap_mm > MAX_TOL` -> `NG`, `reason=GAP_EXCEED_MAX`
- `avg_gap_mm > AVG_TOL` -> `NG`, `reason=GAP_EXCEED_AVG`
- 그 외 -> `OK`, `reason=WITHIN_TOL`

`MAX_TOL`, `AVG_TOL`은 기존 `App.config` 설정값을 그대로 사용한다.

## 5. DTS 출력 매핑
- `OK`:
  - `2100,OK,<max_gap>,<avg_gap>,<ts>`
- `NG` (reason별):
  - `2002,GAP_EXCEED_MAX,<max_gap>,<avg_gap>,<ts>`
  - `2002,GAP_EXCEED_AVG,<max_gap>,<avg_gap>,<ts>`
  - `2002,STALE_GAP_DATA,0.000,0.000,<ts>`
  - `2002,INVALID_GAP_DATA,0.000,0.000,<ts>`
- `NO_RESULT / 데이터 부재`:
  - `1004,NO_RESULT,<ts>`
  - `1004,INVALID_GAP_DATA,<ts>`
  - `1004,STALE_GAP_DATA,<ts>`

참고: 상태코드는 기존 쿨다운/중복 억제 정책(`SendStatusOnce`)을 따른다.

## 6. 연동 지점
- 대상 파일: `DTS/DTS/Workspace/DTS/DTS/Form1.cs`
- 교체 후보:
- `EvaluateGap(int poseCount)` 내부 난수 로직 제거
- 외부 지표(JSON/IPC) 로딩 및 검증 로직 추가

## 7. 실패 처리
- JSON 없음/파싱 실패:
  - `NG`, `reason=NO_RESULT`
- 필드 누락/비정상 값(NaN/inf):
  - `NG`, `reason=INVALID_GAP_DATA`
- 데이터 신선도 초과(`STALE_THRESHOLD_SEC`, 기본값 5초, App.config에서 설정):
  - `NG`, `reason=STALE_GAP_DATA`

### 7.1 원자성 보장 (필수)
- Python(`gab.py`)은 임시 파일(`gap_input.json.tmp`)에 먼저 쓴 후 `os.rename`으로 원자적 교체 필수
- DTS는 `.tmp` 파일 존재 시 읽기를 연기하여 부분 쓰기 상태를 감지
- 목적: JSON을 쓰는 도중 DTS가 읽는 race condition → 오염 데이터로 잘못된 경로 전송 방지

## 8. 구현 순서
1. `gab.py` 출력 JSON 생성기 추가
2. DTS에서 JSON 로더/검증기 추가
3. `EvaluateGap`을 실측 지표 기반으로 교체
4. 기존 상태코드/로그 포맷과 회귀 테스트
