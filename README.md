# GFP binder design · v0.1.4

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/HisameOgasahara/tmp_protein/blob/main/GFP_Binder_T4.ipynb?v=0.1.4)

Colab에서 T4 GPU를 선택하고 전체 셀을 실행하면 기본 모드에서 공개 대조군 두 개를 각각 세 시드로 예측합니다. 결정 구조와 접촉면이 유사한 자세가 나왔는지, 그 자세의 ipTM 순위가 몇 위인지 확인합니다.

`BENCHMARK_ONLY`를 해제하면 GFP 구조에서 결합체 뼈대와 서열을 설계하고, 복합체 예측과 형광 평가를 실행합니다. 형광 배율은 구조와 교차 검증 조건을 통과한 후보에 표시합니다.

버전을 올릴 때 노트북 첫 제목, 이 제목과 배지 URL의 `v` 값을 함께 갱신합니다.
