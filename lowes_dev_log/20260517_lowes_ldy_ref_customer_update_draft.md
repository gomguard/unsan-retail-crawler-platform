# Lowe's LDY/REF 수집 안정화 현황 및 운영 전환 계획

작성일: 2026-05-17

## 1. 요약

Lowe's REF(냉장고), LDY(세탁기) 카테고리에 대해 메인 목록, 상세 페이지, 최종 산출물 생성까지 end-to-end 테스트를 진행했습니다.

현재까지 가장 안정적으로 확인된 방식은 Lowe's 검색 목록은 실제 브라우저 기반 UC API 방식으로 수집하고, 상세 페이지는 ZenRows 기반으로 수집하되 실패 건에 대해서 UC fallback을 적용하는 구조입니다.

현재 결과 기준으로 REF는 운영 전환 가능한 수준에 근접했고, LDY는 최종 산출물은 완성되었으나 상세 페이지 일부 실패 건에 대한 fallback 보강이 필요합니다. 다음 주에는 금/토/일 반복 테스트와 fallback 안정화를 통해 운영 기준을 확정하고, 2주 후부터 정기 운영 전환을 목표로 합니다.

## 2. 현재 최고 결과

| 카테고리 | 검색어 | Main 성공 | Main unique 상품 | Detail 대상 | Detail 파싱 성공 | Detail 실패 | 최종 row | 최종 가격 채움 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| REF | refrigerator | 13/13 pages | 300 targets | 300 | 300 | 0 | 300 | 300/300 |
| LDY | washing machine | 13/13 pages | 193 targets | 193 | 185 | 8 | 193 | 193/193 |

### REF

- Main 수집: 13페이지 모두 성공
- Main rows: 312
- 최종 target rows: 300
- Detail 성공: 300/300
- Detail 실패: 0
- Final output: 300 rows
- Final price completeness: 300/300

REF는 현재 테스트 기준으로 메인 목록, 상세 페이지, 최종 산출물 모두 안정적으로 생성되었습니다.

### LDY

- Main 수집: 13페이지 모두 성공
- Main rows: 312
- 최종 unique target rows: 193
- Lowe's API 응답 기준 product count: 192, pagination page count: 8
- 9페이지에서 1개 unique가 추가되어 최종 193개 확보
- Detail 파싱 성공: 185/193
- Detail 실패: 8건, 모두 ZenRows 422 RESP001
- Final output: 193 rows
- Final price completeness: 193/193

LDY는 검색 결과 자체가 300개 미만으로 확인되었습니다. 300개 제한은 최대 수집 상한이며, 실제 Lowe's 검색 결과 unique 상품 수가 193개였기 때문에 최종 산출물도 193개로 생성되었습니다.

## 3. 수집 방식 판단

| 영역 | 현재 판단 | 비고 |
|---|---|---|
| Main/Search | UC browser API 우선 | ZenRows search HTML은 413/504 이슈가 있어 primary로 부적합 |
| BSR | UC 전환 가능, ZenRows도 사용 가능 | 현재 LDY BSR은 ZenRows로 24건 성공 |
| Detail | ZenRows 우선 + UC fallback 권장 | REF는 300/300 성공, LDY는 8건 fallback 필요 |
| 저장 | S3/DB 연동 경로 확인 | 현재 dry-run 중심, 운영 전 실제 load 검증 필요 |

## 4. 운영 가능성 측정 기준

금/토/일 3일 동안 일 2회, 총 6회 반복 테스트를 기준으로 운영 가능성을 측정합니다.

| 항목 | 측정 기준 | 운영 가능 기준 |
|---|---:|---:|
| Main page 성공률 | 성공 page / 요청 page | 98% 이상 |
| Main target 생성률 | 생성 target / 기대 target | 98% 이상 |
| Detail fetch 성공률 | 성공 detail / 대상 detail | 95% 이상 |
| Detail fallback 후 성공률 | ZenRows + UC fallback 성공 / 대상 detail | 99% 이상 |
| Final row 생성률 | final rows / target rows | 99% 이상 |
| 가격 필드 완성률 | 가격 채움 rows / final rows | 99% 이상 |
| 실패 기록 완전성 | 실패 건별 status/error/url 기록 | 100% |
| 재실행 가능성 | 실패 건 retry 및 resume 가능 여부 | 가능 |

## 5. 주말 반복 테스트 계획

대상 기간: 금/토/일, 일 2회, 총 6회

| 회차 | 시간대 | 대상 | 확인 항목 |
|---:|---|---|---|
| 1 | 금 오전 | REF, LDY | Main/Detail/Final end-to-end |
| 2 | 금 오후 | REF, LDY | 반복 실행 안정성, 실패 건 기록 |
| 3 | 토 오전 | REF, LDY | VPN/UC 세션 안정성 |
| 4 | 토 오후 | REF, LDY | Detail fallback 성능 |
| 5 | 일 오전 | REF, LDY | S3 dry-run, DB load dry-run |
| 6 | 일 오후 | REF, LDY | 운영 전환 기준 최종 확인 |

## 6. 다음 주 안정화 작업

1. LDY detail 실패 8건 UC fallback 적용
2. Main/Detail benchmark 실시간 기록 정착
3. BSR 수집 UC 전환 테스트
4. S3 실제 업로드 전 dry-run manifest 검증
5. DB load 대상 테이블 및 row count 검증
6. 실패 건 retry/resume 정책 확정
7. 금/토/일 일 2회 반복 테스트 결과표 작성

## 7. 운영 전환 전망

현재 기준으로 REF는 운영 가능 수준에 가깝고, LDY는 상세 페이지 fallback만 보강하면 운영 가능성이 높습니다.

다음 주 안정화 및 반복 테스트를 거쳐, 2주 후부터 정기 운영 전환을 목표로 진행 가능합니다.

운영 전환 전 최종 체크포인트는 다음과 같습니다.

- REF/LDY 각각 6회 반복 테스트 통과
- LDY detail fallback 후 실패율 1% 이하
- Final output row count 및 가격 completeness 기준 충족
- S3/DB 실제 적재 리허설 성공
- 실패 건 로그, benchmark, manifest 파일 자동 생성 확인

## 8. 내부 참고 파일

```text
lowes/data/ref/20260517/output/final_output.csv
lowes/data/ref/20260517/status/20260517_status.json
lowes/data/ldy/20260517/output/final_output.csv
lowes/data/ldy/20260517/status/20260517_status.json
lowes/data/ldy/20260517/detail/parsed/detail_failures.csv
lowes/data/ldy/20260517/main/benchmarks/main_fetch_summary.json
lowes_dev_log/20260517_lowes_ldy_tests.md
```

