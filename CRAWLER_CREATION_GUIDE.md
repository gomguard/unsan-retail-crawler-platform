# 신규 크롤러 생성 가이드

이 문서는 개발자가 아니어도 “새 사이트 크롤러를 어떻게 추가하는지” 이해할 수 있도록 만든 설명서입니다.

목표는 단순합니다.

```text
새 사이트나 새 제품군이 생겼을 때,
코드를 처음부터 다시 짜지 않고,
DB에 설정을 넣고,
테스트용 테이블에 먼저 수집해본 뒤,
문제가 없으면 운영으로 넘기는 구조를 만든다.
```

이 문서는 사람이 직접 새 크롤러를 추가할 때 따라 할 수 있는 절차를 대상으로 합니다.

기준 운영 정책은 아래 문서입니다.

```text
CRAWLER_OPERATION_POLICY.md
```

이 문서는 그 정책을 더 쉽게 풀어쓴 “실행 가이드”입니다.

---

## 1. 먼저 큰 그림부터 이해하기

크롤러는 쇼핑몰 사이트에서 상품 정보를 가져오는 프로그램입니다.

예를 들어 이런 일을 합니다.

```text
BestBuy에서 refrigerator 검색 결과를 가져온다.
Lowe's에서 washing machine 검색 결과를 가져온다.
Amazon에서 TV best seller 목록을 가져온다.
상품 상세 페이지에 들어가서 가격, 리뷰, 스펙을 보강한다.
최종 결과를 DB 테이블에 넣는다.
```

그런데 사이트마다 구조가 다릅니다.

```text
BestBuy는 GraphQL API를 쓴다.
Lowe's는 REST JSON API를 쓴다.
Amazon은 HTML이 자주 바뀌고 차단도 많다.
Walmart는 embedded JSON이나 검색 API를 찾아야 한다.
```

그래서 매번 코드에 URL과 테이블명을 직접 박아 넣으면 금방 복잡해집니다.

이 문제를 해결하려고 `common_setting` DB 테이블을 만들었습니다.

---

## 2. common_setting을 왜 만들었나

예전 방식은 이런 느낌입니다.

```text
코드 안에 BestBuy URL이 있음
코드 안에 Lowe's URL이 있음
코드 안에 결과 테이블명이 있음
새 제품군이 생기면 코드 수정이 많음
테스트하다가 운영 테이블을 잘못 건드릴 위험이 있음
```

새 방식은 이렇게 바꿉니다.

```text
URL은 DB 설정 테이블에서 읽는다.
결과 테이블명도 DB 설정 테이블에서 읽는다.
몇 페이지를 돌릴지도 DB 설정 테이블에서 읽는다.
처음에는 tmp_* 테스트 테이블에만 넣는다.
운영 테이블은 승인 전까지 건드리지 않는다.
```

즉 역할을 나눕니다.

```text
DB common setting = 무엇을 돌릴지 정하는 설정판
크롤러 코드 = 실제로 수집하는 실행 엔진
local data 폴더 = raw, parsed, debug 파일 보관
S3 = 수집 원본 장기 백업
DB output table = 최종 결과 적재
```

이렇게 하면 새 크롤러를 만들 때 훨씬 쉬워집니다.

---

## 3. 이걸 하면 결과적으로 어떻게 되나

예를 들어 누군가 이렇게 요청했다고 가정합니다.

```text
Lowe's 세탁기(LDY) 크롤러 만들어줘.
main과 bsr 목록을 돌리고,
300개 상품을 뽑고,
상세 페이지에서 가격과 스펙을 보강해서,
DB에 넣어줘.
```

이 가이드를 따르면 최종적으로 아래 상태가 됩니다.

```text
1. DB에 Lowe's LDY main URL이 등록된다.
2. DB에 Lowe's LDY bsr URL이 등록된다.
3. DB에 Lowe's LDY 결과 테이블명이 등록된다.
4. 운영 테이블이 아니라 tmp_lowes_ldy_final_output_날짜 같은 테스트 테이블이 만들어진다.
5. 크롤러가 1~3페이지 정도 먼저 테스트로 돈다.
6. raw 응답 파일이 local data 폴더에 저장된다.
7. parser가 상품 목록을 CSV로 만든다.
8. detail 수집으로 가격/스펙을 보강한다.
9. final_output.csv가 만들어진다.
10. DB tmp 테이블에 적재된다.
11. row 수, 가격 성공률, 실패 이유를 확인한다.
12. 문제가 없으면 나중에 운영 테이블로 전환한다.
```

핵심은 이것입니다.

```text
처음부터 운영 테이블에 넣지 않는다.
항상 tmp 테이블에서 먼저 검증한다.
```

---

## 4. 자주 나오는 용어 쉽게 설명

### retailer

쇼핑몰 이름입니다.

```text
Bestbuy
Lowes
Amazon
Walmart
```

### product_line

제품군입니다.

```text
TV  = TV
HHP = 휴대폰
REF = 냉장고
LDY = 세탁기/건조기
```

### page_type

어떤 종류의 페이지를 수집할지 뜻합니다.

```text
main      일반 검색 결과
bsr       best seller 또는 best-selling 정렬 결과
promotion 프로모션/세일 페이지
trend     trending 페이지
detail    상품 상세 페이지
review    리뷰 페이지
```

### target URL

크롤러가 들어갈 시작 URL입니다.

예:

```text
https://www.bestbuy.com/site/searchpage.jsp?cp={page}&id=pcat17071&st=refrigerator
https://www.lowes.com/search?searchTerm=refrigerator
```

`{page}`는 페이지 번호가 들어갈 자리입니다.

```text
cp={page}
```

이런 URL은 실제 실행 때 아래처럼 바뀝니다.

```text
cp=1
cp=2
cp=3
```

### output table

최종 결과를 넣는 DB 테이블입니다.

테스트 중에는 반드시 `tmp_*` 이름을 씁니다.

예:

```text
tmp_bestbuy_ref_final_output_20260517
tmp_lowes_ldy_final_output_20260517
```

### run profile

크롤러를 몇 페이지 돌릴지, detail은 몇 개 할지 같은 실행 옵션입니다.

예:

```text
default_pages = 3
detail_limit = 50
page_workers = 1
detail_workers = 2
```

### raw

사이트에서 받은 원본 응답입니다.

예:

```text
HTML 원문
JSON 응답
GraphQL 응답
headers
meta 정보
```

raw를 저장하는 이유는 나중에 parser가 틀렸을 때 다시 사이트에 접속하지 않고도 고칠 수 있기 때문입니다.

### parsed

raw에서 필요한 값을 뽑아 정리한 중간 결과입니다.

예:

```text
main_target_occurrences.csv
bsr_rank_map.csv
detail_enriched_rows.csv
```

### final_output.csv

DB에 넣기 직전의 최종 CSV입니다.

---

## 5. 전체 과정 한 번에 보기

새 크롤러를 만들 때는 아래 순서로 진행합니다.

```text
1. 요청 정리
2. 사이트 구조 확인
3. DB에 target URL 등록
4. DB에 output table 등록
5. DB에 run profile 등록
6. 테스트용 tmp 결과 테이블 생성
7. 크롤러 코드 또는 template 준비
8. main 1페이지 테스트
9. bsr 1페이지 테스트
10. parser 결과 확인
11. detail 5개 테스트
12. final_output.csv 생성
13. tmp DB 테이블에 적재
14. 결과 검증
15. full test
16. 운영 전환 여부 결정
```

처음부터 300개, 1000개를 돌리지 않습니다.

항상 작게 시작합니다.

```text
처음: 1페이지, detail 5개
다음: 3페이지, detail 50개
그다음: 300개 전체
마지막: 운영 table 전환
```

---

## 6. DB common setting 테이블 설명

현재 핵심 테이블은 3개입니다.

```text
common_setting_step01_target_page_url
common_setting_step02_output_table
common_setting_step03_run_profile
```

그리고 결과 테이블을 실제로 만드는 step이 있습니다.

```text
common_setting_step05_prepare_output_tables
```

### step01_target_page_url

무슨 사이트의 어떤 URL을 돌릴지 저장합니다.

예:

```text
SEA / REF / Bestbuy / main / https://www.bestbuy.com/site/searchpage.jsp?cp={page}&id=pcat17071&st=refrigerator
SEA / REF / Bestbuy / bsr  / https://www.bestbuy.com/site/searchpage.jsp?cp={page}&id=pcat17071&sp=Best-Selling&st=refrigerator
SEA / REF / Lowes   / main / https://www.lowes.com/search?searchTerm=refrigerator
SEA / LDY / Lowes   / main / https://www.lowes.com/search?searchTerm=washing+machine
```

이 테이블이 있으면 코드가 URL을 몰라도 됩니다.

코드는 DB에서 조건으로 URL을 찾습니다.

```text
corp = SEA
product_line = REF
account_name = Lowes
page_type = main
```

### step02_output_table

결과를 어느 테이블에 넣을지 저장합니다.

예:

```text
SEA / REF / Bestbuy / final        / tmp_bestbuy_ref_final_output_20260517
SEA / REF / Bestbuy / product_list / tmp_bestbuy_ref_product_list_20260517
SEA / LDY / Lowes   / final        / tmp_lowes_ldy_final_output_20260517
```

여기서 중요한 규칙이 있습니다.

```text
테스트 중에는 tmp_* 테이블만 사용한다.
운영 테이블은 직접 건드리지 않는다.
```

### step03_run_profile

몇 페이지를 돌릴지, detail을 몇 개 할지 저장합니다.

예:

```text
Bestbuy REF:
  default_pages = 3
  detail_limit = 50
  page_workers = 1
  detail_workers = 2

Lowes LDY:
  default_pages = 5
  detail_limit = 10
  page_workers = 1
  detail_workers = 2
```

새 사이트는 처음에는 보수적으로 설정합니다.

```text
page_workers = 1
detail_workers = 1 또는 2
```

사이트 차단이나 실패 원인을 먼저 확인해야 하기 때문입니다.

### step05_prepare_output_tables

`step02_output_table`에 등록된 테이블 이름을 보고 실제 DB 테이블을 생성합니다.

예:

```text
tmp_lowes_ldy_final_output_20260517
tmp_bestbuy_ref_product_list_20260517
```

단, `is_active=true`인 것만 생성합니다.

즉 아직 테스트 준비만 해둔 `Walmart` 같은 항목은 `is_active=false`로 두면 실제 테이블이 만들어지지 않습니다.

실행 명령:

```powershell
python -m common_settings.common_setting_orchestrator --from-step 05
```

상태 확인:

```powershell
python -m common_settings.common_setting_status
```

---

## 7. 신규 크롤러 생성 실전 순서

아래 순서대로 하면 됩니다.

### 1단계: 요청을 표로 정리

먼저 아래 값을 정합니다.

```text
corp
product_line
account_name
page_type
target_count
detail_required
review_required
output_mode
```

예:

```text
corp = SEA
product_line = LDY
account_name = Lowes
page_type = main, bsr
target_count = 300
detail_required = yes
review_required = no
output_mode = tmp
```

### 2단계: 사이트가 어떤 방식인지 확인

브라우저 개발자 도구의 Network 탭을 봅니다.

확인할 것:

```text
상품 목록이 HTML에 있는가?
JSON API가 따로 호출되는가?
GraphQL인가?
페이지 이동 방식은 page인가 offset인가 cursor인가?
쿠키나 store 정보가 필요한가?
```

가능하면 HTML scraping보다 API를 우선합니다.

좋은 순서:

```text
1. GraphQL 또는 REST JSON API
2. 페이지 안에 들어있는 embedded JSON
3. HTML selector
4. Playwright로 렌더링된 DOM
```

### 3단계: step01에 URL 등록

URL을 `common_setting_step01_target_page_url`에 등록합니다.

등록 예:

```text
SEA / LDY / Lowes / main / https://www.lowes.com/search?searchTerm=washing+machine
SEA / LDY / Lowes / bsr  / https://www.lowes.com/best-sellers/appliances/washers-dryers/...
```

page 번호가 필요하면 `{page}`를 씁니다.

```text
https://www.bestbuy.com/site/searchpage.jsp?cp={page}&id=pcat17071&st=washing+machine
```

### 4단계: step02에 결과 테이블 등록

결과 테이블명을 정합니다.

테스트 중이면 반드시 `tmp_*`로 만듭니다.

예:

```text
tmp_lowes_ldy_final_output_20260517
tmp_bestbuy_ldy_final_output_20260517
tmp_bestbuy_ldy_product_list_20260517
```

왜 `tmp_*`를 쓰나?

```text
테스트 실패가 운영 데이터에 섞이지 않게 하기 위해서입니다.
컬럼이 틀려도 운영 테이블이 망가지지 않게 하기 위해서입니다.
중복 적재나 삭제 실수를 막기 위해서입니다.
```

### 5단계: step03에 실행 옵션 등록

처음에는 작게 시작합니다.

권장:

```text
default_pages = 1 또는 3
detail_limit = 5 또는 50
page_workers = 1
detail_workers = 1 또는 2
```

차단이 없고 안정적이면 나중에 늘립니다.

### 6단계: tmp 결과 테이블 생성

명령:

```powershell
python -m common_settings.common_setting_orchestrator --from-step 05
```

성공 확인:

```powershell
python -m common_settings.common_setting_status
```

확인할 값:

```text
is_active = true
exists = true
```

### 7단계: main 1페이지 수집

가장 먼저 일반 검색 결과 1페이지만 수집합니다.

확인:

```text
raw response 저장됨
meta 파일 저장됨
status_code 정상
상품 row가 1개 이상 나옴
product_url이 있음
rank가 있음
```

### 8단계: parser 확인

raw를 parsed CSV로 변환합니다.

확인:

```text
main_target_occurrences.csv 생성
상품명 있음
가격 또는 가격 후보 있음
product_url 있음
중복이 심하지 않음
```

### 9단계: bsr 수집

bsr이 있으면 1페이지 수집합니다.

확인:

```text
bsr_rank_map.csv 생성
bsr_rank가 숫자로 잡힘
main과 매칭 가능한 key가 있음
```

bsr URL이 없으면 실패가 아니라 skip입니다.

### 10단계: final target 생성

main과 bsr 결과를 합쳐 최종 대상 상품을 만듭니다.

예:

```text
target_count = 300
main_rank 기준으로 300개 선택
bsr_rank가 있으면 같이 붙임
```

### 11단계: detail 5개 테스트

처음부터 300개 detail을 돌리지 않습니다.

먼저 5개만 봅니다.

확인:

```text
상세 페이지 접근 성공
가격 파싱 성공
스펙 파싱 성공
브랜드/model id 확인
실패 cache 기록
```

### 12단계: final_output.csv 생성

최종 CSV를 만듭니다.

확인:

```text
row 수가 target과 맞는지
필수 컬럼이 있는지
가격 컬럼이 비어 있지 않은지
product_url이 정상인지
batch_id가 있는지
```

### 13단계: tmp DB table에 적재

운영 테이블이 아니라 tmp 테이블에만 넣습니다.

확인:

```text
insert row count
delete existing batch count
table column mismatch 여부
```

### 14단계: 결과 검증

최소한 아래는 확인합니다.

```text
main 수집 row 수
final target row 수
detail 성공 수
가격 성공 수
중복 product_url 수
DB 적재 row 수
실패 사유 top list
```

### 15단계: full test

smoke test가 성공하면 범위를 키웁니다.

예:

```text
pages = 15
target_count = 300
detail_limit = 300 또는 0
```

여기서 `detail_limit=0`은 보통 제한 없이 전체를 의미하도록 각 크롤러에서 사용합니다.

---

## 8. 사이트별로 무엇을 조정해야 하나

사이트마다 가장 많이 달라지는 부분은 아래입니다.

```text
1. 상품 목록을 가져오는 방식
2. 페이지 넘기는 방식
3. 쿠키/session/store context 필요 여부
4. 가격이 어디에 있는지
5. 상세 스펙이 어디에 있는지
6. 차단이 있는지
```

### Pagination 방식

페이지를 넘기는 방식은 사이트마다 다릅니다.

```text
page number 방식:
  page=1
  page=2
  cp=1
  cp=2

offset 방식:
  offset=0
  offset=24
  offset=48

cursor 방식:
  cursor=abc...
  nextToken=xyz...

infinite scroll:
  스크롤할 때마다 API 호출
```

이 값은 코드 안에서 함수로 감싸야 합니다.

예:

```text
url_for_page(page)
build_payload(page)
build_offset(page)
```

### Store context

일부 사이트는 지역에 따라 가격과 재고가 달라집니다.

예:

```text
zipcode
storeNumber
nearByStores
regionCode
selectedStore
```

Lowe's에서 Anchorage가 보였던 이유도 이것입니다.

```text
Anchorage Lowe's 매장 기준 가격/재고를 보여주고 있었던 것
```

즉 Anchorage는 쿠키 하나의 이름이 아니라, store context에 들어간 지역/매장 정보입니다.

주의:

```text
운영 기준 지역이 어디인지 먼저 정해야 합니다.
store context가 바뀌면 가격/재고 결과도 바뀔 수 있습니다.
```

### Anti-bot

사이트가 자동 접근을 막을 수 있습니다.

증상:

```text
403
429
captcha
robot check
empty response
HTML은 오는데 상품이 없음
API 401/403
```

대응 순서:

```text
1. requests 직접 호출
2. browser session으로 쿠키 확보 후 API 호출
3. curl replay
4. Playwright
5. proxy 또는 ZenRows
```

처음부터 큰 병렬로 돌리면 차단 원인을 파악하기 어렵습니다.

---

## 9. BestBuy 조정 방법

BestBuy는 현재 기준 구현입니다.

현재 방식:

```text
main/bsr: GraphQL
promotion: GraphQL 또는 Apollo data
trend: page embedded data 또는 HTML fallback
detail: Apollo/embedded JSON 우선
review: GraphQL
```

새 BestBuy 제품군을 추가할 때 할 일:

```text
1. main URL 확인
2. bsr URL 확인
3. promotion/trend URL이 있는지 확인
4. step01에 URL 등록
5. step02에 final/product_list tmp table 등록
6. step03에 run profile 등록
7. step05로 tmp table 생성
8. BESTBUY_CATEGORY에 새 product_line 지원
9. final_output.csv 컬럼 확인
10. smoke test
```

주의할 점:

```text
TV product_list는 crawl_datetime 컬럼을 쓴다.
HHP/REF/LDY product_list는 crawl_strdatetime 컬럼을 쓴다.
GraphQL response에 errors가 있어도 documents가 있으면 일부 상품은 살릴 수 있다.
promotion_position은 여러 프로모션에 걸리면 "2 ||| 5" 같은 multi value가 될 수 있다.
```

운영 전 확인:

```text
final_output.csv 컬럼과 DB 컬럼이 맞는지
detail 가격 성공률이 충분한지
review가 필요한 제품군인지
promotion/trend가 해당 제품군에 맞게 해석되는지
```

---

## 10. Lowe's 조정 방법

Lowe's는 검색 상품 API가 확인되었습니다.

핵심 endpoint:

```text
https://www.lowes.com/search/products
```

예시 query:

```text
searchTerm=refrigerator
offset=24
adjustedNextOffset=21
nearByStores=1633,2955,2512
ac=false
algoRulesAppliedInPageLoad=false
```

즉 Lowe's는 HTML만 긁는 방식이 아니라 JSON API를 사용할 수 있습니다.

좋은 구조:

```text
1. 브라우저로 search 페이지에 한 번 진입
2. cookie/session/store context 확보
3. 이후 /search/products API를 직접 호출
4. offset을 바꿔가며 pagination
```

Lowe's에서 특히 중요한 값:

```text
searchTerm
offset
adjustedNextOffset
storeNumber
zipCode
nearByStores
regionCode
cookie/Akamai session
```

REF 예:

```text
searchTerm=refrigerator
```

LDY 예:

```text
searchTerm=washing machine
```

주의할 점:

```text
store context에 따라 가격/재고가 달라질 수 있다.
API가 Akamai/session에 의존할 수 있다.
requests 단독 호출은 막힐 수 있다.
브라우저 세션 확보 후 API replay가 안정적이다.
```

Lowe's 신규 제품군 추가 순서:

```text
1. 검색어 확정
2. main URL 확정
3. bsr URL 또는 bsr API 확인
4. step01에 main/bsr URL 등록
5. step02에 tmp final table 등록
6. step03에 run profile 등록
7. step05로 tmp table 생성
8. main API 1페이지 테스트
9. offset pagination 테스트
10. detail 5개 테스트
11. 가격 파싱 성공률 확인
```

---

## 11. Amazon 조정 방법

Amazon은 가장 조심해야 하는 사이트입니다.

이유:

```text
HTML 구조가 자주 바뀐다.
robot/captcha가 자주 나온다.
가격이 list/detail/offer 영역에 흩어져 있다.
리뷰/평점 표시가 제품마다 다르게 보일 수 있다.
```

기본 전략:

```text
main: search HTML
bsr: Best Sellers page
detail: HTML 또는 embedded data
review: 처음에는 생략하거나 별도 확인
```

Amazon 신규 제품군 추가 순서:

```text
1. search URL 확인
2. bsr category URL 확인
3. blocked/captcha 여부 확인
4. step01 URL 등록
5. step02 tmp final table 등록
6. selector/parser smoke test
7. main 1페이지에서 상품 row가 나오는지 확인
8. detail 5개 테스트
```

주의:

```text
처음부터 병렬을 높이지 않는다.
blocked page도 raw로 저장한다.
상품이 0개인 것과 차단된 것을 구분해야 한다.
```

Amazon은 처음에는 generic JSON table로 시작해도 됩니다.

즉 모든 필드를 wide schema로 바로 만들기보다:

```text
row_json에 원본 row 보존
자주 검색할 필드만 column으로 projection
```

이 방식이 안전합니다.

---

## 12. Walmart 조정 방법

Walmart는 아직 active crawler로 완전히 확정하지 않은 상태라 planned 설정으로 두는 것이 좋습니다.

예상 URL:

```text
https://www.walmart.com/search?q=tv&page={page}&affinityOverride=default
https://www.walmart.com/search?q=tv&affinityOverride=default&sort=best_seller&page={page}
```

예상 전략:

```text
main: search page embedded JSON 또는 API
bsr: sort=best_seller
detail: embedded JSON
review: 별도 API 확인 필요
```

Walmart 추가 순서:

```text
1. search URL 확인
2. Network에서 JSON/API 확인
3. embedded JSON이 있는지 확인
4. step01 URL 등록
5. step02 output table은 등록하되 처음엔 is_active=false 가능
6. probe 성공 후 is_active=true 전환
7. step05로 tmp table 생성
8. smoke test
```

주의:

```text
blocked page와 empty result를 구분해야 한다.
store/zip context가 가격에 영향을 주는지 확인해야 한다.
```

---

## 13. smoke test 기준

smoke test는 “작게 돌려서 구조가 맞는지 확인하는 테스트”입니다.

처음에는 아래 정도면 충분합니다.

```text
main 1페이지
bsr 1페이지
detail 5개
DB tmp 적재
```

성공 기준:

```text
raw 파일이 저장됨
meta 파일이 저장됨
main parsed row가 1개 이상
product_url이 있음
rank가 있음
final_output.csv가 생성됨
tmp DB table에 insert 성공
실패 row가 있으면 실패 이유가 기록됨
```

실패해도 괜찮습니다.

중요한 것은 실패 이유가 남아야 한다는 점입니다.

```text
HTTP 403
captcha
parser missing field
price not found
detail timeout
table column mismatch
```

---

## 14. full test 기준

smoke test 후 full test를 합니다.

예:

```text
target_count = 300
main pages = 필요한 만큼
detail_limit = 300
```

확인할 것:

```text
최종 row 수
중복 sku/product_url
가격 파싱 성공률
detail 성공률
review 성공률
DB insert row 수
S3 sync 성공 여부
local cleanup 조건 충족 여부
```

운영 전환은 full test 후에만 합니다.

---

## 15. 운영 전환 기준

운영 테이블로 넘기기 전에 아래를 확인합니다.

```text
target_count 충족
detail 성공률 합의 기준 이상
가격 성공률 합의 기준 이상
중복 검토 완료
S3 sync manifest success=true
DB reload idempotent 확인
운영 table 이름 승인
```

`idempotent`는 같은 batch를 다시 넣어도 결과가 이상하게 중복되지 않는다는 뜻입니다.

보통은 같은 `batch_id`가 있으면 기존 row를 지우고 다시 넣습니다.

---

## 16. 절대 하지 말아야 할 것

```text
테스트 중 운영 table에 직접 적재하지 않는다.
cookie/API key/password를 DB setting에 원문 저장하지 않는다.
raw 없이 parser만 만들지 않는다.
실패 request를 조용히 버리지 않는다.
새 사이트 첫 실행부터 병렬을 크게 잡지 않는다.
S3 성공 확인 전 local cleanup을 하지 않는다.
DB prepare와 DB load를 한 step에 섞지 않는다.
```

특히 cookie와 API key는 조심해야 합니다.

DB에는 이런 식으로 참조 이름만 두는 것이 좋습니다.

```text
proxy_profile_name
secret_key_name
env_key_name
store_profile_name
```

실제 secret 값은 `.env`나 secret manager에서 관리합니다.

---

## 17. 자주 쓰는 명령어

common setting 전체 실행:

```powershell
python -m common_settings.common_setting_orchestrator --all
```

결과 테이블만 준비:

```powershell
python -m common_settings.common_setting_orchestrator --from-step 05
```

상태 확인:

```powershell
python -m common_settings.common_setting_status
```

DB lock 상태 확인:

```powershell
python -m common_settings.common_setting_lock_status
```

BestBuy dry-run:

```powershell
python -m bestbuy.bestbuy_orchestrator --category REF --dry-run --all
```

Lowe's dry-run:

```powershell
python -m lowes.lowes_orchestrator --dry-run --all
```

---

## 18. 새 크롤러 만들 때 최종 체크리스트

아래가 전부 체크되면 “테스트용 신규 크롤러 생성 완료”로 볼 수 있습니다.

```text
[ ] step01_target_page_url에 URL이 있다.
[ ] step02_output_table에 tmp 결과 테이블이 있다.
[ ] step03_run_profile에 실행 옵션이 있다.
[ ] step05 실행 후 tmp table exists=true다.
[ ] main raw가 저장된다.
[ ] main parsed CSV가 생성된다.
[ ] final target CSV가 생성된다.
[ ] detail 5개 테스트가 끝났다.
[ ] final_output.csv가 생성된다.
[ ] tmp DB table insert가 성공했다.
[ ] 실패 row는 실패 이유가 기록되어 있다.
```

운영 전환 체크리스트:

```text
[ ] full target_count를 만족한다.
[ ] 가격 성공률이 기준 이상이다.
[ ] detail 성공률이 기준 이상이다.
[ ] 중복 검토가 끝났다.
[ ] S3 sync가 성공했다.
[ ] 같은 batch 재적재 테스트가 안전하다.
[ ] 운영 table 이름이 승인됐다.
[ ] tmp table에서 운영 table로 전환 계획이 있다.
```

---

## 19. 한 줄 요약

이 구조의 목적은 이것입니다.

```text
새 사이트를 추가할 때 코드부터 고치지 말고,
DB 설정으로 무엇을 돌릴지 정하고,
tmp 테이블에서 먼저 검증하고,
문제가 없을 때만 운영으로 넘긴다.
```

이렇게 하면 새 사이트나 새 제품군을 추가할 때도 같은 절차로 안전하게 크롤러를 만들 수 있습니다.
