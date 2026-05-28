# Stability Report — Battery Case ICP (2026-05-28)

## 1. Scope

- Population: ICP reports under `data/battery_case/reg_icp` and `data/battery_case/live_icp`
- Total reports scanned: **28**
- Valid samples (with `seam_local_metrics.seams`): **25**
- Excluded (seam metrics missing): **3**
  - 20260320_132652_gui, 20260320_134853_gui, 547
- Quality gate: `/home/hanmech/DTS/data/battery_case/quality_gate_v2_2026-04-08.json`
- Archive (`data/archive/failed_icp`): **7** report(s) intentionally excluded from this aggregation
- Seams covered: U1_right, U2_left (S5 has no entries in current ICP reports)
- **Geometry metrics excluded from variation/verdict**: `centerline_p90_mm`, `tangent_p90_deg`, `corridor_inlier_ratio` are sample-invariant in current reports (driven by reference seam geometry, not by capture). They are reported separately in §7 *Reference Seam Geometry Note* and are not used in per-capture verdict.
- **Verdict metrics**: `fitness`, `rmse_mm`, `worst_mean_nn_mm`, `worst_max_nn_mm` (quality_gate_v2 thresholds applied directly).

## 2. Per-Seam Variation (all valid samples)

| seam | metric | n | mean | std | min | max |
|------|--------|---|------|-----|-----|-----|
| U1_right | mean_nn_mm | 25 | 0.820 | 0.680 | 0.384 | 3.411 |
| U1_right | p90_nn_mm | 25 | 1.624 | 1.315 | 0.566 | 5.774 |
| U2_left | mean_nn_mm | 25 | 0.861 | 0.516 | 0.467 | 2.281 |
| U2_left | p90_nn_mm | 25 | 1.710 | 1.381 | 0.782 | 7.068 |

## 3. Global ICP Stats (all valid samples)

| metric | n | mean | std | min | max |
|--------|---|------|-----|-----|-----|
| fitness | 25 | 0.624 | 0.134 | 0.466 | 0.915 |
| rmse_mm | 25 | 1.082 | 0.250 | 0.951 | 1.596 |

## 4. Condition Comparison (REG_* captures)

| condition | fitness | rmse_mm | U1_right.mean_nn_mm | U1_right.p90_nn_mm | U2_left.mean_nn_mm | U2_left.p90_nn_mm |
|---|---|---|---|---|---|---|
| BASE | 0.562 | 0.953 | 0.484 | 1.019 | 0.530 | 0.899 |
| L | 0.563 | 0.953 | 0.449 | 0.957 | 0.467 | 0.788 |
| R | 0.466 | 0.990 | 1.963 | 4.602 | 2.281 | 7.068 |
| NEAR | 0.567 | 0.958 | 0.388 | 0.566 | 0.513 | 1.061 |
| FAR | 0.559 | 0.953 | 0.520 | 1.189 | 0.534 | 0.911 |
| YAWP | 0.559 | 0.951 | 0.432 | 0.718 | 0.516 | 1.059 |
| YAWN | 0.554 | 0.955 | 0.447 | 0.696 | 0.499 | 0.852 |

## 5. Per-Capture Verdict

Quality gate v2 applied directly (no `diagnosis` field on these legacy reports).
Per-sample verdict uses the worst seam for `mean_nn_mm` and `max_nn_mm`. `corridor_inlier_ratio` is excluded (see §1 and §7).

| capture_id | source | condition | verdict | fitness | rmse_mm | worst_mean_nn_mm | worst_max_nn_mm | reasons |
|---|---|---|---|---|---|---|---|---|
| 703 | live_icp | — | BLOCK | 0.861 | 1.574 | 1.608 | 5.698 | worst_max>5.0mm |
| REG_R | reg_icp | R | BLOCK | 0.466 | 0.990 | 2.281 | 7.365 | fitness<0.5, seam_mean>2.0mm, worst_max>5.0mm |
| codex | live_icp | — | BLOCK | 0.894 | 1.577 | 3.411 | 8.386 | seam_mean>2.0mm, worst_max>5.0mm |
| 361 | live_icp | — | WARNING | 0.865 | 1.567 | 1.455 | 4.841 | rmse>1.5mm, seam_mean>1.0mm, worst_max>3.0mm |
| 583 | live_icp | — | WARNING | 0.563 | 0.963 | 0.793 | 3.854 | worst_max>3.0mm |
| 602 | live_icp | — | WARNING | 0.570 | 0.964 | 1.016 | 2.986 | seam_mean>1.0mm |
| 806 | live_icp | — | WARNING | 0.915 | 1.594 | 1.660 | 3.532 | rmse>1.5mm, seam_mean>1.0mm, worst_max>3.0mm |
| CMP978 | live_icp | — | WARNING | 0.913 | 1.596 | 0.978 | 3.153 | rmse>1.5mm, worst_max>3.0mm |
| 007 | live_icp | — | PASS | 0.554 | 0.955 | 0.499 | 1.584 | — |
| 144 | live_icp | — | PASS | 0.562 | 0.959 | 0.738 | 2.952 | — |
| 343 | live_icp | — | PASS | 0.571 | 0.957 | 0.762 | 2.824 | — |
| 643 | live_icp | — | PASS | 0.571 | 0.957 | 0.720 | 2.184 | — |
| CMP763 | live_icp | — | PASS | 0.559 | 0.959 | 0.700 | 2.227 | — |
| R01 | live_icp | — | PASS | 0.562 | 0.953 | 0.521 | 1.177 | — |
| R02 | live_icp | — | PASS | 0.563 | 0.956 | 0.530 | 1.230 | — |
| R03 | live_icp | — | PASS | 0.562 | 0.955 | 0.513 | 1.251 | — |
| R04 | live_icp | — | PASS | 0.562 | 0.955 | 0.519 | 1.311 | — |
| R05 | live_icp | — | PASS | 0.562 | 0.954 | 0.534 | 1.490 | — |
| REG_BASE | reg_icp | BASE | PASS | 0.562 | 0.953 | 0.530 | 1.683 | — |
| REG_FAR | reg_icp | FAR | PASS | 0.559 | 0.953 | 0.534 | 2.068 | — |
| REG_L | reg_icp | L | PASS | 0.563 | 0.953 | 0.467 | 1.438 | — |
| REG_NEAR | reg_icp | NEAR | PASS | 0.567 | 0.958 | 0.513 | 1.618 | — |
| REG_YAWN | reg_icp | YAWN | PASS | 0.554 | 0.955 | 0.499 | 1.584 | — |
| REG_YAWP | reg_icp | YAWP | PASS | 0.559 | 0.951 | 0.516 | 1.850 | — |
| rehearsal_978 | live_icp | — | PASS | 0.570 | 0.955 | 0.675 | 2.543 | — |

## 6. Verdict Summary

- PASS: **17**
- WARNING: **5**
- BLOCK: **3**

## 7. Reference Seam Geometry Note

The following metrics are sample-invariant across the current 25 valid reports — they reflect properties of the reference seam geometry rather than capture-to-capture variation. They are excluded from §2/§4 aggregation and from §5 per-capture verdict, but preserved here for reference.

| seam | centerline_p90_mm | tangent_p90_deg | corridor_inlier_ratio |
|---|---|---|---|
| U1_right | 1.477 | 5.391 | 100.0% |
| U2_left | 2.108 | 6.167 | 81.0% |

**Interpretation**: U2_left's reference corridor inlier ratio is 81%, meaning the reference seam definition itself is loose under the current corridor threshold. This is a property of the seam definition, not capture quality. Tightening or redefining U2_left should be considered separately (tracked under quality_gate_v2 corridor threshold review).

## 8. Reproduction Checklist

> 동일 절차로 본 리포트를 다시 만들어내기 위한 최단 경로. 보유 캡처 외 새 입력은 없음.

### 8-1. 입력 데이터 위치

| 항목 | 경로 | 비고 |
|---|---|---|
| ICP 리포트 (정상 운영 조건) | `data/battery_case/reg_icp/<capture_id>/icp_report_<capture_id>.json` | 7개 (REG_BASE/L/R/NEAR/FAR/YAWP/YAWN) — 조건별 비교 표 소스 |
| ICP 리포트 (live 캡처) | `data/battery_case/live_icp/<capture_id>/icp_report_<capture_id>.json` | 21개 — 변동 폭 모집단 |
| Quality gate 임계 | `data/battery_case/quality_gate_v2_2026-04-08.json` | per-capture verdict 기준 (corridor 제외) |
| 제외 대상 | `data/archive/failed_icp/<capture_id>/icp_report_<capture_id>.json` | 7개, 본 집계 제외 |

### 8-2. 실행 명령

```bash
# 기본 (canonical 산출물 경로 그대로 갱신)
python3 scripts/build_stability_report.py

# 출력 경로 커스터마이즈
python3 scripts/build_stability_report.py \
    --markdown docs/STABILITY_REPORT_2026-05.md \
    --json-out output/stability_report/stability_summary_<ts>.json

# 단위 테스트
python3 -m pytest tests/test_build_stability_report.py -q
```

### 8-3. 예상 출력

- stdout 2줄:
  ```text
  Markdown written: docs/STABILITY_REPORT_2026-05.md
  JSON summary written: output/stability_report/stability_summary_<YYYYMMDD_HHMMSS>.json
  ```
- §1 Scope 수치: scanned=28, valid=25, excluded(seam missing)=3, archive=7
- §6 Verdict Summary: PASS=17, WARNING=5, BLOCK=3 (현 quality_gate_v2 + 현재 캡처 기준; 새 캡처 추가 시 갱신될 수 있음)
- pytest: 17 PASS

### 8-4. 실패 시 확인 분기

| 증상 | 1차 확인 | 참조 |
|---|---|---|
| `No ICP reports under ...` | `data/battery_case/reg_icp`, `data/battery_case/live_icp` 두 디렉토리 존재 및 `icp_report_*.json` 파일 존재 여부 | §1 Scope |
| `valid=0` (스캔은 되지만 유효 0) | 리포트 JSON에 `seam_local_metrics.seams` 필드 존재 여부. 누락 시 ICP 파이프라인 재실행 필요 | §1 제외 목록 |
| 예상보다 BLOCK이 많음 | quality_gate_v2 임계가 바뀌었는지 확인 (`data/battery_case/quality_gate_v2_*.json`) | §5 reasons 컬럼 |
| 모든 캡처가 WARNING (corridor 사유) | 회귀 — 현재 빌더는 corridor를 verdict에서 제외해야 함. `judge()` 내 corridor_inlier 적용 여부 확인 | §1 / §7 |
| REG_* 조건 표가 비어 있음 | `capture_id` prefix가 `REG_`로 시작하고 suffix가 `BASE/L/R/NEAR/FAR/YAWP/YAWN` 중 하나인지 확인 | `parse_condition()` |
| pytest 실패 | `python3 -m pytest tests/test_build_stability_report.py -v` 로 실패 케이스 식별. corridor 회귀 또는 임계값 변경이 흔한 원인 | tests 파일 |

