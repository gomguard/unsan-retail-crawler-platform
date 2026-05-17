# UNSAN Retail Crawler Platform

BestBuy, Lowe's, Amazon 등 리테일 사이트의 상품 목록, 상세 정보, 리뷰/가격 데이터를 수집하기 위한 크롤러 작업 공간입니다.

현재 목표는 단순한 스크립트 모음이 아니라, 새 retailer나 새 제품군을 추가할 때 같은 절차로 확장할 수 있는 운영형 크롤러 구조를 만드는 것입니다.

## 핵심 구조

```text
common_settings/  DB 기반 공통 설정 테이블 생성/seed/상태 확인
bestbuy/          BestBuy crawler pipeline
lowes/            Lowe's crawler pipeline
amazon/           Amazon crawler pipeline
references/       DDL, 샘플 schema 등 가벼운 참고 자료
```

로컬 raw/data 산출물은 Git에 올리지 않고 S3와 DB를 기준으로 관리합니다.

## 주요 문서

- `CRAWLER_OPERATION_POLICY.md`: 운영 정책, 폴더 구조, S3/DB/load 기준
- `CRAWLER_CREATION_GUIDE.md`: 비전문가도 따라갈 수 있는 신규 크롤러 생성 가이드

## Common Setting

크롤러는 URL, 결과 테이블명, 실행 옵션을 코드에 직접 박지 않고 DB common setting을 우선 사용합니다.

현재 핵심 테이블:

```text
public.common_setting_step01_target_page_url
public.common_setting_step02_output_table
public.common_setting_step03_run_profile
```

결과 테이블 준비:

```powershell
python -m common_settings.common_setting_orchestrator --from-step 05
```

상태 확인:

```powershell
python -m common_settings.common_setting_status
```

## 기본 실행 예시

BestBuy dry-run:

```powershell
python -m bestbuy.bestbuy_orchestrator --category REF --dry-run --all
```

Lowe's dry-run:

```powershell
python -m lowes.lowes_orchestrator --dry-run --all
```

## 보안/데이터 정책

아래 파일은 Git에 올리지 않습니다.

```text
.env
*/data/
node_modules/
raw response / curl capture / cookies
large sample HTML
local archive
```

API key, DB password, session cookie는 `.env` 또는 별도 secret manager에서 관리합니다.
