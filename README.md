# DTS — 자동 용접 경로 생성 시스템

카메라 촬영 → CAD/PCD 정합(ICP) → 용접 경로 생성 → 품질 판정 → 로봇 전달

## 빠른 시작

### 1. 사전 준비

| 항목 | 버전 | 비고 |
|------|------|------|
| Python | 3.10 이상 | WSL 또는 Linux 권장 |
| Open3D | 0.18 이상 | 정합, PCD 처리 |
| NumPy | 1.26 이상 | |
| Pillow | — | GUI 이미지 표시 |
| matplotlib | 3.8 이상 | 시각화 |
| tkinter | — | GUI (`sudo apt install python3-tk`) |
| Mech-Eye SDK | 2.5.4 | 카메라 촬영 시에만 필요 (선택) |

```bash
pip install -r requirements.txt
```

### 2. 데이터 설정

공유본에 샘플 데이터가 포함되어 있습니다 (`data/DTS_image/`).

설정 파일 생성:
```bash
cp dts_config.example.json dts_config.json
```

`dts_config.json` 편집:
```json
{
    "data_root": "data/DTS_image"
}
```

별도 데이터 디렉토리가 있으면 해당 경로로 변경.
디렉토리 구조:
```
DTS_image/
├── pipeline/
│   ├── ref_battery_case.ply        # 기준 포인트 클라우드
│   └── icp_transform_*.npy        # 정합 변환 행렬
├── captures/
│   └── point_cloud_*.ply          # 카메라 캡처 파일
└── cad/                           # (선택) 추가 용접선 CSV
```

레지스트리 JSON에 원래 개발 환경 절대경로가 들어있지만, `data_root` 설정 시 자동 변환됩니다.

환경변수로도 설정 가능:
```bash
export DTS_DATA_ROOT=data/DTS_image
```

우선순위: `dts_config.json` > `DTS_DATA_ROOT` 환경변수 > 기본값

### 3. 실행

**방법 A: GUI (데모/검증 권장)**
```bash
export DISPLAY=:0  # WSL 환경만
python3 scripts/battery_case_gui.py
```

GUI 흐름: 촬영 → 정합(ICP) → 경로 생성 → 품질 판정 → 내보내기

**방법 B: CLI (개별 단계)**
```bash
# 1단계: 정합
python3 scripts/register_battery_capture_icp.py \
    --raw-pcd <캡처파일.ply> \
    --ref-pcd <기준PCD.ply>

# 2단계: 경로 생성
python3 scripts/battery_seam_pipeline.py \
    --ref-pcd <기준PCD.ply> \
    --meas-pcd <캡처파일.ply> \
    --icp-transform <변환행렬.npy> \
    --seams U1_right U2_left S5_long_bottom_steps \
    --out-dir output/

# 3단계: (선택) 카메라 촬영
python3 scripts/mecheye_capture.py --discover
python3 scripts/mecheye_capture.py --ip <카메라IP> --out-dir data/captures/
```

### 4. 테스트

```bash
pip install pytest
python3 -m pytest tests/              # 단위 테스트 131개
scripts/run_e2e_dts_stack.sh           # E2E 테스트 (mock 서버 포함)
```


## 설정

경로 상수는 `dts/config.py`에 집중되어 있습니다.

| 매개변수 | 기본값 | 설명 |
|----------|--------|------|
| `DEFAULT_ROI_MIN/MAX` | `[-450,-350,1150]`/`[450,250,1450]` | 포인트 클라우드 관심영역 |
| `DEFAULT_ICP_STAGES` | 4단계 (8→4→2→1mm) | 다중 스케일 정합 복셀 크기 |


## 구조

```
dts/                    # 핵심 라이브러리 (독립 실행 가능)
├── config.py           # 경로/상수 관리
├── transforms.py       # 좌표 변환 (오일러, 쿼터니언, 강체)
├── pose.py             # 6자유도 포즈, 리샘플링, 1100 포맷
├── seam.py             # 용접선 로딩, snap 정책, 정밀도 점수
├── icp.py              # 다중 스케일 정합, 품질 판정
└── paths.py            # 캡처 ID/경로 해석

scripts/                # CLI 진입점 및 GUI
├── battery_case_gui.py           # 메인 GUI (tkinter)
├── register_battery_capture_icp.py  # 정합 CLI
├── battery_seam_pipeline.py      # 경로 생성 CLI
├── mecheye_capture.py            # 카메라 촬영
└── ...                           # 보조 실행기

DTS/DTS/                # C# WinForms (.NET 4.8) — 로봇 통신
mock/                   # E2E 테스트용 mock 서버
tests/                  # Python 단위 테스트 (131개)
data/                   # 용접선 정의, 레지스트리, 설정
docs/                   # 설계 문서, 실험 기록
```

### 파이프라인 흐름

```
[카메라] → 원시 PCD
    ↓
[정합(ICP)] → 4단계 Point-to-Plane (8→4→2→1mm)
    ↓            + 용접선 영역 정밀화
[경로 생성] → CAD 용접선 → 표면 snap → 리샘플링 → 6자유도 포즈
    ↓            snap 모드: no_snap / surface_k5 / constrained_k5
[품질 판정] → fitness, RMSE, 용접선 정밀도, 복도 검사
    ↓
[1100 포맷] → DTS (C#) → 로봇 UDP
```

### 주요 기술 결정

- **오일러 규칙**: sxyz (고정축 XYZ = 회전축 ZYX) — Mech-Mind / 현대로봇 표준
- **정합**: 4단계 다중 스케일 Point-to-Plane + 용접선 영역 정밀화
- **품질 기준**: fitness BLOCK<0.50, WARNING<0.55 (v2, 12캡처 기반)
- **좌표계**: 로봇 좌표계 + 오일러 6필드 고정


## 스크립트 목록

**핵심 실행기 (공유본에서 실제 사용)**

| 스크립트 | 용도 |
|----------|------|
| `battery_case_gui.py` | 메인 GUI — 전체 파이프라인 실행 |
| `register_battery_capture_icp.py` | 정합 CLI |
| `battery_seam_pipeline.py` | 용접 경로 생성 CLI |
| `mecheye_capture.py` | 카메라 촬영 |
| `seam_to_pose.py` | 용접선 CSV → 6자유도 포즈 + 1100 포맷 |
| `detect_pcd_edges.py` | edge-snap 실험용 보조 모듈 (파이프라인 import 의존) |
| `overlay_seam_on_rgb.py` | GUI RGB 오버레이 생성 |
| `seam_eval_policy.py` | 품질 기준/임계값 로더 |
| `transforms.py` | 호환성용 변환 shim |
| `_bootstrap.py` | scripts 직접 실행용 경로 bootstrap |

**Mech-Viz 연동 (선택)**

| 스크립트 | 용도 |
|----------|------|
| `mechviz_runtime.py` | Mech-Viz 외부이동 서비스 실행 |
| `viz_outer_move_service.py` | Mech-Viz 포즈 전달 서비스 |

**테스트/E2E 보조**

| 스크립트 | 용도 |
|----------|------|
| `run_e2e_dts_stack.sh` | mock 기반 E2E 실행 |


## 공유본 구성

이 패키지에는 DTS 시스템 재현에 필요한 **모든 구성요소**가 포함되어 있습니다:

```
README.md, requirements.txt, dts_config.example.json
dts/                          # Python 핵심 라이브러리
scripts/                      # CLI + GUI
tests/                        # 단위 테스트 (131개)
mock/                         # E2E mock 서버
DTS/DTS/                      # C# WinForms (.NET 4.8) — 로봇 통신
data/battery_case/            # 용접선 정의, 레지스트리, 설정
data/DTS_image/               # 샘플 PCD 데이터 (최소 검증 세트)
docs/                         # 실행 가이드, 제약사항, 설계 문서
```

**포함된 샘플 데이터** (`data/DTS_image/`):

```
data/DTS_image/
├── pipeline/
│   ├── ref_battery_case.ply         # 기준 PCD
│   └── icp_transform_978.npy        # 기준 변환 행렬
└── captures/
    └── point_cloud_20260317_134008_978.ply  # 기준 캡처
```

`dts_config.json`의 `data_root`를 `data/DTS_image`로 설정하면 GUI와 CLI 모두 바로 실행됩니다.

**참고**: C# 프로젝트에서 `*.ply`/`*.stl` 테스트 파일은 용량 절감을 위해 제외.
Mech-Viz 연동은 Mech-Viz + Mech-Center 별도 설치 필요.


## 문서

| 문서 | 내용 |
|------|------|
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 설치 및 실행 가이드 |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | 현재 제약사항 및 용접선 상태 |
| [docs/PROJECT_MASTER.md](docs/PROJECT_MASTER.md) | 아키텍처, 전략, 결정 기록 |
| [docs/MILESTONES.md](docs/MILESTONES.md) | 로드맵 |
| [docs/GAP_IO_CONTRACT.md](docs/GAP_IO_CONTRACT.md) | Gap JSON / 상태 코드 규약 |


## 현재 상태 (2026-04-10)

- 배터리 케이스 파이프라인: 12건 캡처 검증 완료, 운영 리허설 통과
- 생산용 용접선: U1_right, U2_left, S5_long_bottom_steps (CAD 에지 기반)
- 정합: 4단계 다중 스케일 + 용접선 영역 정밀화, 평균 정밀도 ~0.7mm
- 품질 판정 v2: 차단 fitness<0.50, 경고 fitness<0.55
- GUI: 촬영 → 정합 → 경로 생성 → 품질 판정 → Mech-Viz 내보내기
- 테스트: 131개 통과
- C# DTS 안전장치: StopLatch, fail-closed, 포즈 범위 ±5000mm
