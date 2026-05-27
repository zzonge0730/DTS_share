# U2_left Offset Sweep 분석 (2026-05-27)

## 목적

`U2_left` seam의 약 1.0mm 수준 NN 한계가 단순 노이즈인지, seam 정의가 특정 방향으로 치우친 systematic bias인지 정량 확인한다.

본 분석은 **production seam 재정의가 아니라 원인 좁히기용 정량 분석**이다. 실제 seam 정의 변경은 CAD/도면/실물 확인 후 별도 결정해야 한다.

## 실행 조건

- 대상 seam: `U2_left`
- 기준 snap: `constrained_k5`
- 캡처: `763`, `978`
- step: `5.0mm`
- constrained max offset: `2.0mm`
- sweep 방향:
  - global `x`, `y`, `z`
  - local `normal`
  - local `binormal`
- sweep offset: `-3, -2, -1, -0.5, 0, +0.5, +1, +2, +3mm`

실행 명령:

```bash
python3 scripts/analyze_u2_left_offset_sweep.py \
  --captures 763 978 \
  --snap-mode constrained_k5 \
  --top 12
```

출력:

- `output/u2_left_offset_sweep_20260527.csv`
- `output/u2_left_offset_sweep_20260527.json`

## Baseline

현재 `U2_left + constrained_k5` 기준:

| 지표 | 값 |
|---|---:|
| avg mean NN | 0.793mm |
| avg p90 NN | 1.414mm |
| worst max NN | 2.399mm |
| avg centerline p90 | 1.681mm |
| avg tangent p90 | 6.44deg |
| corridor inlier | 100.00% |
| corridor pass | true |

## Sweep 상위 결과

| rank | direction | offset | avg mean NN | avg p90 NN | worst max NN | corridor | pass_all | delta mean NN |
|---:|---|---:|---:|---:|---:|---:|---|---:|
| 1 | binormal | +1.0mm | 0.739mm | 1.323mm | 2.430mm | 92.68% | false | -0.054mm |
| 2 | normal | -0.5mm | 0.748mm | 1.382mm | 2.341mm | 100.00% | true | -0.046mm |
| 3 | z | -0.5mm | 0.764mm | 1.436mm | 2.339mm | 100.00% | true | -0.029mm |
| 4 | binormal | +0.5mm | 0.770mm | 1.350mm | 2.516mm | 97.56% | false | -0.023mm |
| 5 | x | +0.5mm | 0.779mm | 1.355mm | 2.305mm | 97.56% | false | -0.014mm |
| 6 | y | -0.5mm | 0.784mm | 1.331mm | 2.373mm | 100.00% | true | -0.009mm |
| baseline | - | 0.0mm | 0.793mm | 1.414mm | 2.399mm | 100.00% | true | 0.000mm |

## 해석

1. **가장 낮은 mean NN은 `binormal +1.0mm`지만 corridor가 깨진다.**
   - 평균 NN은 0.054mm 개선되지만 corridor inlier가 92.68%로 떨어지고 `pass_all=false`다.
   - 운영 seam 재정의 후보로 바로 쓰기에는 부적합하다.

2. **운영 기준을 유지하면서 가장 좋은 후보는 `normal -0.5mm`다.**
   - 평균 NN은 0.046mm 개선된다.
   - corridor inlier는 100%를 유지한다.
   - centerline p90도 baseline 1.681mm에서 1.359mm로 낮아진다.

3. **개선 폭은 작다.**
   - `normal -0.5mm`의 mean NN 개선은 약 0.046mm다.
   - 이는 seam 정의를 당장 교체할 정도의 강한 증거라기보다는, U2_left에 소량의 normal 방향 bias가 있을 수 있다는 신호로 보는 게 맞다.

## 결론

- `U2_left`는 대규모 재정의가 필요한 상태로 보이지 않는다.
- 정량상 가장 방어 가능한 후속 검토 후보는 **local normal 방향 -0.5mm offset**이다.
- 단, 개선 폭이 0.05mm 수준이므로 CAD/도면/CloudCompare 시각 확인 없이 production seam으로 승격하면 안 된다.

## 다음 액션

1. CloudCompare에서 현재 `U2_left`와 `normal -0.5mm` 후보를 동시에 overlay.
2. 실제 용접선 기준으로 어느 쪽이 도면/형상과 맞는지 확인.
3. 확인 전까지 운영 seam은 기존 `U2_left + constrained_k5` 유지.
