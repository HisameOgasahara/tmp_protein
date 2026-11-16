# GFP binder design · v0.1.5

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/HisameOgasahara/tmp_protein/blob/main/GFP_Binder_T4.ipynb?v=0.1.5)

Colab에서 T4 GPU를 선택하고 전체 셀을 실행하면 각 대조군의 GFP와 결합체 구조를 독립적으로 제공하고, recycle 10회와 시드 0·1·2로 결합 자세를 예측합니다. 체인 간 정답 거리는 가립니다. GFP 정렬 후 결합체 RMSD, 잔기 쌍 접촉 회복률, 기존 접촉면 기준 통과 여부와 ipTM 순위를 함께 확인합니다.

비교 조건은 `BENCHMARK_TEMPLATE=target`·`BENCHMARK_RECYCLES=3`, `target`·`10`, `both`·`10` 순서입니다. 개선이 확인되면 `BENCHMARK_SEEDS`를 `0,1,2,3,4,5,6,7,8,9`로 늘립니다. [원인 분석과 개선 방향](docs/2026-11-17-gfp-benchmark-improvement.md), [기존 실행 결과](results)

`BENCHMARK_ONLY`를 해제하면 GFP 구조에서 결합체 뼈대와 서열을 설계하고, 복합체 예측과 형광 평가를 실행합니다. 형광 배율은 구조와 교차 검증 조건을 통과한 후보에 표시합니다.

버전을 올릴 때 노트북 첫 제목, 이 제목과 배지 URL의 `v` 값을 함께 갱신합니다.
