# GFP 도킹 실행 지연과 GPU 전환

2026-11-17 · 관찰 버전 v0.1.7 · 후속 버전 v0.1.8

## 실행 중 관찰

| 항목 | 확인 결과 |
| --- | --- |
| 초기 실패 | ProDy가 LightDock 원자 선택식을 해석하는 중 SelectionError 발생 |
| 의존성 조치 이후 | 도킹 탐색 로그에 단계 증가와 새 영역 실행 기록 확인 |
| 탐색 규모 | 207개 영역, 영역당 200개 후보, 100단계 |
| 자원 | CPU 병렬 탐색, 화면의 GPU 메모리 사용량 0.0 GB |
| 완료 상태 | 전체 탐색·후처리 완료 시간과 최종 결합면 회복 결과 미확인 |

현재 탐색은 인식된 CPU 코어 수를 사용한다. 전체 영역 수에 비해 동시 처리 자원이 적으면 대기 시간이 길어진다. 구조 생성과 군집화는 영역별로 순차 실행된다. 총 실행 시간은 Colab에서 사전에 측정되지 않았다.

ProDy와 pyparsing의 호환성이 초기 실패의 유력 원인이다. 당시 실제 pyparsing 버전은 제출 로그에서 확인되지 않았다. ProDy 후속 릴리스에는 pyparsing 상한 제한이 포함되어 있다. [ProDy 릴리스](https://github.com/prody/ProDy/releases/tag/v2.5.0)

## 실험 목적과 GPU 대안

실행 05에서 Minimizer는 개별 구조를 제공한 10개 시드 모두 결합면 회복 기준을 통과하지 못했다. 동일한 개별 구조를 이용한 다른 도킹 탐색을 비교한다. [실행 05 분석](2026-11-17-gfp-run05-analysis.md)

MEGADOCK은 두 PDB 구조를 입력받아 CUDA 기반 FFT 강체 탐색을 수행한다. 단일 GPU 실행과 Colab 빌드 설정이 공개되어 있다. v0.1.8은 원래 상대 배치를 제거한 두 구조를 입력하고 점수 상위 자세를 기존 RMSD·접촉·충돌 기준으로 평가한다. 탐색 및 점수 함수가 달라지므로 도구명과 설정을 결과에 기록한다. [공식 구현](https://github.com/akiyamalab/MEGADOCK)

| 설정 | v0.1.8 조건 |
| --- | --- |
| 회전 샘플 | 공식 기본값 3,600개 |
| 격자 간격 | 공식 기본값 1.2 Å |
| 저장 후보 | 공식 기본값 2,000개 |
| 평가 후보 | 점수 상위 최대 100개 |
| 참조 입력 | 실행 05의 동일한 개별 구조 |
| 평가 | GFP 정렬 RMSD, 접촉면 Jaccard, 잔기 쌍 접촉, 비수소 원자 충돌 |

실제 T4 빌드·실행 시간·결합면 회복 성능은 Colab 실행으로 확인해야 한다. MEGADOCK의 라이선스는 CC BY-NC 4.0이며 상업적 이용에는 별도 허가가 필요하다. [빌드 안내](https://github.com/akiyamalab/MEGADOCK/blob/master/doc/BUILD.md) · [라이선스](https://github.com/akiyamalab/MEGADOCK/blob/master/LICENSE)
