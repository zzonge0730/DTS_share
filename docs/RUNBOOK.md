# DTS 실행 가이드

> 처음 받아서 실행하는 사람을 위한 문서입니다.
> 기술 상세는 README.md, 개발 이력은 docs/PROJECT_MASTER.md 참고.


## 1. 설치

### 1-1. Python 환경

```bash
# Python 3.10 이상 필요
python3 --version

# 패키지 설치
pip install -r requirements.txt
```

설치되는 패키지: numpy, open3d, Pillow, matplotlib

tkinter가 없으면 GUI 실행 불가 (CLI는 가능):
```bash
# Ubuntu/WSL
sudo apt install python3-tk
```

### 1-2. Mech-Eye SDK (선택)

카메라 촬영 기능을 쓸 경우에만 필요. 경로 생성만 할 때는 불필요.

- Mech-Eye SDK 2.5.4 설치
- Python 바인딩: `pip install MechEyeAPI`


## 2. 데이터 설정

### 2-1. 설정 파일 생성

```bash
cp dts_config.example.json dts_config.json
```

`dts_config.json` 편집:
```json
{
    "data_root": "data/DTS_image"
}
```

공유본에 포함된 샘플 데이터를 쓸 경우 위 경로 그대로 사용하면 됩니다.
별도 데이터 디렉토리가 있으면 그 경로로 변경.

환경변수로도 설정 가능:
```bash
export DTS_DATA_ROOT=data/DTS_image
```

### 2-2. 필요한 데이터 파일

`data_root` 디렉토리 아래에 다음 구조가 필요합니다:

```
DTS_image/
├── pipeline/
│   ├── ref_battery_case.ply         # 기준 포인트 클라우드 (~50MB)
│   └── icp_transform_*.npy         # 정합 변환 행렬 (<1KB)
├── captures/
│   └── point_cloud_*.ply           # 카메라 캡처 파일 (~30MB)
└── cad/                            # (선택) 추가 용접선 CSV
```

**최소 실행 세트**: 기준 PCD 1개 + 캡처 PLY 1개 + 변환 행렬 NPY 1개
→ 공유본의 `data/DTS_image/`에 이미 포함되어 있습니다.

### 2-3. 레지스트리 파일

`data/battery_case/capture_registry_*.json` 파일에 캡처별 경로가 기록되어 있습니다.
이 경로는 원래 개발 환경 기준이지만, `dts_config.json`에 `data_root`를 설정하면 자동으로 변환됩니다.

새 캡처를 추가하면 레지스트리에 자동 등록됩니다.


## 3. GUI로 실행

```bash
# WSL 환경일 경우
export DISPLAY=:0

# GUI 실행
python3 scripts/battery_case_gui.py
```

### GUI 화면 흐름

1. **캡처 선택** — 드롭다운에서 캡처 ID 선택 (또는 "Capture" 버튼으로 새 촬영)
2. **정합(ICP)** — "Register" 버튼 → CAD-PCD 자동 정합 실행
3. **경로 생성** — 용접선 선택 (U1_right, U2_left, S5_long_bottom_steps) → "Run Pipeline" 버튼
4. **결과 확인** — 포즈 수, 정밀도 점수, 품질 판정 표시
5. **내보내기** — 포즈 CSV + 1100 파일 자동 저장


## 4. CLI로 실행

### 4-1. 정합(ICP)

```bash
python3 scripts/register_battery_capture_icp.py \
    --raw-pcd <캡처파일.ply> \
    --ref-pcd <기준PCD.ply>
```

출력: `data/battery_case/live_icp/<캡처ID>/` 에 변환 행렬 + 리포트

### 4-2. 용접 경로 생성

```bash
python3 scripts/battery_seam_pipeline.py \
    --ref-pcd <기준PCD.ply> \
    --meas-pcd <캡처파일.ply> \
    --icp-transform <변환행렬.npy> \
    --seams U1_right U2_left S5_long_bottom_steps \
    --out-dir output/
```

출력: `output/` 에 `*_pose.csv` (6자유도 포즈) + `*_1100.txt` (로봇 전송용)

### 4-3. 카메라 촬영 (Mech-Eye SDK 필요)

```bash
# 카메라 검색
python3 scripts/mecheye_capture.py --discover

# 촬영
python3 scripts/mecheye_capture.py --ip <카메라IP> --out-dir data/captures/
```


## 5. 테스트

```bash
# 단위 테스트 (131개, 데이터 파일 불필요)
pip install pytest
python3 -m pytest tests/

# E2E 테스트 (mock 서버 포함)
scripts/run_e2e_dts_stack.sh
```


## 6. C# DTS (로봇 통신)

로봇 컨트롤러와 UDP로 통신하는 Windows 프로그램입니다.
Python 경로 생성과는 독립적으로 동작합니다.

### 6-1. 빌드 환경

- Visual Studio 2019 이상
- .NET Framework 4.8
- 프로젝트 파일: `DTS/DTS/Workspace/DTS/DTS.sln`

### 6-2. 빌드

```
Visual Studio에서 DTS.sln 열기 → 빌드 → 솔루션 빌드 (Ctrl+Shift+B)
```

### 6-3. 설정 (App.config)

`DTS/DTS/Workspace/DTS/DTS/App.config` 에서 환경에 맞게 수정:

| 항목 | 기본값 | 설명 |
|------|--------|------|
| VISION_IP / VISION_PORT | 172.21.135.200 / 50001 | 비전 TCP 수신 주소 |
| ROBOT_IP / ROBOT_PORT | 172.21.135.200 / 2000 | 로봇 UDP 전송 주소 |
| MY_IP / MY_PORT | 172.21.128.1 / 2001 | DTS 자체 바인드 주소 |
| ICP_FITNESS_MIN | 0.3 | 정합 품질 하한 |
| ICP_INLIER_RMSE_MAX | 1.5 | 정합 RMSE 상한 (mm) |
| X/Y/Z_MIN/MAX | ±5000 | 포즈 안전 범위 (mm) |

### 6-4. E2E 테스트 (mock 서버)

로봇/비전 장비 없이도 mock 서버로 전체 흐름을 테스트할 수 있습니다:

```bash
# WSL에서 mock 서버 실행
scripts/run_e2e_dts_stack.sh

# 또는 개별 실행
python3 mock/mock_vision_tcp.py   # 비전 TCP mock
python3 mock/mock_robot_udp.py    # 로봇 UDP mock
```

Windows에서 DTS.exe 실행 → mock 서버와 통신 → E2E 검증

### 6-5. 참고

- `DTS/DTS/Workspace/` 내 `*.ply`, `*.stl` 파일은 공유본에서 제외 (용량 절감)
- 빌드/실행에는 영향 없음 (테스트용 3D 파일)


## 7. 자주 막히는 문제

### "ModuleNotFoundError: No module named 'dts'"
→ 반드시 `python3 scripts/xxx.py` 형태로 실행. 스크립트가 자동으로 경로를 잡습니다.

### "tkinter not found" / GUI 안 뜸
→ `sudo apt install python3-tk` (Ubuntu/WSL)
→ WSL이면 `export DISPLAY=:0` 필요 (X server가 실행 중이어야 함)

### 정합 실행 시 "PCD file not found"
→ `dts_config.json`의 `data_root` 경로 확인. 해당 디렉토리에 `pipeline/ref_battery_case.ply`가 있어야 합니다.

### 경로 오류 (다른 환경의 절대경로 표시)
→ 레지스트리 JSON에 원래 개발 환경 경로가 들어있지만, `data_root` 설정 시 자동 변환됩니다.
   `dts_config.json`을 아직 만들지 않았다면 만들어주세요.

### "No seam candidates found"
→ `data/battery_case/cad_seams/` 디렉토리에 용접선 CSV 파일이 있는지 확인.
   이 디렉토리는 공유본에 포함되어 있어 정상적으로 받았다면 있어야 합니다.

### Mech-Viz 시뮬레이션 관련
→ Mech-Viz가 설치된 Windows 환경에서만 동작. 없으면 경로 생성까지만 실행 가능.
