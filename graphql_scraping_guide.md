# GraphQL 스크래핑 완전 가이드

### — Best Buy를 메인 예시로, 모든 GraphQL 사이트에 적용 가능

> 이 가이드는 **비전문가가 AI(Claude Code 등)와 함께 vibe coding으로 개발하기 위한** 문서입니다.
> 코드를 직접 짤 필요 없어요. **AI에게 적절히 요청하는 법**을 배우는 게 핵심입니다.
>
> **메인 예시는 Best Buy**지만, 다음 사이트들에도 같은 원리 적용 가능:
> - GraphQL 있는 사이트: Walmart, Shopify 기반 사이트, Airbnb 등
> - REST 사이트: Target, eBay (Part 6.4 참고)
> - 봇 보호 약한 사이트: Proton VPN으로 대체 가능 (Part 2.2 참고)
> - Amazon: Selenium 권장 (Part 1.2 참고)

---

# 📖 먼저 — 이 가이드 어떻게 열어야 보기 좋아?

이 가이드는 **마크다운(.md) 파일**이에요. 메모장으로 열면 `# 이거`, `**저거**` 같은 기호가 그대로 보여서 읽기 힘들어요. **마크다운 뷰어**로 열어야 표/굵은 글씨/제목이 예쁘게 보입니다.

## 🥇 추천: VS Code (가장 쉬움)

EC2 Windows에서 작업하실 거면 VS Code가 이미 깔려있을 가능성이 커요. 없으면 https://code.visualstudio.com 에서 무료.

**열기 방법**:

1. VS Code에서 `bestbuy_graphql_guide.md` 파일 열기
2. **`Ctrl + Shift + V`** 누르기 → 예쁘게 렌더링된 미리보기가 새 탭으로 열림
3. 또는 **`Ctrl + K` → `V`** (떼고 누름) → 좌우 분할 보기 (편집 + 미리보기 동시)

> 💡 **추천**: `Ctrl + K → V`로 분할 보기. 왼쪽엔 원본, 오른쪽엔 미리보기. 스크롤도 같이 따라가요.

**팁**: 미리보기 화면에서:
- `Ctrl + F` → 검색 (예: "Part 2.6.7" 검색하면 바로 점프)
- 목차의 링크 클릭하면 해당 섹션으로 이동
- 마우스 휠 또는 화살표 키로 스크롤

## 🥈 다른 옵션들

| 환경 | 방법 |
|---|---|
| **GitHub** | 파일 업로드 후 클릭하면 자동 렌더링 |
| **Typora** (유료) | 파일 더블클릭 — WYSIWYG 편집 |
| **Obsidian** (무료) | 파일 추가 — 노트 앱처럼 |
| **브라우저 확장** | Chrome에 "Markdown Viewer" 설치 후 .md 파일 끌어다 놓기 |
| **온라인** | https://stackedit.io 에서 붙여넣기 |

## ⚠️ 이렇게 열면 안 됨

- ❌ **메모장 / Notepad** — 기호 그대로 보여서 눈 아픔
- ❌ **워드(Word)** — 형식 깨짐
- ❌ **VS Code인데 미리보기 안 켬** — 위의 단축키 꼭!

---

# 🚨🚨🚨 필수로 읽어야 할 것 (이거만 봐도 OK)

> **다른 거 다 건너뛰어도 됩니다. 아래 5개만 무조건 읽으세요.**
> **시험에 나옵니다 (진짜로).**

## 🔴 우선순위 0번 — Part 1 전체 (기본 개념) (20분)

> ⚠️ **이거 모르면 다른 거 다 무용지물.** 내가 뭘 만들고 있는지 모르면 방향 잃습니다.

읽어야 할 것:
- **Part 1.1** — 우리가 뭘 만드는지 (2분)
- **Part 1.2** — API, REST, GraphQL, JSON이 뭔지 (10분)
- **Part 1.3** — Best Buy 동작 방식, SKU/BSIN, GET/POST (5분)
- **Part 1.4** — ZenRows가 왜 필요한지 (3분)

이거 안 읽으면:
- AI가 짜준 코드 보고 "이게 뭐야?" 멍해짐
- 고객사 요청 받아도 어떻게 분류할지 모름
- 비용 절약 원리도 이해 못함 (어디서 돈이 새는지 모름)
- 에러 나도 뭐가 잘못된지 감 못 잡음

**여기 못 넘기면 나머지 다 봐도 헛수고입니다.**

## 🔴 우선순위 1번 — Part 2.6.7 체크리스트 (5분)

이거 안 하면 ZenRows 호출이 **2.5배 비싸게** 차감됩니다. **한 달에 수십만 원 차이.**
AI한테 던질 검증 프롬프트 있음.

## 🔴 우선순위 2번 — Part 2.4 비용 계산 (5분)

새 작업 시작 전 호출 수 미리 계산.
**안 하면 며칠 만에 월 한도 소진** 가능.

## 🟡 우선순위 3번 — Part 5.7 고객사 요청 대응 (10분)

"리뷰 추가해줘", "스펙 빼줘" 같은 요청 받았을 때 어떻게 AI한테 시킬지.
9개 시나리오 + **만능 프롬프트 5.7.8**.

## 🟡 우선순위 4번 — Part 5.1 + 5.2 프롬프트 (15분)

AI한테 시킬 때 어떻게 요청해야 결과가 잘 나오는지.
처음 셋업할 때 **그대로 복붙용 프롬프트 6개**.

---

**총 55분 투자로 가이드의 90% 가치를 얻을 수 있어요.**

> 💡 **읽는 순서는 위 번호 그대로**.
> 우선순위 0번(기본 개념)이 깔리지 않으면 1번부터 봐도 멍하니까,
> 무조건 0번부터 차례로.

## 🔑 한 가지만 외운다면 — 이거

```
🚨 작업 시작 전 무조건 Part 2.6.7의 체크리스트 프롬프트 한 번 돌리기.
```

이 한 줄이 가이드 전체의 핵심이에요. 다른 거 다 까먹어도 이거 하나만 기억하세요.

## ❓ 자기 점검 질문 — 다음 답할 수 있나요?

위의 필수 5개 읽고 나면 아래 질문에 답할 수 있어야 해요.

### 🧱 기본 개념 (Part 1 — 못 답하면 매우 위험)

| 질문 | 답이 어디? |
|---|---|
| 1. 우리가 만들 게 정확히 뭔가? (한 문장으로) | Part 1.1 |
| 2. REST와 GraphQL의 차이는? 왜 GraphQL을 쓰나? | Part 1.2 |
| 3. JSON이 뭔가? Python의 어떤 자료형이랑 비슷한가? | Part 1.2 |
| 4. GET과 POST의 차이는? 우리는 왜 POST를 쓰나? | Part 1.3 |
| 5. SKU ID와 BSIN의 차이는? | Part 1.3 |
| 6. ZenRows를 왜 써야 하나? (Akamai가 뭐길래) | Part 1.4 + 2.1 |

### 💰 비용 / 운영 (Part 2)

| 질문 | 답이 어디? |
|---|---|
| 7. ZenRows의 `js_render`을 왜 끄거나 켜면 안 되나? | Part 2.3 + 2.6 |
| 8. Best Buy 1회 호출 시 차감되는 비용은? | Part 2.3 |
| 9. 한 달 한도 25,000회 안에서 어떻게 작업해야 하나? | Part 2.4 |
| 10. 호출 1번이 25× 비용으로 가고 있는지 어떻게 확인? | Part 2.6.2 |
| 11. 새 작업 시작 전에 어떤 프롬프트를 먼저 돌려야 하나? | Part 2.6.7 |

### 🤖 AI 협업 (Part 5)

| 질문 | 답이 어디? |
|---|---|
| 12. AI한테 무작정 "개선해줘"라고 하면 왜 안 되나? | Part 5.1, 5.8 |
| 13. "리뷰 더 받아주세요" 요청 받으면 뭐부터 해야 하나? | Part 5.7.4 |

### 판정

- **기본 개념 (1~6번) 3개 이상 못 답하면 → Part 1부터 다시 정독.** (다른 거 봐도 헛수고)
- **7~11번 중 3개 이상 못 답하면 → Part 2 다시 읽기. 돈 새는 중.**
- **12~13번 못 답하면 → Part 5 살펴보기.**
- **다 답할 수 있으면 → 운영 시작 OK.**

> ⚠️ 기본 개념(1~6번)은 반드시 알아야 해요.
> 이거 모르면 AI가 짜준 코드 봐도 멍하고, 고객사 요청 받아도 어떻게 분류할지 모르고,
> 비용 어디서 새는지도 감 못 잡습니다.

---

# 🗺️ 그 다음 — 상황별로 어디를 볼까?

> 위의 필수 5개 다 읽으셨다면, 이제는 **상황별 길찾기**로 나머지 활용.
> 처음부터 끝까지 읽지 마세요. **필요한 곳만** 찾아보세요.

## 📍 5가지 상황별 길찾기

### 상황 1: "나 이거 처음이야. 뭐부터 봐야 해?"

**딱 3개만 읽으세요. 15분이면 끝.**

1. **Part 1.1** (2분) — 우리가 뭘 만들 건지
2. **Part 1.2** (5분) — 기술 용어들 (REST, GraphQL, JSON, API)
3. **Part 2.1** (3분) — 왜 ZenRows를 써야 하는지

이것만 읽으면 전체 그림이 잡혀요. **나머지는 필요할 때 검색**.

### 상황 2: "AI한테 코드 만들어달라고 시킬 거야"

**Part 5만 보면 됩니다.** 코드 짤 필요 없어요.

1. **Part 5.1** — 좋은 프롬프트 vs 나쁜 프롬프트 (2분)
2. **Part 5.2** — 시작용 프롬프트 6개 (순서대로 복붙)
3. 막히면 **Part 5.5** 디버깅 프롬프트

코드 못 읽어도 돼요. 프롬프트만 복붙하면 AI가 알아서 해요.

### 상황 3: "고객사가 뭐 추가/제거 요청했어"

**Part 5.7로 직행.** 가장 자주 쓰는 섹션이에요.

- 비슷한 시나리오 있으면 (5.7.1~5.7.7) → 거기 프롬프트 복붙
- 비슷한 게 없으면 → **5.7.8 만능 프롬프트** 사용

### 상황 4: "비용이 걱정돼 / 청구서 무서워"

**Part 2 전체 (2.1~2.7).** 30분.

- **Part 2.6.7 체크리스트 프롬프트** (가장 중요) — 한 번 돌리면 돈 새는 거 다 잡힘
- **Part 2.7 estimate_cost** — 작업 시작 전 비용 미리 계산

### 상황 5: "막혔어. 도와줘"

**Part 8.4 FAQ** 또는 **Part 5.5 디버깅 프롬프트**.

증상 검색해서 그대로 복붙하세요.

---

## 🚫 절대 안 해도 되는 것

- ❌ **코드 직접 읽기** — 가이드의 코드들은 AI한테 보여주는 용도예요. 본인이 읽고 이해할 필요 없어요.
- ❌ **순서대로 처음부터 읽기** — 지쳐서 포기합니다. 필요한 곳만.
- ❌ **모든 프롬프트 외우기** — 가이드 옆에 두고 복붙하세요.
- ❌ **GraphQL 문법 공부** — AI가 알아서 합니다.

## ✅ 무조건 해야 하는 것

- ✅ **Part 2.6.7 체크리스트 프롬프트** 한 번은 돌리기 (돈 새는 거 잡기)
- ✅ **작업 시작 전 Part 2.7 estimate_cost 돌리기** (비용 계산)
- ✅ **고객사 요청 받으면 Part 5.7로 가기** (안 그러면 헛다리)
- ✅ **막히면 Part 5.5나 Part 8.4 찾기** (혼자 끙끙대지 말기)

---

## 🎯 빠른 시작 (30분 이내)

처음이신 분은 이 순서로:

```
[1] Part 1.1 읽기 (2분) — 뭘 만들지
        ↓
[2] Part 2.1 + 2.6.7 읽기 (10분) — 비용 위험 인지
        ↓
[3] Part 5.2.1 프롬프트 복붙 (5분) — AI한테 환경 설정 시키기
        ↓
[4] Part 5.2.2 ~ 5.2.6 프롬프트 차례로 복붙 (10~20분)
        ↓
[5] 작은 테스트 — top_n=5로 검증
        ↓
[6] Part 2.6.7 체크리스트 프롬프트 한 번 돌리기
        ↓
끝! 운영 시작 가능
```

코드 한 줄도 안 짰지만 동작하는 스크래퍼가 생겼어요.

---

## ⚠️ 이 가이드의 핵심 철학

**비전문가가 코드를 직접 보고 멍해질 수 있어요.** 그래서:

1. ✅ **모든 대응은 "그대로 복붙 가능한 프롬프트"로 제공**
2. ✅ **AI에게 물어볼 때 무엇을 함께 첨부할지 알려줌**
3. ✅ **"왜 이런 프롬프트로 물어야 하는지"도 설명**
4. ❌ **코드 직접 수정 강요하지 않음**

### 실전 예시 — 비전문가가 빠지는 함정 vs 가이드의 접근

**함정 (이렇게 하면 멍해짐)**:
> 가이드: "zenrows_client.py에서 `js_render` 옵션을 환경변수로 처리하세요"
>
> 비전문가: 😵 어디 파일? 어디 줄? 어떻게 바꿔?

**가이드의 접근 (그대로 복붙)**:
> AI한테 이 프롬프트 던지세요:
>
> ```
> 내 zenrows_client.py에서 js_render 옵션을 환경변수로 토글 가능하게 만들어줘.
> 기본값은 "0"(false)으로. BESTBUY_JS_RENDER 환경변수로 제어.
> .env.example에도 추가해줘.
> ```

→ AI가 알아서 파일 찾고, 수정하고, 설명까지 해줘요.

## 이 가이드를 읽는 방법 (개념 학습용)

만약 기술 개념도 좀 이해하고 싶다면, 모든 개념은 다음 순서로 설명되어 있어요:

1. **왜 이게 만들어졌나** (어떤 문제를 풀려고 등장했는지)
2. **어떻게 동작하나** (구조 설명)
3. **우리한테 어떻게 적용하나** (실제 사용)
4. **AI한테 어떻게 시킬까** (프롬프트 템플릿)

> AI한테 새 개념을 물어볼 때도 이렇게 물어보세요:
> "X 기술이 왜 만들어졌어? 어떤 문제를 풀려고?"
> 이렇게 물으면 단순 정의보다 훨씬 본질적인 답이 나와요.

---

## 목차

- **Part 1. 알아야 할 개념** — 10분 읽기 (기술이 왜 존재하는지)
- **Part 2. ZenRows와 비용 계산** ⭐ — 돈이 어떻게 빠져나가는지 + 체크리스트 프롬프트
- **Part 3. 시스템 설계** — 우리가 만들 구조
- **Part 4. 구현** — AI에게 시킬 모듈들의 청사진
- **Part 5. AI에게 작업 시키는 법** ⭐⭐ — 모든 상황별 프롬프트 (가장 자주 볼 곳)
- **Part 6. 새 사이트/기능 추가하기** — GraphQL 쿼리 추출하는 법
- **Part 7. 환경 설정 (EC2 Windows)** — 실제 운영
- **Part 8. 레퍼런스** — 막혔을 때 찾아볼 자료

---
---

# Part 1. 알아야 할 개념

## 1.1 우리가 만들 게 뭔가

Best Buy 웹사이트에서 **상품 정보를 자동으로 수집**하는 프로그램이에요. 구체적으로:

1. 검색어 입력 (예: "cellphone") → 검색 결과의 모든 상품 SKU 목록 가져오기
2. 각 SKU별로 상세 정보 가져오기 (이름, 가격, 평점, 스펙 등)
3. 각 상품의 "비교 추천 상품(Compare similar products)" 목록도 가져오기
4. 비교 추천 상품들의 상세 정보까지 가져오기
5. 전부 정리해서 저장 (JSON, CSV, DB 등)

### 왜 이게 어려운가?

Best Buy는 봇이 자동으로 정보 긁어가는 걸 막아놨어요. 그래서:
- 일반 Python 코드로 요청하면 즉시 차단됨 (403 에러)
- **ZenRows** 같은 봇 우회 서비스를 끼고 호출해야 통과됨
- ZenRows는 호출당 돈을 내니까, **호출 수를 최소화**하는 게 핵심

---

## 1.2 데이터는 어떻게 왔다 갔다 하나 (왕초보 버전)

### 우리가 웹사이트를 볼 때 실제로 일어나는 일

여러분이 Best Buy 웹사이트를 열면 보이는 화면 뒤에서 사실은 이런 일이 벌어져요:

```
   [내 컴퓨터/브라우저]                    [Best Buy 서버]
        │                                      │
        │   "Galaxy S26 페이지 보여줘"          │
        │  ─────────────────────────────────►  │
        │         (요청 = Request)              │
        │                                      │
        │                                      │  데이터베이스에서
        │                                      │  상품 정보 찾는 중...
        │                                      │
        │   {이름: "Galaxy S26",                │
        │    가격: 799.99,                      │
        │    이미지: "...", ...}                │
        │  ◄─────────────────────────────────  │
        │         (응답 = Response)             │
        │                                      │
   화면에 보여줌
```

이걸 **"클라이언트(나)와 서버(Best Buy) 사이의 통신"**이라고 해요. 우리가 만들 스크래퍼도 결국 이걸 흉내내는 거예요.

### 메시지 형식 — JSON

#### JSON이 만들어진 이유

옛날(1990년대~2000년대)엔 데이터를 주고받을 때 **XML**이라는 형식을 많이 썼어요. 이런 모양:

```xml
<product>
  <name>Galaxy S26</name>
  <price>799.99</price>
  <inStock>true</inStock>
</product>
```

장점도 있었지만 문제가 컸어요:
- **너무 복잡함** — 여는 태그/닫는 태그 다 써야 함
- **데이터 크기 큼** — 같은 정보인데 글자 수 2~3배
- **파싱이 느림** — 컴퓨터가 해석하는 데 시간/메모리 많이 씀

2001년 Douglas Crockford라는 사람이 더 간단한 대안을 만들었어요. 그게 **JSON** (JavaScript Object Notation).

JavaScript의 객체 표기법을 그대로 가져와서:
- 닫는 태그 같은 거 없음
- 사람이 읽기도 쉽고, 컴퓨터가 처리하기도 빠름
- 거의 모든 프로그래밍 언어가 쉽게 지원

→ XML을 거의 대체했어요. 지금은 웹 API의 표준 형식.

#### JSON 생김새

```json
{
  "이름": "Galaxy S26",
  "가격": 799.99,
  "재고": true,
  "리뷰_개수": 295
}
```

Python의 dict랑 거의 똑같아요. 키와 값이 짝지어진 구조.

```python
# Python에서는 그냥 dict처럼 다룸
data = {"이름": "Galaxy S26", "가격": 799.99}
data["이름"]  # "Galaxy S26"
```

### "API"가 뭔가?

#### API가 만들어진 이유

처음 인터넷이 만들어졌을 땐 **사람이 보는 웹페이지(HTML)** 만 있었어요. 사람이 브라우저로 보고 클릭하는 거.

근데 점점 **프로그램끼리 데이터를 주고받아야 할 일**이 생겼어요:
- 가격 비교 사이트가 여러 쇼핑몰 가격을 모음
- 모바일 앱이 서버에서 데이터 받아옴
- A 회사 시스템이 B 회사 시스템과 연동

사람이 보는 HTML은 프로그램이 해석하기 어려워요. 그래서 **프로그램을 위한 별도의 창구**를 만들기 시작했어요. 이게 **API**.

#### API 정의

API = **A**pplication **P**rogramming **I**nterface

쉽게 말하면 **"프로그램이 다른 프로그램에게 데이터 달라고 부탁하는 창구"**. 식당에 비유하면:

```
[손님(내 코드)]  →  [점원(API)]  →  [주방(서버 내부)]
                       ↑
              "메뉴판"이 정해져 있음
              어떻게 주문하면 뭐가 나오는지
```

API는 보통 두 가지 종류가 있어요: **REST**와 **GraphQL**. 이 두 가지가 우리가 알아야 할 핵심.

---

### REST API — 전통적인 방식 (식당 비유)

#### REST가 만들어진 이유

2000년대 초, 인터넷이 폭발적으로 커지면서 **컴퓨터끼리 데이터를 주고받을 표준**이 필요해졌어요.

이전엔 회사마다 자기 식으로 통신했어요:
- A 회사: "PRODUCT_GET 123" 같은 자체 형식
- B 회사: 자기만 아는 XML 구조
- C 회사: 또 다른 방식

→ **모든 회사의 통신 방식이 달라서 개발이 지옥**. 새 회사랑 연동하려면 매번 처음부터 배워야 함.

이걸 해결하려고 2000년에 로이 필딩이라는 사람이 박사논문에서 **REST**라는 원칙을 제안했어요.

핵심 아이디어:
- **이미 잘 동작하는 웹(HTTP) 기술을 그대로 쓰자**
- URL로 자원(데이터)을 표현하고, HTTP 메서드(GET/POST/PUT/DELETE)로 동작 표현
- 누구나 직관적으로 이해 가능

```
GET    /products/123     → 상품 123 정보 가져오기
POST   /products         → 새 상품 만들기
PUT    /products/123     → 상품 123 수정
DELETE /products/123     → 상품 123 삭제
```

웹 개발자라면 누구나 보자마자 이해 가능한 형식. 그래서 **표준처럼 자리잡았어요**.

---

#### REST의 구조: 메뉴마다 따로 주문

REST API는 **메뉴마다 따로 주문**하는 방식이에요.

식당 메뉴판:
```
URL: /api/products/123        →  상품 정보
URL: /api/reviews/123         →  상품 리뷰
URL: /api/recommendations/123 →  추천 상품
URL: /api/products/123/stock  →  재고 정보
```

각 URL이 하나의 "메뉴". 원하는 메뉴 URL로 요청 보내면 그것만 받음.

#### REST 실제 예시

```
요청: GET https://api.bestbuy.com/products/6650408

응답:
{
  "skuId": "6650408",
  "이름": "Galaxy S26",
  "가격": 799.99,
  "브랜드": "Samsung",
  "이미지": "...",
  "스펙": {...},
  "기타_모든_필드": "..."
}
```

#### REST의 특징

✅ **장점**:
- 직관적. URL 보면 뭘 가져올지 알기 쉬움
- 웹 표준(HTTP)을 그대로 쓰니까 캐싱, 보안, 모니터링 도구가 풍부
- 단순한 사이트는 이걸로 충분

❌ **단점**: REST가 만들어진 2000년대엔 데스크탑 웹이 전부였어요. 그땐 문제 없었는데, **모바일 시대가 오면서 한계**가 드러났어요:

1. **여러 정보 필요하면 여러 번 요청**
   - 상품 1개 화면에 상품정보 + 리뷰 + 추천을 보여주려면 → 3번 요청 필요
   - 데스크탑 시대엔 OK, 모바일 4G에선 느림

2. **필요 없는 데이터도 다 받음** (오버페치)
   - 상품 이름만 필요한데 → 응답에 스펙 100개도 다 따라옴
   - 데이터 요금제/배터리 낭비

3. **정보 부족하면 또 요청** (언더페치)
   - 상품 받았는데 카테고리 이름이 빠져있어 → 카테고리 API 또 호출

이런 문제가 큰 사이트일수록 심각해져요. **호출 수가 폭증**하니까요.

→ 이 문제 때문에 GraphQL이 등장했어요.

---

### GraphQL — Best Buy가 쓰는 방식 (식당 비유)

#### GraphQL이 만들어진 이유

2012년 Facebook 모바일 앱 팀에 큰 고민이 있었어요.

**뉴스피드 화면**을 모바일 앱에서 보여주려는데:
- REST로 만들면 → 게시물 1개당 5~10번 호출 (작성자, 좋아요, 댓글, 사진...)
- 피드에 게시물 50개 → **수백 번의 호출**
- 모바일 4G에선 너무 느림. 배터리 다 닳음

기존 REST의 두 가지 문제가 동시에 터졌어요:
1. 화면 하나 보여주려고 호출 너무 많음 (N+1 문제)
2. 호출마다 필요 없는 데이터까지 다 옴 (오버페치)

Facebook은 처음엔 화면마다 전용 REST 엔드포인트를 만들었는데, 화면이 바뀔 때마다 백엔드 API도 새로 만들어야 했어요. **개발 속도가 안 따라옴**.

그래서 Facebook 엔지니어 Lee Byron 등이 2012년 사내에서 GraphQL을 개발하기 시작했고, 2015년에 공개했어요.

핵심 발상의 전환:
```
[REST의 사고방식]
서버가 정한 응답을 클라이언트가 받는다.
"이 URL에 요청하면 이런 데이터를 주겠다"

[GraphQL의 사고방식]
클라이언트가 필요한 것을 정의하고, 서버는 그에 맞춰 준다.
"내가 원하는 모양을 알려주면 그대로 줘"
```

**힘이 클라이언트로 넘어옴**. 화면 바뀔 때마다 백엔드 안 바꿔도 됨.

→ 이게 GraphQL이 푼 핵심 문제예요.

---

#### GraphQL의 구조: 한 번에 원하는 것만

GraphQL은 **한 번에 원하는 것만 골라서 주문**하는 방식이에요.

식당 비유 계속:
```
[REST 손님]:
  "물 주세요" → 물 받음
  "빵 주세요" → 빵 받음
  "스테이크 주세요" → 스테이크 받음 (감자, 야채 다 따라옴)
  → 점원이 3번 왕복

[GraphQL 손님]:
  "물, 빵, 스테이크는 미디엄으로 감자만, 야채는 빼고. 한꺼번에 주세요"
  → 점원이 1번에 정확히 그것만 가져옴
```

#### GraphQL 실제 예시

요청:
```graphql
{
  product(skuId: "6650408") {
    이름             # 이름만 받을게요
    가격             # 가격만 받을게요
    customerReviews {  # 리뷰는 평점이랑 개수만
      averageRating
      reviewCount
    }
                       # 다른 건 안 줘도 돼요
  }
}
```

응답:
```json
{
  "data": {
    "product": {
      "이름": "Galaxy S26",
      "가격": 799.99,
      "customerReviews": {
        "averageRating": 4.8,
        "reviewCount": 295
      }
    }
  }
}
```

**원하는 것만 받음**. 군더더기 없음.

#### GraphQL의 진짜 강력한 점: 한 요청에 여러 종류 묶기

```graphql
{
  # 상품 정보
  product(skuId: "6650408") { 이름 가격 }

  # 리뷰
  reviews(skuId: "6650408") { 평점 개수 }

  # 추천 상품
  recommendations(skuId: "6650408") { 추천_SKU_목록 }
}
```

REST였으면 3번 요청해야 할 걸 **한 번에** 끝냄.

#### GraphQL이 우리한테 좋은 이유

✅ **ZenRows 호출 1번 = 우리 돈 = 약 $0.00276 (Best Buy 기준)**

REST면 3번 = ~$0.008인데 GraphQL이면 1번 = $0.00276. **3배 절감**.

그래서 Best Buy 작업에서 GraphQL을 적극 활용하는 게 핵심이에요.

---

### REST vs GraphQL 한눈에 보기

| 항목 | REST | GraphQL |
|---|---|---|
| 비유 | 메뉴 따로따로 주문 | 한 번에 원하는 것만 |
| URL | 메뉴마다 다른 URL | URL 하나 (`/graphql`) |
| 요청 방식 | GET, POST 등 다양 | 보통 POST |
| 응답 크기 | 큼 (필요 없는 것도 옴) | 작음 (요청한 것만) |
| 여러 정보 필요할 때 | 여러 번 요청 | 한 번에 묶기 가능 |
| Best Buy는? | ❌ 안 씀 | ✅ 사용 중 |

---

### 한계 — GraphQL도 마법은 아님

**A의 결과를 보고 B를 요청해야 할 때는 두 번 호출 불가피.**

예시:
```
1. 검색 → SKU 10개 받음 (어떤 SKU인지 미리 모름)
2. 그 10개 SKU의 상세 정보 받음
```

검색 결과를 봐야 어떤 SKU를 물어볼지 알기 때문에, 한 번에는 못 함.

이게 우리 Step 1 → Step 2 흐름이에요 (Part 3에서 자세히).

### 정리: 우리가 만들 코드의 모양

```python
# 1. Best Buy에 GraphQL 요청 보내기
request = {
    "query": "{ product(skuId: \"6650408\") { 이름 가격 } }"
}

# 2. ZenRows를 통해 POST
response = requests.post("https://...gateway/graphql",
                        json=request,
                        ...ZenRows 설정...)

# 3. JSON 응답 받음
data = response.json()
print(data["data"]["product"]["이름"])  # "Galaxy S26"
```

기본 흐름은 이게 전부예요. Part 4에서 이걸 모듈로 깔끔하게 만들 거예요.

---

### 잠깐, 어떤 사이트나 다 GraphQL로 가능한가?

**아니요.** 우리가 GraphQL로 호출할 수 있는 건 **그 사이트가 GraphQL을 미리 만들어놨을 때**만 가능해요.

```
┌────────────────────────────────────────────────────┐
│  GraphQL 있는 사이트 (스크래핑 친화적)               │
│  Best Buy, Walmart, Shopify 사이트들, Airbnb 등    │
│  → GraphQL 쿼리로 데이터 받기 가능 ✅              │
│                                                    │
├────────────────────────────────────────────────────┤
│  REST만 있는 사이트                                 │
│  Target, eBay, 많은 전통적 사이트                   │
│  → REST 호출로 데이터 받기 (GraphQL은 못 씀)       │
│                                                    │
├────────────────────────────────────────────────────┤
│  공개 API 없는 사이트                               │
│  HTML만 내려주는 사이트                             │
│  → HTML을 받아서 직접 파싱해야 함                  │
│                                                    │
├────────────────────────────────────────────────────┤
│  Amazon — 특수 케이스                                │
│  공식 API: SP-API/PA-API (승인 필요)                │
│  내부: GraphQL + REST + HTML 혼용                   │
│  → 보통 Selenium/Playwright + HTML 파싱이 무난     │
└────────────────────────────────────────────────────┘
```

### Amazon은 어떻게 접근하나

Amazon은 GraphQL이 깔끔하게 잡히는 사이트는 아니지만, **Selenium이나 Playwright로 충분히 가능**해요. 실제로 많이 쓰이는 방법이에요.

| 옵션 | 장점 | 단점 |
|---|---|---|
| **Selenium/Playwright** | HTML이 잘 그려진 상태에서 파싱. Best Buy처럼 봇 보호 빡세지 않음 | 느림 (페이지당 몇 초) |
| **공식 API (SP-API/PA-API)** | 안정적, 합법 | 자격 요건 (셀러/제휴마케터) |
| **상용 서비스** (Keepa, RainforestAPI) | 가격 히스토리까지 가공된 데이터 | 추가 비용 |

### Amazon vs Best Buy 차이

| 항목 | Amazon | Best Buy |
|---|---|---|
| 데이터 받는 방법 | 주로 HTML 렌더링 후 파싱 | GraphQL 직접 호출 |
| 추천 도구 | Selenium/Playwright | ZenRows + requests |
| 속도 | 느림 (브라우저 띄움) | 빠름 (단순 POST) |
| 호출당 비용 | 낮음 (단순 HTML fetch) | ZenRows protected results |
| 봇 보호 | 중간 (CAPTCHA 가끔) | 강함 (Akamai) |

### 정리

Amazon은 **다른 도구가 더 잘 맞는 케이스**예요. Best Buy 방식(ZenRows + GraphQL)을 그대로 적용하려면 어려운데, Selenium 같은 브라우저 자동화로 가면 오히려 쉬워요.

이 가이드는 **GraphQL 기반 사이트(Best Buy 류)** 에 최적화되어 있어요. Amazon 작업하려면 별도 Selenium 가이드가 더 적합합니다.

새 사이트 작업 시작 전 항상 **Part 6.2의 절차로 확인**해야 해요 (F12 → Network → GraphQL 요청이 있는지).

### 왜 큰 회사들은 GraphQL을 쓰기 시작했나?

GraphQL은 2015년 Facebook이 공개한 기술이에요. 그 전까지는 다들 REST만 썼어요. 회사들이 GraphQL로 옮긴 이유:

#### 1. 모바일 앱 때문에

스마트폰 시대가 오면서 문제가 생겼어요:

```
[데스크탑 웹]                    [모바일 앱]
큰 화면, 빠른 인터넷               작은 화면, 느린 4G
→ 데이터 많이 받아도 OK            → 데이터 조금만 받고 싶음
```

REST는 응답이 정해져 있어서 데스크탑이든 모바일이든 똑같이 받음. 모바일은 **필요 없는 데이터까지 받느라 느림 + 배터리 소모**.

GraphQL로 옮기니까:
- 데스크탑: 모든 필드 요청
- 모바일: 필요한 필드만 요청
- **하나의 API로 둘 다 효율적으로** 처리 가능

#### 2. 프론트엔드 개발자가 빨라짐

REST 환경:
```
프론트엔드: "이 화면에 카테고리 이름도 필요해요"
백엔드: "그럼 API 새로 만들어드릴게요... 3일 걸려요"
```

GraphQL 환경:
```
프론트엔드: 쿼리에 categoryName 한 줄 추가
→ 백엔드 작업 없이 바로 됨
```

신기능 출시 속도가 빨라져요. 회사 입장에서 매우 큰 이점.

#### 3. 화면당 호출 수 감소 = 서버 부하 감소

상품 페이지 하나 열면 REST는 5~10번 호출되는 경우가 흔해요. 트래픽 많은 사이트는 서버 비용 폭증.

GraphQL은 한 번에 묶으니까 서버 호출 수가 줄어요. **인프라 비용 절감**.

#### 4. 모니터링과 분석이 쉬워짐

GraphQL은 어떤 필드를 누가 얼마나 요청하는지 정확히 추적 가능. "이 필드는 아무도 안 쓰니까 제거해도 되겠다" 같은 판단이 쉬워요.

### 그럼 왜 회사들이 GraphQL을 못 버리는가?

스크래퍼 입장에서 중요한 부분이에요. **회사들이 GraphQL을 갑자기 닫거나 바꾸기 어려운 이유**:

#### 1. 자기 사이트가 그걸로 동작 중

Best Buy 웹사이트 자체가 `/gateway/graphql` 호출로 데이터를 받아옴. **이걸 끄면 자기 웹사이트가 안 돌아감**.

우리가 호출하는 URL이 곧 그들 사이트가 호출하는 URL이라서, **막을 수 없어요**. (대신 봇 보호로 우회를 막는 거지, GraphQL 자체를 못 막음.)

#### 2. 모바일 앱도 같은 GraphQL 씀

웹사이트뿐 아니라 Best Buy 앱(iOS/Android)도 같은 GraphQL 서버를 호출해요. GraphQL을 바꾸면:
- 웹사이트 수정
- iOS 앱 업데이트 + 앱스토어 심사
- Android 앱 업데이트 + 플레이스토어 심사
- 그리고 **사용자들이 앱 업데이트하기 전까지** 구버전 호환 유지 필요

→ 한번 공개된 GraphQL은 **수년간 유지**되는 게 보통이에요.

#### 3. 외부 파트너/통합 시스템

대형 이커머스는 가격 비교 사이트, 광고 플랫폼, 재고 관리 시스템 등과 연동되어 있어요. API 바꾸면 다 깨짐. 변경하려면 모든 파트너 통보 + 마이그레이션 기간 부여.

#### 4. GraphQL의 버전 관리 철학

REST는 `/v1/`, `/v2/` 같이 버전을 명시적으로 나누기 쉬운데, GraphQL은 **필드를 추가/삭제(deprecated)** 하는 식으로 점진적으로 진화해요. 갑자기 큰 변화 안 함.

### 스크래퍼 입장에서 의미

✅ **좋은 소식**:
- 한번 잘 만들어두면 **수년간 동작**
- 갑자기 작동 안 하는 일 거의 없음
- 필드가 추가될 순 있어도 사라지는 건 보통 미리 deprecated 알림 후 6개월~1년 유예

⚠️ **주의할 점**:
- 회사가 봇 감지를 강화할 순 있음 (GraphQL은 그대로지만 우회가 어려워짐)
- 가끔 큰 리뉴얼 때 쿼리 이름이 바뀜 (`getProduct` → `productBySkuId` 등)
- 그래서 **Part 6.2의 쿼리 추출 방법을 익혀두는 게 중요**

GraphQL이 있는 사이트는 안정적으로 운영 가능한 좋은 타겟이에요. 우리가 Best Buy를 고른 것도 이런 이유 중 하나.

---

## 1.3 Best Buy는 어떻게 동작하나

### 핵심 식별자

- **SKU ID** (예: `6668565`): Best Buy의 개별 상품 고유 번호. 숫자 7~8자리.
- **BSIN** (예: `J39TC8JGZK`): 같은 모델의 변형들(색상, 용량)을 묶는 마스터 ID.

### GraphQL 엔드포인트 (요청 보내는 주소)

```
https://www.bestbuy.com/gateway/graphql
```

모든 요청은 이 주소로 **POST 방식**으로 보내요.

### 잠깐, GET이랑 POST가 뭐예요?

#### HTTP 메서드가 만들어진 이유

웹 초창기(1991년) 영국 CERN 연구소의 팀 버너스리가 HTTP를 만들 때, "**의도를 명확히 구분**하려고" 여러 메서드를 정의했어요.

문제 상황: 모든 요청이 똑같아 보이면 서버가 위험해요.
- 누군가 단순히 "주소 들어가봤을 뿐"인데
- 그게 데이터를 삭제하거나 결제하는 동작이면? → 큰 사고

그래서 의도별로 분리:

| 메서드 | 의도 | 사이드 이펙트 |
|---|---|---|
| GET | 데이터 **읽기** | 없음 (안전) |
| POST | 새로 **만들기** 또는 복잡한 작업 | 있음 |
| PUT | **수정** | 있음 |
| DELETE | **삭제** | 있음 |

규칙이 있으니까:
- 브라우저는 GET만 미리 prefetch해도 안전 (속도 빠름)
- 검색 엔진은 GET 페이지만 인덱싱
- 캐시 시스템은 GET 응답을 저장
- 백버튼 누를 때 GET은 자동 재실행, POST는 사용자에게 물음 ("재제출하시겠습니까?")

**HTTP 표준이 이걸 강제하는 게 아니라 약속**이에요. 다 같이 지키니까 웹이 안전하게 동작.

우리가 알아야 할 건 GET과 POST 두 개.

#### GET — 정보를 "받아오는" 요청

브라우저 주소창에 URL 치면 일어나는 게 바로 GET이에요.

```
GET https://www.bestbuy.com/site/searchpage.jsp?st=cellphone
                                                ▲
                                       파라미터를 URL에 붙임
```

특징:
- **데이터를 URL에 적어서 보냄** (`?key=value` 형식)
- 데이터 크기 제한 있음 (URL 길이 한계)
- 브라우저 주소창에 그대로 표시됨 → 비밀번호 같은 거 보내면 안 됨
- 결과를 받아오기만 함 (서버 상태 변경 X)

비유하자면 **편지 봉투에 안 적힌 외부 메모**예요. 우체부가 다 볼 수 있음.

#### POST — 정보를 "전달하면서 요청"하는 방식

긴 데이터나 복잡한 데이터를 보낼 때 써요.

```
POST https://www.bestbuy.com/gateway/graphql

요청 본문(body):
{
  "query": "{ product(skuId: \"6650408\") { 이름 가격 } }",
  "variables": { "skuId": "6650408" }
}
```

특징:
- **데이터를 요청 본문(body)에 담아 보냄** — URL은 깔끔
- 크기 제한 거의 없음 (긴 GraphQL 쿼리도 OK)
- URL에 안 보임 → 비밀번호, 큰 데이터 보낼 때 적합
- 서버에 뭔가 만들거나 처리 요청할 때도 씀 (가입, 결제 등)

비유하자면 **편지 봉투 안에 든 편지**예요. 우체부는 봉투만 보고 내용은 모름.

#### 우리가 POST를 쓰는 이유

GraphQL 쿼리는 **길고 복잡**해요. 변수도 dict 구조고요. URL에 다 못 적어요.

```
❌ GET으로 못 함:
   /graphql?query={product(skuId:"6650408"){이름 가격 customerReviews{...}}}
   → URL 너무 길고 특수문자 깨짐

✅ POST로:
   /graphql
   Body: {"query": "...", "variables": {...}}
   → 본문에 깔끔하게 담김
```

#### Python 코드로 보면

```python
import requests

# GET 요청 (URL에 파라미터)
r = requests.get("https://example.com/search", params={"q": "cellphone"})

# POST 요청 (body에 데이터)
r = requests.post("https://www.bestbuy.com/gateway/graphql",
                  json={"query": "...", "variables": {...}})
```

`requests.post()`에서 `json=` 파라미터에 dict를 넣으면 자동으로 JSON으로 변환해서 본문에 담아줘요. 우리가 만들 코드도 이걸 씁니다.

### 핵심 GraphQL 함수 3가지

이 3개만 알면 90%는 할 수 있어요:

| 함수 | 역할 | 입력 | 출력 |
|---|---|---|---|
| `search` | 검색 | 검색어, 페이지 번호, 필터 | 상품 리스트 (SKU + 기본정보) |
| `productBySkuId` | 상품 상세 | SKU ID | 이름, 가격, 스펙, 리뷰 등 모든 정보 |
| `recommendationsV2` | 추천 상품 | SKU ID + 추천 종류 | 비교/보완 추천 SKU 목록 |

---

## 1.4 ZenRows는 왜 필요한가 (요약)

Best Buy는 Akamai라는 봇 차단 시스템을 써요. 그냥 Python으로 요청하면 즉시 차단됨.

**ZenRows**는 이걸 우회해주는 유료 서비스예요.
- 진짜 Chrome처럼 위장한 요청
- 주거용 IP 사용
- Akamai 쿠키 챌린지 자동 해결

> 비용 계산과 절감 방법은 **Part 2에서 상세하게** 다룹니다. Best Buy 작업의 가장 중요한 부분이에요.

---
---

# Part 2. ZenRows와 비용 계산 ⭐

> **이 챕터를 안 읽으면 청구서 보고 놀랍니다.** 진지하게요.

## 2.1 왜 ZenRows를 써야 하는가

### 잠깐, 왜 봇 차단이라는 게 존재하지?

먼저 **봇 차단 시스템이 왜 만들어졌는지** 알아두면 ZenRows의 존재 이유가 더 명확해져요.

2000년대 초만 해도 웹은 상대적으로 자유로웠어요. 누구나 자유롭게 접근 가능. 근데 점점 문제들이 생겼어요:

1. **가격 정보 무단 수집**: 경쟁사가 매일 가격 크롤링해서 자동으로 1원씩 깎음
2. **재고 매점매석**: 봇이 콘서트 티켓, 신상 운동화를 1초 만에 다 사들임 (스니커즈, BTS 콘서트 사례)
3. **DDoS 같은 부하**: 봇 수천 개가 동시 호출 → 서버 다운
4. **계정 탈취 시도**: 비밀번호 무차별 대입 (brute force)
5. **콘텐츠 도용**: 뉴스 기사, 상품 사진 무단 복사

회사 입장에선 손해가 커요. **사람 손님은 받고, 봇은 막아야** 함.

이걸 해결하려고 **Akamai**, **Cloudflare**, **PerimeterX** 같은 봇 차단 회사들이 등장했어요. 이들은 수많은 사이트 트래픽을 학습해서 "봇 vs 사람" 패턴을 매우 정확히 구분해요.

→ **Akamai는 봇이라면 누구든 거의 다 잡아내요**. 그래서 우리도 차단당하는 거.

### Best Buy의 방어선

```
   우리 요청
      ↓
   [Akamai Bot Manager]   ← 여기서 봇 거른다
      ↓
   Best Buy 서버
      ↓
   응답
```

Akamai가 보는 것들:
1. **TLS fingerprint** — Python `requests`의 시그니처가 고유함 → 0.1초 만에 봇 판별
2. **IP 주소 평판** — AWS/GCP/Azure 같은 데이터센터 IP는 거의 즉시 차단
3. **쿠키 챌린지** — `_abck`, `bm_sz` 같은 쿠키를 JS로 풀어야 정상값 생성
4. **요청 빈도/패턴** — 사람은 1초에 GraphQL 10번 안 때림
5. **헤더 누락** — Chrome 전용 헤더(`sec-ch-ua` 등) 없으면 의심

### 그럼 ZenRows는 왜 만들어졌나?

봇 차단이 강해지자, "**합법적인 스크래핑 수요**"도 같이 커졌어요:
- 가격 비교 사이트 (소비자에게 좋은 서비스)
- 시장 조사 (학술, 비즈니스)
- SEO 분석 도구
- 자기 회사 가격을 경쟁사와 비교
- 모니터링/알림 서비스

이 합법적인 사용자들이 **Akamai를 매번 직접 우회하는 건 너무 어려워요**. 우회 기술이 빠르게 바뀌고, 한 명이 따라가기 힘듦.

그래서 **ZenRows** 같은 서비스가 등장했어요. 핵심 가치:
- "**복잡한 봇 우회는 우리가 다 처리할 테니, 당신은 데이터만 받아가세요**"
- 주거용 IP 풀 운영 (수백만 개)
- TLS 시그니처 Chrome처럼 위장
- Akamai 쿠키 챌린지 자동 해결
- 매일 업데이트되는 우회 기법

직접 우회 시스템 만들려면 풀타임 엔지니어 + 인프라 비용이 들어요. **ZenRows에 $69 내는 게 훨씬 싸요.** 이게 ZenRows의 존재 이유.

### 시도해본 사람의 검증

> **시나리오 A (그냥 Python `requests`)** → 즉시 403 차단됨. 이미 본인이 확인.

이게 ZenRows를 써야 하는 이유예요. 직접 우회는 시간만 잡아먹고 불안정해요.

## 2.2 ZenRows 대안: Proton VPN은 되는가?

**결론부터: 거의 안 됩니다.** 이유:

### Proton VPN의 한계

| 항목 | Proton VPN | ZenRows |
|---|---|---|
| **IP 종류** | 데이터센터 IP (Proton 서버) | 주거용 IP 풀 (수백만 개) |
| **Akamai 우회** | ❌ Proton IP 대부분 블랙리스트 | ✅ 자동 우회 |
| **TLS 시그니처** | ❌ Python requests 그대로 | ✅ Chrome 위장 |
| **쿠키 챌린지** | ❌ 직접 풀어야 함 | ✅ 자동 |
| **세션 관리** | ❌ 직접 | ✅ session_id로 |

### 직접 확인 방법

Proton VPN 켜고 EC2에서 다음 코드 돌려보세요:

```python
import requests
r = requests.get("https://www.bestbuy.com/site/searchpage.jsp?st=cellphone")
print(r.status_code)
print(r.text[:500])
```

**예상 결과**:
- `403 Forbidden` 또는
- 본문에 `"Reference #"`, `"Pardon Our Interruption"`, Akamai 챌린지 페이지

만약 가끔 200이 나오더라도, 5~10회 호출 후 차단됩니다. 운영 가능한 수준이 아니에요.

### 그럼 Proton VPN은 언제 쓰면 되나?

**봇 보호가 약한 사이트에는 충분히 쓸 만해요.** 비용 절감 효과 큼.

사이트별 Proton VPN 사용 가능 여부:

| 사이트 유형 | Proton VPN | ZenRows 필요? |
|---|---|---|
| **봇 보호 없는 사이트** (소규모 쇼핑몰, 블로그, 뉴스) | ✅ 충분 | ❌ |
| **약한 보호** (eBay, 일부 중소 이커머스) | ✅ 가능 (속도 조절 필요) | ❌ |
| **중간 보호** (일부 PerimeterX 사이트) | ⚠️ 일부 가능 | 권장 |
| **강한 보호 (Akamai)** — Best Buy, Walmart, Target 등 | ❌ 거의 안 됨 | ✅ 필수 |
| **자체 강력 보호** — Amazon | ❌ | ✅ 필수 |

### 비용 절감 전략

작업 대상 사이트별로 도구 분리:

1. **쉬운 사이트는 Proton VPN으로** → ZenRows 호출 수 절약
2. **Akamai/강력 보호 사이트만 ZenRows로** → 25,000회/월 한도를 진짜 필요한 곳에 사용

이렇게 하면 같은 $69/월로 훨씬 더 많은 작업이 가능해요.

### Proton VPN으로 사이트 테스트하는 법

새 사이트 작업 시작 전에 **항상** 이 테스트부터:

```python
import requests

def test_with_proton(url: str, num_tests: int = 10):
    """Proton VPN 켠 상태에서 사이트가 응답하는지 확인."""
    success = 0
    blocked = 0

    for i in range(num_tests):
        try:
            r = requests.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/124.0.0.0 Safari/537.36"
            })
            print(f"[{i+1}] HTTP {r.status_code}, {len(r.text)} bytes")

            if r.status_code == 200 and "Reference #" not in r.text[:1000]:
                success += 1
            else:
                blocked += 1
        except Exception as e:
            print(f"[{i+1}] Error: {e}")
            blocked += 1

    print(f"\n결과: 성공 {success}/{num_tests}, 차단 {blocked}/{num_tests}")
    if success == num_tests:
        print("✅ Proton VPN으로 충분! ZenRows 불필요.")
    elif success >= num_tests * 0.7:
        print("⚠️ 가끔 차단. 속도 조절하면 가능. 또는 ZenRows 고려.")
    else:
        print("❌ Proton VPN으로 안 됨. ZenRows 사용해야 함.")


# 사용 예
test_with_proton("https://target-site.com/category/...")
```

**규칙**: 10회 중 10회 성공해야 운영 가능. 1~2회만 실패해도 자동화 중 누적되면 큰 문제.

### Best Buy의 경우

Akamai 보호가 강력해서 **Proton VPN으로 거의 불가능**. ZenRows 비용은 어쩔 수 없는 투자비예요. 다만 다른 작업에는 Proton VPN을 적극 활용해서 전체 비용을 낮추세요.

## 2.3 ZenRows 호출 단위 이해하기

### 사용자의 현재 플랜 (Developer $69/월)

| 항목 | 한도 |
|---|---|
| **Universal Scraper API - basic results** | 250,000회/월 |
| **Universal Scraper API - protected results** | 10,000회/월 |
| **Scraping Browser / Residential Proxies** | 12.73 GB/월 |
| **동시 요청 수** | 20 |

### 핵심: 호출당 "배수"로 차감되는 시스템

ZenRows는 호출 1번이 옵션에 따라 **다른 비율**로 카운터에서 빠져요:

| 설정 | 비용 배수 | 같은 250K basic 풀로 가능한 호출 수 |
|---|---|---|
| Basic (아무 옵션 X) | 1× | 250,000회 |
| `js_render=true` | 5× | 50,000회 |
| `premium_proxy=true` | 10× | 25,000회 |
| **`js_render=true` + `premium_proxy=true`** | **25×** | **10,000회** ← protected |

즉 "basic 250K"와 "protected 10K"는 **같은 풀의 다른 환산값**이에요. 곱셈 비율에 따라 카운터가 다르게 표시되는 거예요.

### Best Buy는 어떤 호출이 되나?

Best Buy는 Akamai 봇 보호 → **premium_proxy 필수** (10×)
GraphQL이라 JS 불필요 → **js_render=false** (1×)

→ **합쳐서 10× 비용**. 250K ÷ 10 = **25,000회/월 가능**

만약 실수로 `js_render=true`까지 켜면:
→ **25× 비용**. 250K ÷ 25 = **10,000회/월로 감소** (2.5배 손해)

### 호출당 비용 (Best Buy 기준)

```
월 $69 ÷ 25,000회 = $0.00276/호출 (약 3.6원/호출)
```

> 위 표의 "protected 10K"는 **둘 다 켰을 때**라서 실제 우리는 그것보다 2.5배 여유가 있어요.

GB 트래픽도 별도로 차감되지만, GraphQL은 응답이 작아서 12.73GB 한도는 보통 호출 한도 도달 전엔 안 걸려요.

## 2.4 매번 호출하기 전 비용 계산하는 법

작업 시작 전에 **반드시** 이걸 계산하세요.

### 공식

```
필요한 호출 수 = (검색 페이지 수) + (검색 결과 SKU 수 ÷ chunk_size)
실제 한도 = 25,000회/월 (Best Buy의 경우, premium_proxy만 켰을 때)
```

### 예시 시나리오 1: 한 카테고리 가볍게 모니터링

- 검색어: "cellphone"
- 검색 1페이지 (96개)
- 그 중 상위 20개 상세 + 리뷰 + 비교 추천

| 단계 | 호출 수 |
|---|---|
| 검색 1페이지 | 1 |
| 20개 SKU → chunk_size=10 → 2 batch | 2 |
| **총** | **3회** |

→ 한 달 한도 25,000회 ÷ 3 = **약 8,300번 실행 가능**
→ 매시간 실행해도 한 달 약 720번 → **매우 여유 있음**

### 예시 시나리오 2: 전체 카테고리 크롤링

- 검색어: "cellphone"
- **모든 페이지** (numFound 6,000 → 96개씩 약 63페이지)
- 모든 SKU 상세 + 리뷰 + 비교 추천

| 단계 | 호출 수 |
|---|---|
| 검색 63페이지 | 63 |
| 6,000 SKU → chunk_size=10 → 600 batch | 600 |
| **총** | **663회** |

→ 한 달 한도 25,000 ÷ 663 = **약 37번 실행 가능**

⚠️ **하루 한 번 자동화면 OK (30회). 하지만 여유 별로 없음**.

### 예시 시나리오 3: 위험한 시나리오 ⚠️

- 5개 카테고리 (cellphone, laptop, tv, headphone, camera)
- 각 카테고리 전체 페이지 + 모든 상품 상세
- **하루 1회 자동화**

| 단계 | 호출 수 |
|---|---|
| 카테고리 × 5 × 평균 50페이지 | 250 |
| 평균 5,000 SKU × 5 카테고리 × chunk=10 | 2,500 |
| **하루 총** | **2,750회** |
| **한 달 총** | **82,500회** |

→ **한도 3.3배 초과**. 9일 만에 한도 소진. 추가 청구 발생.

## 2.5 비용 절감 6가지 원칙

### 1. `js_render=false` 무조건 사용

GraphQL POST는 JS 실행이 필요 없어요. ZenRows 가격 구조상:

| 설정 | 비용 배수 |
|---|---|
| Basic (아무것도 안 켬) | 1× |
| JS rendering 켬 | 5× |
| Premium proxies 켬 | 10× |
| **JS + Premium proxies 둘 다** | **25×** (Best Buy 같은 protected) |

Best Buy는 Akamai 우회용으로 `premium_proxy=true`가 필수예요 → 이미 10× 비용. 여기에 `js_render=true`까지 켜면 **25× = 2.5배 더 비싸짐**. GraphQL은 JS 불필요하니 절대 켜지 마세요.

### 2. Alias batch 활용

- 같은 함수든 다른 함수든 한 호출에 묶기
- Best Buy의 경우 한 호출에 SKU 10개 상세 + 비교추천 + 리뷰 한꺼번에 가능

### 3. chunk_size 최적화

| chunk_size | 호출 수 (100 SKU) | 비고 |
|---|---|---|
| 5 | 20회 | 안전, 호출 많음 |
| **10** | **10회** | **권장** |
| 15 | 7회 | 응답 큼 |
| 20+ | 5회 | 쿼리 길이 초과 위험 |

### 4. 중복 SKU 제거

```python
unique_skus = list(set(all_skus))  # 무조건 dedupe
```

### 5. 필드 최소화

응답이 작을수록 빠르고 GB 한도 절약. 안 쓸 필드는 쿼리에서 빼기.

### 6. 캐싱

- 변하지 않는 데이터(스펙, 설명)는 한 번 받으면 DB 저장
- 자주 변하는 것(가격, 재고)만 재호출

## 2.6 ZenRows 설정 검증하기 (꼭 한 번은!)

> ⚠️ **실제 사례**: 처음 시작할 때 `js_render=true` + `premium_proxy=true`로 설정해서 **25× 비용**으로 호출되고 있었음. 검증 후 `js_render=false`로 바꿔 **10× 비용**으로 절감 (호출당 60% 줄임).
>
> 누구나 할 수 있는 실수예요. ZenRows 공식 예제 코드가 보통 `js_render=true`로 되어 있거든요.

### 2.6.1 왜 검증이 필요한가

ZenRows 옵션을 잘못 설정하면 같은 호출이라도 **2.5배 비싸짐**. 대시보드 청구서 보고 놀라기 전에 한 번 검증해두면 안전.

검증해야 할 것들:
1. **현재 설정이 뭐로 되어 있나** (코드/환경변수 확인)
2. **호출 1번이 실제로 얼마 차감되나** (응답 헤더 확인)
3. **수정 후 정상 동작하나** (1페이지 테스트)
4. **얼마나 절감됐나** (수정 전/후 비교)

### 2.6.2 응답 헤더 `x-request-cost` 활용

ZenRows는 호출마다 **응답 헤더 `x-request-cost`** 에 차감 비용을 담아줘요. 이걸 코드에서 저장해두면 검증/모니터링 가능.

```python
response = requests.post(zenrows_url, ...)
cost = response.headers.get("x-request-cost", "")
print(f"이번 호출 비용: {cost}")
# 예: "0.0028" → 10× (js_render=false)
# 예: "0.0070" → 25× (js_render=true)
```

> 💡 **수치는 ZenRows 플랜과 설정에 따라 달라요.** 본인 호출의 절대값보다는 **수정 전/후 비교**가 의미 있어요. 같은 호출이 X였다가 X/2.5로 줄면 성공.

### 2.6.3 코드에 비용 추적 내장하기

호출마다 비용을 자동 저장하도록 모듈에 추가:

```python
# zenrows_client.py 안에서
def call_graphql(query, variables=None, session_id="bb1"):
    response = requests.post(
        ZENROWS_URL,
        params={
            "url": BESTBUY_GRAPHQL_URL,
            "apikey": ZENROWS_API_KEY,
            "premium_proxy": "true",
            "js_render": "false",     # ⚠️ 절대 true 금지
            "proxy_country": "us",
            "session_id": session_id,
        },
        headers={...},
        json={"query": query, "variables": variables or {}},
        timeout=60,
    )

    # ⭐ 비용 추적
    metadata = {
        "status_code": response.status_code,
        "x_request_cost": response.headers.get("x-request-cost", ""),
        "elapsed": response.elapsed.total_seconds(),
        "bytes": len(response.text),
    }

    # 호출 메타데이터를 파일에 누적
    log_call(metadata)

    response.raise_for_status()
    return response.json()["data"]
```

이렇게 해두면 매 실행마다 `total_x_request_cost`를 합산해서 보여줄 수 있어요.

### 2.6.4 검증 절차 (한 번만 해두면 끝)

**Step 1. 현재 설정 확인**

`.env` 또는 코드에서 다음 두 값을 찾으세요:
```bash
# 또는 코드의 params dict
js_render=?
premium_proxy=?
```

- 둘 다 `true` → ⚠️ **25× 비용 (최악)**
- premium_proxy만 `true` → ✅ **10× 비용 (정상)**

**Step 2. 1회 테스트 호출 (가장 작은 호출로)**

가장 가벼운 GraphQL 쿼리 1번 호출:

```python
# test_zenrows_cost.py
import requests
from config import ZENROWS_API_KEY

# 간단한 검색 호출 1번
response = requests.post(
    "https://api.zenrows.com/v1/",
    params={
        "url": "https://www.bestbuy.com/gateway/graphql",
        "apikey": ZENROWS_API_KEY,
        "premium_proxy": "true",
        "js_render": "false",     # ← 이 값 바꿔가며 테스트
        "proxy_country": "us",
    },
    headers={"Content-Type": "application/json"},
    json={
        "query": "{ search(input: {site: \"WWW\", queryType: \"SEARCH\", query: \"test\"}, pagination: {pageNumber: 1, offset: 1}) { numFound } }"
    },
    timeout=60,
)

print(f"Status: {response.status_code}")
print(f"Cost: {response.headers.get('x-request-cost')}")
print(f"Response: {response.text[:200]}")
```

**Step 3. 비교 테스트 (전/후)**

같은 호출을 두 가지 설정으로 비교:

```python
def test_cost(js_render: bool):
    response = requests.post(
        "https://api.zenrows.com/v1/",
        params={
            "url": "https://www.bestbuy.com/gateway/graphql",
            "apikey": ZENROWS_API_KEY,
            "premium_proxy": "true",
            "js_render": "true" if js_render else "false",
            "proxy_country": "us",
        },
        headers={"Content-Type": "application/json"},
        json={"query": "..."},
        timeout=60,
    )
    return {
        "js_render": js_render,
        "status": response.status_code,
        "cost": response.headers.get("x-request-cost"),
        "elapsed": response.elapsed.total_seconds(),
    }


# 두 가지 다 테스트
result_off = test_cost(js_render=False)
result_on = test_cost(js_render=True)

print("=== 비교 ===")
print(f"js_render=False: cost={result_off['cost']}, time={result_off['elapsed']:.1f}s")
print(f"js_render=True:  cost={result_on['cost']},  time={result_on['elapsed']:.1f}s")

# 비율 계산
try:
    ratio = float(result_on['cost']) / float(result_off['cost'])
    print(f"비용 차이: {ratio:.1f}배")
    if 2.0 < ratio < 3.0:
        print("✅ 예상대로 약 2.5배 차이 — js_render=False 사용해야 함")
except (ValueError, ZeroDivisionError):
    print("⚠️ 비용 헤더 파싱 실패")
```

→ 약 3 호출 소모 (테스트 비용은 무시할 만함). 한 번만 하면 평생 안전.

**Step 4. 정상 동작 확인**

비용 줄이는 것보다 더 중요한 건 **여전히 데이터를 잘 받아오는지**.

```python
# 작은 페이지로 풀 파이프라인 1회 테스트
result = run_full_pipeline(query="cellphone", top_n=5)

assert len(result["products"]) > 0, "❌ 상품 못 받음"
assert all(p["price"] for p in result["products"]), "❌ 가격 비어있음"
assert all(p["reviews"] for p in result["products"]), "❌ 리뷰 비어있음"
print("✅ js_render=false로도 모든 데이터 정상")
```

이거 통과하면 **그동안 25×로 헛돈 쓰던 거 끝**.

### 2.6.5 운영 중 비용 모니터링

매 실행마다 manifest 같은 파일에 비용 합계 기록:

```python
import json
from pathlib import Path

def save_run_manifest(run_dir: Path, calls_meta: list[dict]):
    total_cost = sum(
        float(call.get("x_request_cost") or 0)
        for call in calls_meta
    )
    manifest = {
        "run_timestamp": datetime.now().isoformat(),
        "total_calls": len(calls_meta),
        "total_x_request_cost": round(total_cost, 5),
        "calls": calls_meta,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )
    print(f"💰 이번 실행 총 비용: {total_cost:.4f}")
```

매일/매주 manifest 모아보면 사용량 추세 보임. 이상 증가 즉시 발견 가능.

### 2.6.6 환경변수로 옵션 토글 가능하게 (베스트 프랙티스)

설정을 코드에 박지 말고 환경변수로 제어:

```python
def zenrows_params():
    params = {"custom_headers": "true"}

    if os.getenv("BESTBUY_PREMIUM_PROXY", "1") in {"1", "true"}:
        params["premium_proxy"] = "true"
        params["proxy_country"] = "us"

    # ⚠️ 기본값을 "0"으로! (GraphQL은 JS 불필요)
    if os.getenv("BESTBUY_JS_RENDER", "0") in {"1", "true"}:
        params["js_render"] = "true"

    return params
```

장점:
- 코드 수정 없이 `.env` 파일로 실험 가능
- 다른 사이트 작업할 때 같은 코드 재사용
- AI한테 시킬 때 "환경변수 토글 가능하게 만들어줘"라고 한 마디만 더 추가

### 2.6.7 한 번 체크리스트 ⭐⭐⭐ (가장 중요)

> 🚨 **이 체크리스트 하나로 한 달에 수십만 원 차이 날 수 있어요.**
> 작업 시작하기 전, 그리고 새 기능 추가할 때마다 무조건 한 번 돌리세요.

| # | 체크 항목 | 안 했을 때 손해 |
|---|---|---|
| 1 | `js_render=false` 인가? | 호출당 **2.5배 더 비쌈** |
| 2 | `premium_proxy=true` 인가? | Akamai 즉시 차단 |
| 3 | 응답 헤더 `x-request-cost` 저장하나? | 비용 추적 불가능 |
| 4 | 비교 테스트 했나? (js on/off) | 어디가 새는지 모름 |
| 5 | 1페이지 테스트로 데이터 정상 수신? | 운영 시작 후 발견 |
| 6 | manifest 파일에 비용 합계 저장하나? | 일별 추세 모름 |
| 7 | 환경변수로 토글 가능한가? | 코드 수정 매번 필요 |

다 체크되면 안심하고 운영. **하나라도 빠지면 돈 새는 중.**

#### 🤖 AI한테 던질 체크리스트 검증 프롬프트

비전문가는 위 7개 항목을 코드에서 직접 확인하기 어려워요. **그냥 AI한테 이 프롬프트를 통째로 복붙하세요**:

```
내 프로젝트 코드를 검사해줘.
가이드 Part 2.6.7의 7가지 체크리스트를 하나씩 확인하고
체크 결과를 표로 보여줘.

확인할 것:
1. zenrows_client.py (또는 ZenRows 호출하는 모듈)에서 js_render가 false로
   설정되어 있는가? (true면 매우 큰 문제)
2. premium_proxy=true 설정되어 있는가?
3. 응답 헤더 x-request-cost를 어딘가 저장하고 있는가?
4. js_render true/false 비교 테스트 코드가 있는가? 없으면 만들어줘.
5. 작은 테스트 실행해서 데이터가 제대로 들어오는지 확인하는 코드가 있는가?
6. 호출 결과를 manifest.json 같은 파일에 비용과 함께 저장하는가?
7. js_render, premium_proxy 등 옵션을 환경변수(.env)로 토글 가능한가?

각 항목에 대해:
- ✅ 통과 / ❌ 실패 / ⚠️ 부분 통과 표시
- 실패한 것은 코드 어디를 어떻게 고쳐야 하는지 구체적으로 알려줘
- 가장 위험한 것부터 우선순위 매겨서

마지막에 "지금 운영 시작해도 안전한가?" 한 줄 결론 줘.
```

이 프롬프트만 던지면 AI가 알아서:
- 코드 스캔
- 7개 항목 확인
- 위험도 평가
- 수정 방법 제시

까지 다 해줘요. **체크리스트 통과 못하면 절대 운영 시작하지 마세요.**

#### 추가: 매주 1회 점검 프롬프트

운영 시작 후에도 정기 점검 권장:

```
지난 일주일치 manifest.json 파일들을 모아서 분석해줘:
- 일별 총 호출 수와 비용 추세
- x-request-cost 평균값 (이상 증가 있는지)
- 한 달 한도(25,000회) 대비 현재 사용량 %
- 다음 주 예상 사용량 (이번 주 추세 기반)

이상 패턴 발견되면 (예: js_render 갑자기 켜진 흔적) 즉시 보고해줘.
```

---

## 2.7 호출 수 사전 추정 코드

작업 시작 전 호출 수 미리 계산하기:

```python
# Best Buy 기준 (premium_proxy=true, js_render=false)
MONTHLY_LIMIT = 25_000  # 호출/월
COST_PER_CALL = 69 / MONTHLY_LIMIT  # ≈ $0.00276


def estimate_cost(num_search_pages: int, num_skus: int,
                 chunk_size: int = 10):
    """ZenRows 호출 수와 비용 추정 (Best Buy 기준)."""
    search_calls = num_search_pages
    detail_calls = -(-num_skus // chunk_size)  # 올림 나눗셈
    total = search_calls + detail_calls

    cost_usd = total * COST_PER_CALL
    cost_krw = cost_usd * 1300  # 환율 가정

    print(f"검색 페이지 호출: {search_calls}회")
    print(f"상세 batch 호출: {detail_calls}회 (chunk_size={chunk_size})")
    print(f"총 호출 수: {total}회")
    print(f"한 달 한도({MONTHLY_LIMIT:,}회) 중 사용 비율: {total/MONTHLY_LIMIT*100:.1f}%")
    print(f"예상 비용: ${cost_usd:.4f} (약 {cost_krw:.0f}원)")
    print(f"이 작업 한 달에 몇 번 가능: {MONTHLY_LIMIT // total}회")

    if total > MONTHLY_LIMIT:
        print(f"⚠️ 경고: 한 달 한도 초과! {total - MONTHLY_LIMIT}회 초과분 추가 청구")
    elif total > MONTHLY_LIMIT * 0.5:
        print(f"⚠️ 주의: 한 달 한도의 50% 이상 한 번에 사용")

    return total


# 사용
estimate_cost(num_search_pages=1, num_skus=20)
# → 3회. 한도의 0.01%. 매우 안전.

estimate_cost(num_search_pages=63, num_skus=6000)
# → 663회. 한도의 2.7%. 월 37번 가능.

estimate_cost(num_search_pages=250, num_skus=25000)
# → 2,750회. 한도의 11%. 월 9번 가능. ⚠️ 매일은 초과.
```

**모든 신규 작업 시작 전에 이 함수 먼저 돌리세요.** 진심이에요.

---
---

# Part 3. 시스템 설계

## 3.1 전체 아키텍처 한 장 그림

```
┌──────────────────────────────────────────────────────────────────┐
│                         사용자 입력                                │
│              (예: 검색어 "cellphone", 페이지 수 5)                 │
└────────────────────────────────┬─────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  [Step 1] 검색으로 SKU 수집                                       │
│  GraphQL: search(query: "cellphone", pageNumber: 1~5)            │
│  → SKU 리스트 (페이지당 24~96개) + 기본정보                       │
└────────────────────────────────┬─────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────┐
│  [Step 2] 상세 + 리뷰 + 비교추천 ⭐ 한 호출에 다 묶기              │
│  GraphQL: alias batch로                                          │
│     - productBySkuId × N         (상세 + 리뷰 20개)               │
│     - recommendationsV2 × N      (비교 추천 SKU 목록)             │
│  → 한 호출에 SKU N개의 모든 데이터                                │
└────────────────────────────────┬─────────────────────────────────┘
                                 ↓
                          저장 (JSON/DB)
```

**핵심**: GraphQL은 다른 함수들도 한 요청에 묶을 수 있어요.
`productBySkuId`(상세 + 리뷰)와 `recommendationsV2`(비교 추천)는 별개의 함수지만
alias로 묶으면 **한 번의 ZenRows 호출**에 둘 다 들어와요.

---

## 3.2 데이터 흐름: 단계별 상세

### Step 1. 검색 → SKU 수집

**입력**: `"cellphone"`, page 1
**호출**: GraphQL `search`
**출력**:
```json
{
  "numFound": 6000,
  "documents": [
    { "skuId": "6650408", "name": "Samsung Galaxy S26", "price": 799.99, ... },
    { "skuId": "6665488", "name": "Google Pixel 10", ... },
    ... 24~96개
  ]
}
```

### Step 2. 풀 데이터 한 방에

검색 결과로 얻은 SKU들에 대해 **상세 + 리뷰 20개 + 비교 추천**을 한 호출에 묶어서 가져옴.

**입력**: `["6650408", "6665488", "12582364", ...]` (10개씩 chunk)
**호출**: GraphQL alias batch (chunk당 1회)

쿼리 모양:
```graphql
query Combined($site: String!, $storeId: String!) {
  # 상품 1: 상세 + 리뷰
  p_6650408: productBySkuId(skuId: "6650408") {
    skuId
    name { short }
    price(input: { salesChannel: "LargeView" }) { customerPrice regularPrice }
    customerReviews { averageRating reviewCount }
    specificationGroups { ... }
    reviews(filter: { pageSize: 20 }) {
      results { rating title text userNickname submissionTime }
    }
  }
  # 상품 1: 비교 추천 SKU 목록
  c_6650408: recommendationsV2(input: {
    placement: "pdp-compare-mp", site: $site,
    skus: ["6650408"], storeIds: [$storeId]
  }) { subPlacements { recommendations { id } } }

  # 상품 2도 똑같이 묶기...
  p_6665488: productBySkuId(skuId: "6665488") { ... }
  c_6665488: recommendationsV2(...) { ... }
}
```

**출력**:
- `data.p_6650408` → 상품 1의 상세 + 리뷰 20개
- `data.c_6650408` → 상품 1의 비교 추천 SKU 10개 (ID만)
- (각 SKU마다 반복)

> ℹ️ 비교 추천 상품들의 상세 정보는 **이번에는 안 가져옴**.
> SKU 목록만 받아서 저장. 필요하면 나중에 별도로 가져오기.

---

## 3.3 호출 수 요약 (자세한 계산은 Part 2 참고)

**예시 시나리오**: 검색 "cellphone"으로 상위 50개 상품 + 각각의 상세 + 리뷰 20개 + 비교 추천 SKU 목록

| Step | 호출 수 |
|---|---|
| 1. 검색 (96개씩 1페이지) | 1 |
| 2. 상세+리뷰+비교추천 batch (50개, 10개씩) | 5 |
| **총** | **6회** |

→ 한 달 한도(25,000회)의 **0.02%**. 같은 작업 매시간 자동화해도 안전.

### chunk_size 선택 가이드

| chunk_size | 한 쿼리에 들어가는 alias 수 | 장단점 |
|---|---|---|
| 5 | 5 상품 × 2 함수 = 10 alias | 안전, 호출 많아짐 |
| **10** | 10 상품 × 2 함수 = 20 alias | **권장** |
| 15 | 15 상품 × 2 함수 = 30 alias | 호출 적지만 응답 큼 |
| 20+ | 40+ alias | 쿼리 길이 초과 위험 |

---

## 3.4 모듈 구조

코드는 기능별로 나눠서 만들어요. 아래는 **시작용 예시 구조**예요. 필요에 따라 모듈은 더 추가될 수 있어요.

### 시작 예시

```
bestbuy_scraper/
├── config.py              # ZenRows API 키, 기본 설정
├── zenrows_client.py      # ZenRows로 HTTP 요청 보내는 모듈
├── graphql_queries.py     # GraphQL 쿼리 문자열 모음
├── search.py              # Step 1: 검색 → SKU 수집
├── product_detail.py      # Step 2: 상세 + 리뷰 + 비교추천 (한방에)
├── pipeline.py            # Step 1~2 조합한 메인 파이프라인
└── main.py                # 실행 진입점
```

각 파일이 한 가지 일만 하니까 AI한테 시키기 쉬워요.

### 나중에 추가될 수 있는 모듈들

기능이 늘어나면 이런 모듈들이 추가돼요:

```
bestbuy_scraper/
├── ... (위의 기본 파일들)
├── storage.py             # 결과를 DB/파일에 저장
├── sponsored_enrichment.py # 광고 SKU 부족 정보 보강
├── deduplication.py       # 중복 SKU 제거
├── cost_estimator.py      # 호출 수 사전 계산
├── retry_handler.py       # 차단/실패 시 재시도 로직
├── proton_vpn_client.py   # Proton VPN 호출 (쉬운 사이트용)
├── scheduler.py           # 정기 실행
├── notifier.py            # Slack/이메일 알림
├── analyzer.py            # 수집 데이터 분석
└── tests/                 # 테스트 코드
    ├── test_search.py
    └── test_product_detail.py
```

> **모듈 추가/수정/디버깅은 모두 Part 5의 프롬프트 템플릿으로 처리해요.** AI한테 어떻게 요청할지 정리해뒀어요.

---
---

# Part 4. 구현 (AI에게 시킬 모듈들)

> 각 섹션이 **하나의 작업 단위**예요. Claude Code에 이 섹션 하나씩 던지면 됩니다.

## 4.1 환경 설정

> **EC2 Windows에서 작업하시면 Part 7 먼저 보세요.** 여기는 기본만 설명.

### 필요한 것

- Python 3.10 이상
- ZenRows 계정 + API 키 ([https://www.zenrows.com](https://www.zenrows.com))
- 라이브러리: `requests`, `python-dotenv`

### 설치

```bash
pip install requests python-dotenv
```

### `.env` 파일 만들기 (프로젝트 루트에)

```
ZENROWS_API_KEY=여기에_API_키_붙여넣기
```

### `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

# ZenRows
ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY")
ZENROWS_URL = "https://api.zenrows.com/v1/"

# Best Buy
BESTBUY_GRAPHQL_URL = "https://www.bestbuy.com/gateway/graphql"
DEFAULT_ZIP_CODE = "10001"      # 뉴욕 (가격 기준 위치)
DEFAULT_STORE_ID = "60"         # 가까운 매장
DEFAULT_SALES_CHANNEL = "LargeView"  # 데스크탑 가격

# 호출 설정
DEFAULT_TIMEOUT = 60
RATE_LIMIT_SECONDS = 1.5         # 호출 사이 대기
```

---

## 4.2 모듈 1: ZenRows 호출기

**역할**: Best Buy에 GraphQL POST를 보내는 단일 함수. 모든 호출이 이걸 통과해요.

### `zenrows_client.py`

```python
import json
import time
import requests
from config import (
    ZENROWS_API_KEY, ZENROWS_URL, BESTBUY_GRAPHQL_URL,
    DEFAULT_TIMEOUT, RATE_LIMIT_SECONDS
)


class ZenRowsError(Exception):
    """ZenRows 또는 Best Buy 응답 에러"""
    pass


def call_graphql(query: str, variables: dict = None, session_id: str = "bb1") -> dict:
    """
    ZenRows를 통해 Best Buy GraphQL에 요청을 보낸다.

    Args:
        query: GraphQL 쿼리 문자열
        variables: 쿼리에 들어갈 변수 dict
        session_id: ZenRows 세션 ID (같은 값 쓰면 쿠키 재사용)

    Returns:
        응답의 'data' 필드 (dict)

    Raises:
        ZenRowsError: HTTP 에러, 차단, GraphQL 에러 등
    """
    body = json.dumps({
        "query": query,
        "variables": variables or {}
    })

    # ZenRows 파라미터
    params = {
        "url": BESTBUY_GRAPHQL_URL,
        "apikey": ZENROWS_API_KEY,
        "premium_proxy": "true",
        "js_render": "false",       # GraphQL은 JS 불필요!
        "proxy_country": "us",
        "session_id": session_id,
        "custom_headers": "true",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        # ZenRows POST body 전달 (플랜에 따라 헤더명 확인 필요)
        "Zr-Body": body,
    }

    try:
        r = requests.post(
            ZENROWS_URL,
            params=params,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as e:
        raise ZenRowsError(f"Network error: {e}")

    # HTTP 상태 체크
    if r.status_code != 200:
        raise ZenRowsError(f"HTTP {r.status_code}: {r.text[:300]}")

    # JSON 파싱
    try:
        payload = r.json()
    except ValueError:
        # JSON이 아니면 차단 페이지일 가능성
        raise ZenRowsError(f"Non-JSON response (blocked?): {r.text[:300]}")

    # GraphQL 에러 체크
    if "errors" in payload and not payload.get("data"):
        raise ZenRowsError(f"GraphQL errors: {payload['errors']}")

    # 레이트 리미트 (다음 호출 전 대기)
    time.sleep(RATE_LIMIT_SECONDS)

    return payload.get("data", {})
```

### AI에게 시킬 때 프롬프트 예시

```
config.py를 참고해서 zenrows_client.py를 만들어줘.
call_graphql(query, variables, session_id) 함수 하나만 노출하고,
- ZenRows를 통해 Best Buy GraphQL 엔드포인트에 POST 요청
- 응답 검증 (HTTP status, JSON, GraphQL errors)
- 차단/네트워크 에러는 ZenRowsError로 변환
- 호출 후 RATE_LIMIT_SECONDS만큼 sleep
이렇게 구현해줘.
```

---

## 4.3 모듈 2: GraphQL 쿼리 빌더

**역할**: GraphQL 쿼리 문자열을 한 곳에 모아둠. 나중에 필드 추가/변경하기 쉬워요.

### `graphql_queries.py`

```python
"""GraphQL 쿼리 문자열 모음.

각 쿼리는 함수로 감싸서, 동적으로 만들어야 하는 부분(예: alias batch)을 처리.
"""


# ─────────── 검색 쿼리 ───────────

SEARCH_QUERY = """
query Search(
  $input: SearchInput!,
  $pagination: SearchPagination!,
  $filter: SearchFilter,
  $sort: SearchSort,
  $productPriceInput: ProductItemPriceInput!
) {
  search(input: $input, pagination: $pagination, filter: $filter, sort: $sort) {
    numFound
    documents {
      ... on SearchProduct {
        product {
          skuId
          bsin
          name { short }
          url { pdp }
          primaryImage { piscesHref altText }
          manufacturer { modelNumber }
          reviewInfo { averageRating reviewCount }
          price(input: $productPriceInput) {
            customerPrice
            regularPrice
          }
        }
      }
    }
  }
}
"""


def build_search_variables(query: str, page: int = 1, per_page: int = 96,
                          sort: str = "Best-Match",
                          zip_code: str = "10001", store_id: str = "60"):
    """검색 쿼리에 들어갈 변수 dict 생성."""
    return {
        "input": {
            "site": "WWW",
            "queryType": "SEARCH",
            "query": query
        },
        "pagination": {
            "pageNumber": page,
            "offset": per_page
        },
        "filter": {
            "enableMarketplace": True,
            "facets": [],
            "deviceClass": "l",
            "removeCombos": False,
            "availability": {
                "inventoryType": "storepickup,instore",
                "zipCode": zip_code,
                "preferredStore": store_id,
                "availableStoresList": store_id
            },
            "collapse": True,
            "autoFacet": True
        },
        "sort": {
            "value": sort,
            "displayName": sort.replace("-", " ")
        },
        "productPriceInput": {
            "salesChannel": "LargeView"
        }
    }


# ─────────── 상품 상세 (단건) ───────────

PRODUCT_DETAIL_QUERY = """
query ProductDetail($skuId: String!) {
  product: productBySkuId(skuId: $skuId) {
    skuId
    name { short long }
    brand
    url { pdp }
    images { piscesHref altText }
    primaryImage { piscesHref altText }
    price(input: { salesChannel: "LargeView" }) {
      customerPrice
      regularPrice
    }
    customerReviews {
      averageRating
      reviewCount
    }
    specificationGroups {
      name
      specifications { displayName value definition }
    }
    description { short long }

    # 리뷰 본문 20개
    reviews(filter: { pageSize: 20 }) {
      results {
        rating
        title
        text
        userNickname
        submissionTime
      }
    }
  }
}
"""


# ─────────── ⭐ 통합 Batch 쿼리 (상세+리뷰+비교추천) ───────────

def build_combined_batch_query(sku_ids: list[str], review_count: int = 20) -> str:
    """
    여러 SKU에 대해:
      - 상품 상세
      - 리뷰 N개
      - 비교 추천 SKU 목록
    셋 다 한 번의 호출에 가져오는 alias batch 쿼리 생성.

    Args:
        sku_ids: SKU ID 리스트
        review_count: 각 상품의 리뷰 몇 개 가져올지 (기본 20)
    """
    # 상품 alias (p_SKU)
    product_aliases = "\n".join([
        f'  p_{sku}: productBySkuId(skuId: "{sku}") {{ ...ProductFields }}'
        for sku in sku_ids
    ])

    # 비교 추천 alias (c_SKU)
    compare_aliases = "\n".join([
        f"""  c_{sku}: recommendationsV2(input: {{
    placement: "pdp-compare-mp"
    site: $site
    skus: ["{sku}"]
    storeIds: [$storeId]
  }}) {{ subPlacements {{ recommendations {{ id }} }} }}"""
        for sku in sku_ids
    ])

    return f"""
query CombinedBatch($site: String!, $storeId: String!) {{
{product_aliases}
{compare_aliases}
}}
fragment ProductFields on Product {{
  skuId
  name {{ short }}
  brand
  url {{ pdp }}
  primaryImage {{ piscesHref altText }}
  price(input: {{ salesChannel: "LargeView" }}) {{
    customerPrice
    regularPrice
  }}
  customerReviews {{ averageRating reviewCount }}
  specificationGroups {{
    name
    specifications {{ displayName value }}
  }}
  reviews(filter: {{ pageSize: {review_count} }}) {{
    results {{
      rating
      title
      text
      userNickname
      submissionTime
    }}
  }}
}}
"""
```

> 💡 **여기가 가장 중요한 부분이에요.** 한 쿼리 안에:
> - `p_SKU` (productBySkuId) → 상세 + 리뷰 20개
> - `c_SKU` (recommendationsV2) → 비교 추천 SKU 목록
>
> 두 종류의 함수가 alias로 묶여서 **한 요청에** 전달됨.

---

## 4.4 모듈 3: 검색 (SKU 수집)

**역할**: 검색어와 페이지 수 받아서 SKU 리스트 + 기본정보 반환.

### `search.py`

```python
from zenrows_client import call_graphql
from graphql_queries import SEARCH_QUERY, build_search_variables


def search_products(query: str, page: int = 1, per_page: int = 96,
                   sort: str = "Best-Match") -> dict:
    """
    검색어로 상품 리스트를 가져온다.

    Returns:
        {
            "numFound": 6000,
            "products": [
                {"skuId": "...", "name": "...", "price": ..., ...},
                ...
            ]
        }
    """
    variables = build_search_variables(query, page, per_page, sort)
    data = call_graphql(SEARCH_QUERY, variables)

    search_result = data.get("search", {})
    documents = search_result.get("documents", [])

    products = []
    for doc in documents:
        product = doc.get("product")
        if not product:
            continue
        products.append({
            "skuId": product.get("skuId"),
            "bsin": product.get("bsin"),
            "name": (product.get("name") or {}).get("short"),
            "url": "https://www.bestbuy.com" + (product.get("url") or {}).get("pdp", ""),
            "image": (product.get("primaryImage") or {}).get("piscesHref"),
            "model": (product.get("manufacturer") or {}).get("modelNumber"),
            "rating": (product.get("reviewInfo") or {}).get("averageRating"),
            "reviewCount": (product.get("reviewInfo") or {}).get("reviewCount"),
            "price": (product.get("price") or {}).get("customerPrice"),
            "regularPrice": (product.get("price") or {}).get("regularPrice"),
        })

    return {
        "numFound": search_result.get("numFound", 0),
        "products": products,
    }


def search_all_pages(query: str, max_pages: int = 5, per_page: int = 96) -> list[dict]:
    """여러 페이지의 검색 결과를 합쳐서 반환."""
    all_products = []
    for page in range(1, max_pages + 1):
        result = search_products(query, page, per_page)
        all_products.extend(result["products"])
        if len(result["products"]) < per_page:
            break  # 마지막 페이지
    return all_products
```

---

## 4.5 모듈 4: 상품 상세 + 리뷰 + 비교 추천 (한 방에)

**역할**: SKU 리스트 받아서 한 번의 batch 호출로 **상세 + 리뷰 20개 + 비교 추천 SKU 목록**을 모두 가져옴.

### `product_detail.py`

```python
from zenrows_client import call_graphql
from graphql_queries import build_combined_batch_query


def get_full_details(sku_ids: list[str], chunk_size: int = 10,
                    store_id: str = "60", review_count: int = 20) -> dict:
    """
    여러 SKU에 대해 상세 + 리뷰 + 비교추천을 한방에 가져온다.

    Args:
        sku_ids: SKU ID 리스트
        chunk_size: 한 번에 묶을 SKU 개수
        store_id: 매장 ID (가격/재고 기준)
        review_count: 각 상품의 리뷰 몇 개 가져올지

    Returns:
        {
            "products": {sku_id: {...상세+리뷰...}, ...},
            "compare_map": {sku_id: [추천 SKU 리스트], ...}
        }
    """
    all_products = {}
    compare_map = {}

    for i in range(0, len(sku_ids), chunk_size):
        chunk = sku_ids[i:i + chunk_size]
        query = build_combined_batch_query(chunk, review_count=review_count)

        data = call_graphql(query, {
            "site": "dotcom-l",
            "storeId": store_id,
        })

        # 상품 상세 + 리뷰 파싱 (p_SKU)
        for sku in chunk:
            product = data.get(f"p_{sku}")
            if product:
                all_products[sku] = normalize_product(product)

            # 비교 추천 파싱 (c_SKU)
            compare = data.get(f"c_{sku}") or {}
            subs = compare.get("subPlacements") or []
            if subs:
                compare_map[sku] = [
                    rec["id"] for rec in subs[0].get("recommendations", [])
                ]
            else:
                compare_map[sku] = []

    return {
        "products": all_products,
        "compare_map": compare_map,
    }


def normalize_product(product: dict) -> dict:
    """GraphQL 응답을 평평한 형태로 정리."""
    reviews_raw = (product.get("reviews") or {}).get("results") or []
    reviews = [
        {
            "rating": r.get("rating"),
            "title": r.get("title"),
            "text": r.get("text"),
            "user": r.get("userNickname"),
            "date": r.get("submissionTime"),
        }
        for r in reviews_raw
    ]

    return {
        "skuId": product.get("skuId"),
        "name": (product.get("name") or {}).get("short"),
        "brand": product.get("brand"),
        "url": "https://www.bestbuy.com" + (product.get("url") or {}).get("pdp", ""),
        "image": (product.get("primaryImage") or {}).get("piscesHref"),
        "price": (product.get("price") or {}).get("customerPrice"),
        "regularPrice": (product.get("price") or {}).get("regularPrice"),
        "rating": (product.get("customerReviews") or {}).get("averageRating"),
        "reviewCount": (product.get("customerReviews") or {}).get("reviewCount"),
        "specs": flatten_specs(product.get("specificationGroups") or []),
        "reviews": reviews,  # 리뷰 20개
    }


def flatten_specs(spec_groups: list[dict]) -> dict:
    """스펙 그룹들을 평평한 {이름: 값} dict로."""
    flat = {}
    for group in spec_groups:
        for spec in group.get("specifications") or []:
            flat[spec["displayName"]] = spec["value"]
    return flat
```

### 사용 예시

```python
from product_detail import get_full_details

result = get_full_details(["6650408", "6665488", "12582364"])

# 상품 1의 상세 + 리뷰
product = result["products"]["6650408"]
print(product["name"])         # "Samsung Galaxy S26"
print(product["price"])         # 799.99
print(len(product["reviews"]))  # 20

# 상품 1의 비교 추천 SKU
recommended = result["compare_map"]["6650408"]
print(recommended)  # ["12117681", "12499748", ...]
```

---

## 4.6 모듈 5: 파이프라인 + 저장

**역할**: 위 모듈들을 조합해서 전체 워크플로우 실행.

### `pipeline.py`

```python
import json
from datetime import datetime
from search import search_products
from product_detail import get_full_details


def run_full_pipeline(query: str, top_n: int = 50,
                     review_count: int = 20) -> dict:
    """
    검색어 받아서 전체 파이프라인 실행.

    Args:
        query: 검색어 (예: "cellphone")
        top_n: 검색 결과 상위 몇 개를 상세 조회할지
        review_count: 각 상품의 리뷰 몇 개 수집할지

    Returns:
        {
            "query": "cellphone",
            "timestamp": "2025-...",
            "numFound": 6000,
            "products": [
                {
                    "skuId": "...",
                    "name": "...",
                    "price": ...,
                    "specs": {...},
                    "reviews": [...20개...],
                },
                ...
            ],
            "compare_map": {
                "6650408": ["12117681", "12499748", ...],
                ...
            }
        }
    """
    # ───── Step 1: 검색 ─────
    print(f"[1/2] '{query}' 검색 중...")
    search_result = search_products(query, page=1, per_page=96)
    print(f"     → {search_result['numFound']:,}개 검색됨, "
          f"{len(search_result['products'])}개 페이지 결과 수집")

    top_skus = [p["skuId"] for p in search_result["products"][:top_n]]

    # ───── Step 2: 상세 + 리뷰 + 비교추천 한방에 ─────
    print(f"[2/2] 상위 {len(top_skus)}개의 상세+리뷰+비교추천 수집 중...")
    full = get_full_details(top_skus, review_count=review_count)
    print(f"     → 상품 {len(full['products'])}개 (리뷰 포함), "
          f"비교추천 매핑 {len(full['compare_map'])}개 완료")

    return {
        "query": query,
        "timestamp": datetime.utcnow().isoformat(),
        "numFound": search_result["numFound"],
        "products": list(full["products"].values()),
        "compare_map": full["compare_map"],
    }


def save_to_json(data: dict, filename: str = None):
    """결과를 JSON 파일로 저장."""
    if not filename:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"bestbuy_{data['query']}_{ts}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"💾 저장됨: {filename}")
    return filename
```

### `main.py`

```python
from pipeline import run_full_pipeline, save_to_json


if __name__ == "__main__":
    result = run_full_pipeline(
        query="cellphone",
        top_n=20,         # 검색 상위 20개
        review_count=20,  # 각 상품 리뷰 20개
    )
    save_to_json(result)

    # 결과 요약
    print(f"\n=== 수집 결과 ===")
    print(f"검색어: {result['query']}")
    print(f"전체 검색 결과: {result['numFound']:,}개")
    print(f"수집 상품: {len(result['products'])}개")
    print(f"총 리뷰 수: {sum(len(p['reviews']) for p in result['products'])}")
    print(f"비교 추천 매핑: {len(result['compare_map'])}개")
```

---
---

# Part 5. AI에게 작업 시키는 법

## 5.1 프롬프트 작성 황금 규칙

AI에게 작업 시킬 때 효과적인 프롬프트의 공통점:

1. **참고할 가이드 섹션 명시** — `"가이드 Part 4.5 보고..."`
2. **현재 상황 설명** — 무슨 모듈/파일이 있고 뭐가 안 되는지
3. **원하는 결과 구체적으로** — 입력/출력, 함수 시그니처, 어디에 저장
4. **제약 조건** — 비용/시간/외부 의존성
5. **검증 방법** — 어떻게 동작 확인할지

**나쁜 프롬프트**:
> "스크래퍼 만들어줘"

**좋은 프롬프트**:
> "가이드 Part 4.4 보고 search.py 만들어줘. zenrows_client.py와 graphql_queries.py를 import해서 사용하고, search_products(query, page, per_page) 함수로 노출. 결과 확인은 top_n=5로 'iphone 15' 검색해서 SKU 5개 받아지면 성공."

이 차이가 결과 품질의 90%를 결정해요.

---

## 5.2 시작 단계 프롬프트

처음 프로젝트를 만들 때 순서대로 던지세요.

### 5.2.1 프로젝트 초기 설정

```
이 가이드(bestbuy_graphql_guide.md)를 처음 읽었어. EC2 Windows 환경에서
시작하려고 해.

다음 작업 해줘:
1. Part 4.1과 Part 7 보고 프로젝트 디렉터리 만들기
2. config.py와 .env.example 만들기
3. 가상환경 설정 + requests, python-dotenv 설치 명령어 알려주기
4. ZenRows API 키 동작 확인용 짧은 테스트 스크립트도 같이

EC2 Windows 기준으로 PowerShell 명령어로 알려줘.
```

### 5.2.2 ZenRows 호출 모듈

```
가이드 Part 4.2와 Part 2.6 보고 zenrows_client.py 만들어줘.

요구사항:
- call_graphql(query, variables, session_id) 함수 하나만 노출
- premium_proxy=true, js_render=false 기본값 (둘 다 환경변수로 토글 가능)
- 응답 헤더의 x-request-cost를 메타데이터에 저장
- 차단/네트워크 에러는 ZenRowsError 예외로 변환
- 호출 후 RATE_LIMIT_SECONDS만큼 sleep

만든 후 간단한 테스트: GraphQL 핑 쿼리 1번 호출해서
응답 status_code와 x-request-cost 출력하기.
```

### 5.2.3 GraphQL 쿼리 빌더

```
가이드 Part 4.3 보고 graphql_queries.py 만들어줘.

포함할 것:
- SEARCH_QUERY 문자열 + build_search_variables(query, page, per_page) 함수
- PRODUCT_DETAIL_QUERY (단건용)
- build_combined_batch_query(sku_ids, review_count) — alias batch (핵심)

특히 build_combined_batch_query는 한 호출에:
- productBySkuId (상세 + 리뷰 N개)
- recommendationsV2 (비교 추천 SKU 목록)
둘 다 묶어서 보내야 해. 가이드 Part 4.3의 코드 그대로 따라가도 돼.
```

### 5.2.4 검색 모듈

```
가이드 Part 4.4 보고 search.py 만들어줘.

요구사항:
- search_products(query, page, per_page, sort) → 1페이지 결과
- search_all_pages(query, max_pages) → 여러 페이지 합쳐서 반환
- 반환값은 {"numFound": N, "products": [...]} 형식

테스트: "iphone 15" 1페이지 받아서 numFound와 products 개수 출력.
```

### 5.2.5 통합 상세 모듈 (가장 중요)

```
가이드 Part 4.5 보고 product_detail.py 만들어줘.

요구사항:
- get_full_details(sku_ids, chunk_size=10) 함수
- 한 호출에 상세 + 리뷰 20개 + 비교추천 다 가져오기
- chunk_size씩 나눠서 alias batch로
- 반환: {"products": {sku: {...}}, "compare_map": {sku: [sku들]}}

테스트: SKU 3개로 호출해서 각 상품에 reviews 20개 있는지,
compare_map에 추천 SKU 10개씩 있는지 확인.
```

### 5.2.6 파이프라인

```
가이드 Part 4.6 보고 pipeline.py와 main.py 만들어줘.

요구사항:
- run_full_pipeline(query, top_n, review_count) 함수
- Step 1 (검색) → Step 2 (상세+리뷰+비교추천 batch)
- 결과를 manifest.json에 저장 (Part 2.6.5 형식으로)
- main.py에서 작은 테스트 실행: top_n=5

실행 후 manifest의 total_x_request_cost로 비용 확인.
```

---

## 5.3 작업 단위 분리하기

**중요**: 한 번에 다 만들지 말고 모듈 단위로 차근차근.

### 권장 작업 순서

| 단계 | 모듈 | 예상 시간 | 검증 |
|---|---|---|---|
| 1 | 환경 + config | 10분 | `python -c "import config; print(config.ZENROWS_API_KEY[:5])"` |
| 2 | zenrows_client | 15분 | 핑 호출 200 OK + cost 헤더 출력 |
| 3 | graphql_queries | 10분 | 쿼리 문자열 출력 후 GraphQL 문법 검증 |
| 4 | search | 15분 | "iphone 15" 검색 → SKU 24개 받기 |
| 5 | product_detail | 20분 | SKU 3개 → 상세+리뷰+추천 한 호출 |
| 6 | pipeline + main | 15분 | top_n=5로 전체 흐름 |

각 단계마다 **반드시 동작 확인** 후 다음으로. 한 번에 다 만들면 어디서 잘못된지 못 찾아요.

### 단계 사이 검증 프롬프트

```
방금 만든 [모듈 이름] 단독 테스트해줘. 작은 입력으로 호출하고
출력 보여줘. 만약 에러나면 그것도 그대로 보여주고.

성공 기준:
- [구체적인 검증 조건]
```

---

## 5.4 새 기능 추가 프롬프트

기존 코드에 새 기능을 추가할 때 쓰는 패턴.

### 5.4.1 새 GraphQL 쿼리 추가 (Part 6.2로 추출했을 때)

```
브라우저에서 추출한 새 GraphQL 쿼리야:

[쿼리 문자열 붙여넣기]

변수:
[변수 dict 붙여넣기]

다음 작업 해줘:
1. graphql_queries.py에 [용도] 쿼리 추가
   - 단건이면 XXX_QUERY 상수로
   - batch가 가능하면 build_xxx_batch_query(sku_ids) 함수로
2. 새 모듈 [모듈명].py 만들어서 가이드 Part 4의 다른 모듈들 패턴 따라가기
3. pipeline.py에서 호출하도록 통합
4. 호출 수 영향 Part 2.7 estimate_cost로 계산해서 보여주기
```

### 5.4.2 데이터 저장 추가 (DB/파일)

```
지금은 결과를 JSON 파일로만 저장하는데, SQLite DB에도 저장하고 싶어.

요구사항:
- storage.py 새로 만들기
- save_to_db(data) 함수: products 테이블에 INSERT/UPDATE
- pipeline.py에서 save_to_json 옆에 save_to_db도 호출
- 스키마는 가이드 Part 8.2 필드 사전 보고 추정

기존 코드 흐름 깨지지 않게 해주고, 실행해서 DB 파일 생성되는지 확인.
```

### 5.4.3 sponsored 광고 정보 보강 (실전 예시)

```
검색 결과에 sponsored(광고) 행들이 있는데 정보가 부족해.
sku_id만 있고 가격, 평점, 이미지 등이 비어있어.

다음 작업 해줘:
1. sponsored_enrichment.py 새로 만들기
2. enrich_sponsored_rows(rows) 함수: 
   - container_type == "sponsored_ingrid"인 행만 골라서
   - sku_id 리스트 추출 후 chunk_size=10으로 batch 호출
   - 받은 데이터로 원본 행에 가격/이미지/평점 채우기
3. retry 로직 (MAX_ATTEMPTS=3, exponential backoff)
4. 호출마다 x-request-cost 추적해서 manifest에 저장
5. pipeline.py에서 검색 후, 상세 호출 전에 호출하도록 통합

추가 호출 수와 예상 비용 미리 계산해서 보여줘.
```

### 5.4.4 페이지네이션 추가

```
지금은 검색 1페이지만 가져오는데, 여러 페이지 가져오고 싶어.

요구사항:
- search.py의 search_all_pages(query, max_pages) 활용
- 페이지마다 manifest에 메타 저장 (호출 시각, 비용, status)
- 도중에 실패하면 재시도 (최대 3회)
- 캐싱: 이미 받은 페이지는 재호출 안 함 (force_refresh 옵션)

테스트: max_pages=3으로 실행. 두 번째 실행 시 캐시 활용되는지 확인.
```

### 5.4.5 비용 모니터링 추가

```
가이드 Part 2.6.5처럼 비용 추적 기능을 추가하고 싶어.

요구사항:
- zenrows_client.py에서 매 호출마다 x-request-cost 저장
- pipeline.py 실행 끝에 manifest.json에 total_x_request_cost 합계 저장
- main.py에서 실행 끝에 "💰 이번 실행 총 비용: X" 출력
- 누적 비용 보는 함수 `report_total_cost(run_root)` 도 추가

테스트: 작은 실행 후 manifest.json에 비용 기록됐는지 확인.
```

---

## 5.5 디버깅 프롬프트

문제가 생겼을 때 AI한테 던질 패턴.

### 5.5.1 일반 에러

```
[모듈 이름]의 [함수 이름] 실행 중 에러가 났어.

에러 메시지:
[전체 에러 그대로 — truncate 금지]

입력값:
[검색어/SKU/파라미터 값]

가이드 Part 8.3 에러 코드 사전과 Part 8.4 FAQ 참고해서
원인 진단하고 고쳐줘.
```

### 5.5.2 차단 의심 (403, 빈 응답)

```
ZenRows 응답이 403이야 (또는 빈 응답이 오고 있어).

상황:
- 처음에는 잘 되다가 [N번째 호출]부터 차단됨
- session_id: [값]
- 호출 간격: [값]초

가이드 Part 8.4 Q1 참고해서 진단해줘.
session_id 새로 만들기, 호출 간격 늘리기 같은 안전장치도 추가해줘.
```

### 5.5.3 비용 폭증 의심

```
ZenRows 잔여 호출이 예상보다 빠르게 줄고 있어.

확인 결과:
- 응답 헤더 x-request-cost: [값]
- 호출 1번당 차감: [관찰값]

가이드 Part 2.6과 8.4 Q8 보고 진단해줘.
js_render 설정이 잘못 켜져있는지 확인하고, 환경변수로 즉시 끄는 방법도 알려줘.
```

### 5.5.4 데이터 누락 (200 OK인데 필드 비어있음)

```
GraphQL 응답은 200인데 [필드 이름]이 null로 와.

응답 일부:
[관련 JSON 부분 붙여넣기]

쿼리:
[관련 쿼리 부분 붙여넣기]

가이드 Part 8.4 Q5 보고 진단해줘. price() 함수 인자 누락,
변수 타입 오류 등 흔한 원인부터 체크해줘.
```

### 5.5.5 응답은 OK인데 결과가 매번 다름

```
같은 검색어 "cellphone" 호출하는데 매번 결과가 조금씩 달라.
같은 SKU도 나왔다 안 나왔다 해.

가이드 Part 8.4 Q6 참고해서 진단.
zipCode, storeId 같은 위치 파라미터를 고정값으로 못 박는 코드 수정해줘.
```

---

## 5.6 운영/유지보수 프롬프트

배포 후 일상적으로 쓰는 패턴.

### 5.6.1 비용 점검

```
가이드 Part 2.6 절차대로 ZenRows 비용 점검 스크립트 만들어줘.

기능:
1. 최근 manifest.json들 다 모아서 누적 비용 계산
2. 같은 호출의 x-request-cost가 비정상적으로 높은 경우 경고
3. js_render 설정 잘못된 호출 있는지 검사

매일 한 번 돌리면 좋겠어.
```

### 5.6.2 정기 실행 자동화

```
가이드 Part 7.3 보고 Windows Task Scheduler용 배치 스크립트 만들어줘.

조건:
- 매일 새벽 3시 실행
- 가이드 Part 2.7 estimate_cost로 일일 호출 수 미리 계산
- 한 달 한도(25,000회) 초과 우려 시 실행 안 하고 로그만 남기기
- 결과는 data/YYYYMMDD/ 폴더에 저장
```

### 5.6.3 새 사이트 추가

```
[사이트 이름] 스크래퍼도 만들고 싶어.
가이드 Part 6.2 절차로 GraphQL 쿼리 추출해왔어:

쿼리: [붙여넣기]
변수: [붙여넣기]
URL: [GraphQL 엔드포인트]

가이드 Part 2.2 Proton VPN 테스트 코드로 먼저 봇 보호 강도 확인하고,
- Proton VPN으로 충분하면 → proton_vpn_client.py 새로
- ZenRows 필요하면 → 기존 zenrows_client.py 재사용

새 사이트용 모듈 구조 만들어줘. bestbuy_scraper 폴더는 건드리지 말고
별도 폴더 [사이트명]_scraper로.
```

### 5.6.4 데이터 분석/요약

```
data/ 폴더에 쌓인 manifest.json과 products 파일들 분석해줘.

원하는 결과:
1. 일별 호출 수 추이 그래프 (matplotlib)
2. 카테고리별 평균 가격 변화
3. 가장 자주 등장한 비교 추천 SKU TOP 10
4. ZenRows 비용 일별 합계

analyzer.py 새로 만들어서 함수로 분리해줘.
```

---

## 5.7 고객사 요청 대응 프롬프트 ⭐ (실무 핵심)

> 데이터 수집 운영하다 보면 **"이거 추가로 수집해달라"**, **"저거 빼달라"** 같은 요청이 항상 와요.
> 그때마다 코드 어디를 고쳐야 할지 막막하죠. 여기 프롬프트가 답입니다.

### 5.7.1 새 필드 추가 요청 (예: "리뷰에 헬프풀 카운트도"

**시나리오**: 고객사가 "리뷰 데이터에 '도움됨' 투표 수도 같이 받아주세요" 요청.

**먼저 해야 할 일**: 그 필드가 GraphQL에 존재하는지 확인 (Part 6.2 절차).

**프롬프트**:
```
고객사에서 새 데이터 필드를 요청했어:
- 추가하고 싶은 것: 리뷰의 "도움됨(helpful)" 투표 수
- 현재 상태: reviews(filter:{pageSize:20}) 호출하면 rating, title, text,
  userNickname, submissionTime만 받고 있음

다음 작업 해줘:

[1] 가이드 Part 6.2 절차 따라서 브라우저로 Best Buy 리뷰 페이지 열고,
   "도움됨" 투표가 GraphQL 응답 어디에 들어오는지 확인하는 방법 알려줘.
   (어떤 필드명일지 후보 — helpfulCount, positiveFeedbackCount 등)

[2] 그 필드가 확인되면 graphql_queries.py의 build_combined_batch_query
   안 reviews 부분에 필드 추가.

[3] product_detail.py의 normalize_product 함수에서 그 필드를
   응답에 포함시키기.

[4] 추가 호출 수는 0 (기존 호출에 필드만 추가). 응답 크기만 약간 증가.
   가이드 Part 2.7 estimate_cost 다시 돌려서 영향 없는지 확인.

[5] 작은 테스트: SKU 1개 호출해서 새 필드가 실제로 들어오는지 확인.
   비어있으면 필드명 잘못 추측한 거니까 다시 확인.
```

> 💡 **왜 이렇게 길게?** 비전문가가 "도움됨 추가해줘"만 하면 AI가:
> - 어디 추가할지 모름
> - 실제 GraphQL에 그 필드 있는지 확인 안 함
> - 비용 영향 무시
>
> 위 프롬프트는 그 5가지를 다 짚어줘서 AI가 헛다리 안 짚어요.

### 5.7.2 새 종류 데이터 추가 요청 (예: "Q&A도 수집")

**시나리오**: 고객사가 "각 상품의 Q&A 데이터도 수집해주세요" 요청.

이건 **새 GraphQL 함수 호출**이 필요할 수 있어요 (기존 호출에 필드 추가가 아니라).

**프롬프트**:
```
고객사 요청: 각 상품의 Q&A(질문과 답변) 데이터를 추가로 수집.

먼저 분석해줘:

[1] 가이드 Part 8.1 GraphQL 쿼리 목록 보고 Q&A 관련 쿼리 찾기.
   (예: QuestionsAndAnswers_Init)

[2] 이걸 기존 build_combined_batch_query에 묶을 수 있는지 확인:
    - 같은 productBySkuId 안에 questions 필드로 들어가면 → 호출 수 그대로
    - 별도 호출 필요하면 → 호출 수 2배 증가 ⚠️

[3] 호출 수 영향 estimate_cost로 다시 계산:
    - 영향 없으면 그냥 추가
    - 호출 수 2배 늘어나면 비용/한도 다시 점검 필요

[4] 결정 후 코드 수정:
    a. 같은 쿼리에 묶기 가능 → graphql_queries.py만 수정
    b. 별도 호출 필요 → qna.py 새 모듈 + pipeline.py 통합

[5] 작은 테스트: SKU 3개로 Q&A 받아지는지 확인.
   Q&A 없는 상품도 있을 수 있으니까 null 처리도.

비용 변화 미리 보여주고, 진행 여부 물어봐줘.
```

### 5.7.3 필드 제거 요청 (예: "스펙 전부 빼주세요")

**시나리오**: 고객사가 "스펙 정보는 안 쓰니까 빼주세요. 응답이 너무 무거워요" 요청.

**프롬프트**:
```
고객사 요청: 상품 응답에서 specificationGroups 필드 제거.
이유: 응답이 너무 무겁고 안 씀.

다음 작업 해줘:

[1] graphql_queries.py에서 specificationGroups 관련 부분 제거:
    - PRODUCT_DETAIL_QUERY
    - build_combined_batch_query의 ProductFields fragment

[2] product_detail.py의 normalize_product에서도 specs 처리 제거.
    하지만 기존 저장된 데이터의 specs 컬럼은 유지 (호환성).

[3] 호출 수는 그대로지만 응답 크기 감소 → GB 한도에 여유 생김.
    얼마나 줄어드는지 1개 SKU로 before/after 응답 크기 비교해서 보여줘.

[4] 기존 저장된 데이터에 specs 컬럼이 있으면 NULL로 두고,
    새로 받는 것부터 안 채워지도록.

[5] 단위 테스트로 SKU 1개 호출해서 specs 없이도 잘 동작 확인.
```

### 5.7.4 수집 범위 확장 요청 (예: "리뷰 20개 → 100개")

**시나리오**: 고객사가 "리뷰를 더 많이 (100개) 수집해주세요" 요청.

**위험**: 페이지네이션이 필요할 수도 있고, 호출 수가 늘 수 있음.

**프롬프트**:
```
고객사 요청: 각 상품의 리뷰를 20개에서 100개로 늘리기.

위험 분석 먼저:

[1] reviews(filter:{pageSize:N}) 함수에 pageSize 100 가능한지 확인.
    Best Buy GraphQL이 한 번에 100개 허용하면 그냥 변경.
    제한 있으면 (예: 최대 50) 페이지네이션 필요.

[2] 페이지네이션 필요하면:
    - 한 SKU당 호출 수가 1 → N개로 증가 (큰 비용 차이!)
    - 50 SKU × 2페이지 = 100 추가 호출
    - estimate_cost로 영향 계산

[3] 응답 크기도 5배 증가 → 응답 시간 늘어남.
    chunk_size를 10에서 5로 줄여야 할 수도 있음.

[4] 변경 후 비용 변화 만든 후 보고:
    - 변경 전: 월 X번 실행 가능
    - 변경 후: 월 Y번 실행 가능
    - 차이가 크면 고객사에 단가 협의 필요할 수 있음

[5] 작은 테스트: SKU 3개로 진짜 100개 받아지는지 확인.
   (인기 상품은 1000+ 리뷰 있어서 100개 보장됨)
   (덜 인기 상품은 50개만 있을 수도 있음 — 그것도 OK)
```

### 5.7.5 새 상품 카테고리 추가 (예: "노트북도 수집")

**시나리오**: 기존 cellphone만 수집 중인데 laptop도 추가 요청.

**프롬프트**:
```
고객사 요청: 기존 cellphone 수집 외에 laptop 카테고리도 같이 수집.

진행 절차:

[1] 비용 영향 분석:
    - laptop도 6,000개 SKU 가정
    - cellphone과 똑같은 호출 수 추가 발생
    - 가이드 Part 2.7 estimate_cost로 합계 계산
    - 한 달 한도(25,000회) 대비 % 확인
    - 한도 초과 위험 있으면 경고

[2] 코드 변경:
    - main.py에서 query 인자로 ["cellphone", "laptop"] 둘 다 받기
    - 각 카테고리별로 별도 폴더(data/cellphone, data/laptop)에 저장
    - manifest.json에서 카테고리별로 비용 분리

[3] 카테고리별 검색 변수가 다를 수 있음 (예: 가격대 필터):
    - 가이드 Part 4.3의 build_search_variables에 category별 옵션 분리

[4] 작은 테스트: 두 카테고리 다 top_n=3으로 실행해서
   각 폴더에 데이터 떨어지는지 확인.

[5] 정기 실행할 거면 가이드 Part 7.3의 Task Scheduler 설정도 업데이트.
```

### 5.7.6 데이터 형식 변경 요청 (예: "CSV 말고 Excel")

**시나리오**: "엑셀 파일로 받고 싶어요" 요청.

**프롬프트**:
```
고객사 요청: 결과를 CSV 대신 Excel(.xlsx)로.

다음 작업:

[1] openpyxl 설치 필요: pip install openpyxl

[2] storage.py에 save_to_excel(data, filename) 함수 추가:
    - 시트 1: products (메인 데이터)
    - 시트 2: compare_map (sku별 추천 SKU)
    - 시트 3: reviews (별도 시트로 펼치기)
    - 헤더 행 굵게, 컬럼 너비 자동

[3] main.py에서 기존 save_to_json + 새 save_to_excel 둘 다 호출.
    (CSV는 백업용으로 유지, Excel은 고객 전달용)

[4] 1회 테스트로 .xlsx 파일 열어보고 깨지지 않는지 확인.

비용/호출 수에는 영향 없음 (저장 형식만 변경).
```

### 5.7.7 데이터 빈도/스케줄 변경 (예: "하루 1회 → 4시간마다")

**시나리오**: "더 자주 업데이트해주세요" 요청.

**프롬프트**:
```
고객사 요청: 하루 1회 → 4시간마다 (하루 6회) 자동 실행.

위험 분석 필수:

[1] 비용 영향 (가장 중요):
    - 현재: 일일 X회 × 30일 = 월 30X회
    - 변경: 일일 6X회 × 30일 = 월 180X회 (6배!)
    - 한 달 한도 25,000 ÷ 180X = 며칠 만에 한도 소진?
    - 가이드 Part 2.4 시나리오 3 같은 사고 막기

[2] 한도 초과 시 옵션:
    a. 한 번 실행 시 수집 데이터 줄이기 (top_n 감소)
    b. 카테고리 나눠서 시간대별 분산
    c. 변하지 않는 필드는 캐싱 (Part 2.5 원칙 6)
    d. 안 되면 고객사에 단가 협의

[3] 결정 후 가이드 Part 7.3 Task Scheduler 업데이트.

[4] 매 실행 후 잔여 한도 확인 알림 추가:
    - manifest에 누적 비용 합산
    - 한도 80% 도달 시 Slack/이메일 경고

[5] 첫 24시간 모니터링: 실제로 비용이 예상대로 나오는지 검증.
```

### 5.7.8 모르겠을 때 만능 프롬프트

위에 없는 요청이 와도 당황하지 마세요. **이거 그대로 복붙**하세요:

```
고객사에서 다음 요청을 받았어:

[고객사 요청 그대로 복붙]

다음 절차로 분석해줘:

[1] 요청 분류:
    - 새 필드 추가? (기존 쿼리에 필드만 추가, 호출 수 그대로)
    - 새 함수 호출? (별도 호출 필요, 호출 수 증가)
    - 필드 제거? (응답 크기 감소)
    - 수집 범위 변경? (페이지/리뷰 개수 등)
    - 형식 변경? (CSV/Excel/DB)
    - 스케줄 변경? (실행 빈도)
    - 새 카테고리? (수집 대상 확장)

[2] 가이드의 관련 섹션:
    - Part 8.1 GraphQL 쿼리 목록에서 해당 필드/함수 찾기
    - Part 2.7 estimate_cost로 비용 영향 계산
    - Part 5.7의 비슷한 시나리오 찾기

[3] 변경 전/후 비교 보여주기:
    - 호출 수 변화
    - 응답 크기 변화
    - 한 달 한도 영향
    - 코드 수정 범위

[4] 위험 있으면 경고:
    - 한도 초과 위험
    - 응답 시간 증가로 timeout 위험
    - 차단 위험 (호출 빈도 증가)

[5] 진행 여부 확인 후 단계별 작업 시작.

작은 테스트(SKU 1~3개)로 검증 먼저, 그 다음 풀 실행.
```

### 5.7.9 고객사 요청 대응 워크플로우 (요약)

요청 받으면:

```
1. 요청 받음
   ↓
2. 5.7.8 만능 프롬프트로 AI에게 분석 요청
   ↓
3. AI가 분류 + 비용 영향 + 코드 수정 범위 분석
   ↓
4. 비용 영향 확인:
   - 영향 없음/적음 → 진행
   - 영향 큼 → 고객사에 사전 안내 (단가, 한도)
   ↓
5. 5.7.1~5.7.7 중 비슷한 시나리오 프롬프트 사용
   ↓
6. 작은 테스트로 검증
   ↓
7. 풀 실행
   ↓
8. 결과 고객사 전달 + 비용 보고
```

---

## 5.8 프롬프트 안티패턴 (이렇게 하지 마세요)

### ❌ 너무 막연한 요청

```
"개선해줘"
"더 좋게 만들어줘"  
"버그 고쳐줘"
```

→ AI가 뭘 할지 모름. 결과가 산으로 감.

**대신**:
```
"search.py에서 호출 간격이 너무 짧아서 차단 위험이 있어 보여.
random sleep을 1.5~3.5초로 추가해줘. 가이드 Part 8.4 Q1 참고."
```

### ❌ 한 번에 너무 많이

```
"검색, 상세, 비교추천, 리뷰, 저장, 알림, 분석 다 만들어줘"
```

→ 결과가 부실. 디버깅 어려움.

**대신**: Part 5.3의 단계별 작업 순서대로.

### ❌ 가이드 무시

```
"requests로 직접 Best Buy 호출해서 데이터 가져와줘"
```

→ ZenRows 안 거치면 즉시 차단. 가이드의 핵심을 무시.

**대신**:
```
"가이드의 zenrows_client.py를 통해서만 호출하도록 하고..."
```

### ❌ 검증 없이 다음 단계

```
"방금 만든 거 잘 됐겠지? 다음 거 만들어줘"
```

→ 작은 실수가 누적되어 전체 실패.

**대신**: 5.3의 검증 프롬프트로 매 단계마다 확인.

### ❌ 비용 무시

```
"전체 카테고리 다 긁어줘"
```

→ 한 달 한도 며칠 만에 소진.

**대신**:
```
"전체 카테고리 긁기 전에 Part 2.7 estimate_cost로 호출 수 계산해줘.
한도 80% 넘으면 작업 분할 방법도 제안해줘."
```

---
---

# Part 6. 새 사이트/기능 추가하기 ⭐

> 이 챕터를 익히면 **다른 이커머스 사이트**도 같은 방식으로 스크래핑할 수 있어요.

## 6.1 핵심 아이디어: 브라우저의 네트워크 탭

대부분의 현대 웹사이트(이커머스, 뉴스, SNS)는 **GraphQL이나 REST API로 데이터를 받아옴**. 우리가 할 일은 그 API를 **브라우저처럼 흉내내는 것**.

작업 흐름:
```
[1단계] 브라우저로 사이트 열기
   ↓
[2단계] 개발자도구의 Network 탭에서 GraphQL/API 요청 찾기
   ↓
[3단계] 요청의 쿼리 + 변수 + 헤더 추출
   ↓
[4단계] Python으로 ZenRows 통해 똑같이 호출
   ↓
[5단계] 응답 파싱
```

## 6.2 GraphQL 쿼리 추출하는 법 (단계별)

### Step 1. Chrome 개발자도구 열기

1. 대상 사이트 접속 (예: bestbuy.com)
2. F12 또는 우클릭 → "검사"
3. **Network 탭** 클릭
4. 상단 필터에서 **Fetch/XHR** 선택 (이게 핵심)

### Step 2. 사이트에서 원하는 액션 수행

브라우저에서 데이터를 받아오는 액션 실행:
- 검색하기
- 페이지 이동
- 상품 클릭
- "더 보기" 버튼

이때 Network 탭에 요청들이 쌓여요.

### Step 3. GraphQL 요청 찾기

Network 탭에서 다음 패턴 찾기:
- URL에 `/graphql`, `/api/graphql`, `/gateway/graphql` 포함
- Request Method가 **POST**
- Request payload에 `query`, `variables` 필드

Best Buy 예시:
```
URL: https://www.bestbuy.com/gateway/graphql
Method: POST
Payload: {
  "query": "query Search(...) { ... }",
  "variables": {...}
}
```

### Step 4. 요청 정보 추출

요청을 클릭하면 우측 패널에 상세 정보:

**Headers 탭**:
- Request URL
- Request Headers (User-Agent, Accept 등)

**Payload 탭** (또는 Request 탭):
- `query`: GraphQL 쿼리 문자열
- `variables`: 변수 dict
- `operationName`: 쿼리 이름

이걸 그대로 복사해서 Python 코드에 넣으면 돼요.

### Step 5. cURL로 복사 (편의 기능)

요청 우클릭 → **Copy → Copy as cURL**

cURL 명령어가 클립보드에 복사됨. 이걸:
- [https://curlconverter.com](https://curlconverter.com) 에 붙여넣으면
- Python `requests` 코드로 변환됨

그 코드를 ZenRows 형식으로 살짝 수정하면 끝.

## 6.3 실전 예시: 새로운 쿼리 발견하기

예를 들어 Best Buy에서 "Q&A 데이터"를 추가로 가져오고 싶다면:

### 1) 브라우저에서 Q&A 영역 펼치기

상품 페이지 스크롤 → "Questions & Answers" 섹션 클릭

### 2) Network 탭에서 새 요청 찾기

`QuestionsAndAnswers_Init` 같은 이름의 GraphQL 요청 발견.

### 3) 쿼리 복사

```graphql
query QuestionsAndAnswers_Init($skuId: String!, $searchText: String!) {
  productBySkuId(skuId: $skuId) {
    skuId
    questionInfo { totalQuestionCount totalAnswerCount }
    questions(filter: {showAnsweredQuestions: false, searchText: $searchText},
              pagination: {page: 1, pageSize: 8}) {
      results {
        answerCount
        id
        text
        ...
      }
    }
  }
}
```

### 4) 변수 복사

```json
{
  "skuId": "6668565",
  "searchText": ""
}
```

### 5) Python으로 사용

`graphql_queries.py`에 추가:
```python
QNA_QUERY = """<위 쿼리 그대로>"""

def get_qna(sku_id: str):
    return call_graphql(QNA_QUERY, {
        "skuId": sku_id,
        "searchText": ""
    })
```

## 6.4 새 사이트에 적용하기

다른 사이트(예: Walmart, Target, Amazon)도 같은 방식으로 가능. 사이트별 차이점:

### 사이트별 봇 보호 강도

| 사이트 | 봇 보호 | ZenRows 비용 카운터 |
|---|---|---|
| Best Buy | Akamai | protected (10K/월) |
| Walmart | PerimeterX | protected |
| Target | Akamai | protected |
| Amazon | 자체 | protected (매우 까다로움) |
| eBay | 약한 보호 | basic (250K/월) |
| 소규모 쇼핑몰 | 없음 또는 약함 | basic |

**basic 카운터로 처리되면 25배 더 많이 호출 가능**. 새 사이트 작업 전 ZenRows 테스트로 어느 카운터에서 빠지는지 확인하세요.

### 사이트별 API 종류

- **GraphQL**: Best Buy, Walmart, Shopify 사이트 다수
- **REST**: Target, 많은 전통적 사이트
- **GraphQL + REST 혼용**: Amazon

GraphQL이든 REST든 추출 방법은 같아요. Network 탭에서 찾아서 흉내내기.

## 6.5 새 기능 추가 워크플로우 (AI와 함께)

기존 코드에 새 GraphQL 쿼리 추가할 때:

### 1) 브라우저에서 쿼리 캡처

위 6.2 절차로 GraphQL 쿼리 + 변수 추출

### 2) AI에게 던지기

```
다음 GraphQL 쿼리를 graphql_queries.py에 추가해줘.
함수 이름은 build_xxx_query 또는 XXX_QUERY 형식으로.

쿼리:
[복사한 쿼리 붙여넣기]

변수:
[복사한 변수 붙여넣기]
```

### 3) AI가 만든 함수를 모듈에 통합

```
방금 만든 쿼리를 사용해서 product_detail.py의
get_full_details 함수에 [기능 이름] 데이터도 가져오도록 통합해줘.
```

### 4) 비용 영향 확인

```
새 필드/쿼리 추가로 호출 수가 늘었나? Part 2.7의 estimate_cost 함수로
다시 계산해서 확인해줘.
```

## 6.6 함부로 추가하면 안 되는 것

### ⚠️ 호출 수가 폭증하는 경우

- **별도 호출이 필요한 데이터**: 위시리스트, 장바구니 (인증 필요)
- **페이지네이션이 있는 데이터**: 리뷰 100개, Q&A 50개 등
- **사용자별로 다른 응답**: 개인화 추천

### ⚠️ 인증이 필요한 쿼리

`CustomerData`, `SavedItemLists` 등은 로그인 토큰 필요. ZenRows로 로그인 처리는 매우 복잡함. 가능하면 피하기.

### ✅ 추가하기 쉬운 것

- 기존 `productBySkuId` 응답에 **필드만 추가** (호출 수 그대로)
- 정적 데이터 (한 번 받으면 캐싱 가능)

---
---

# Part 7. 환경 설정 (EC2 Windows)

## 7.1 EC2 Windows에서 작업할 때 주의사항

### Python 설치

1. [Python 공식 사이트](https://www.python.org/downloads/windows/) → Windows installer 64-bit
2. 설치 시 **"Add Python to PATH"** 체크 (필수)
3. 설치 후 PowerShell에서 확인:
```powershell
python --version
pip --version
```

### Git 설치 (선택)

[Git for Windows](https://git-scm.com/download/win) 설치하면 Claude Code랑 같이 쓰기 편함.

### 작업 디렉터리 만들기

```powershell
cd C:\Users\Administrator\
mkdir bestbuy_scraper
cd bestbuy_scraper
```

> EC2 사용자명은 Administrator 또는 EC2-User. 본인 환경에 맞게.

### 가상환경 (권장)

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install requests python-dotenv
```

### .env 파일 (PowerShell에서 생성)

```powershell
@"
ZENROWS_API_KEY=여기에_실제_API_키
"@ | Out-File -Encoding utf8 .env
```

## 7.2 EC2에서 호출할 때 특별히 신경 쓸 점

### EC2 IP는 데이터센터 IP

- 직접 Best Buy 호출하면 즉시 차단 (시도하지 말 것)
- **반드시 ZenRows 경유**해야 함
- ZenRows가 주거용 IP로 우회해줌

### Proton VPN을 EC2에서?

- 가능은 하지만 **Best Buy에는 효과 없음** (Part 2.2)
- 다른 사이트나 일반 브라우징용으로만

### EC2 보안그룹

- **아웃바운드 HTTPS (443)** 열려있어야 함 (기본값)
- 인바운드는 RDP/SSH만 (작업용)

### 인스턴스 타입

- t3.small ~ t3.medium이면 충분
- 메모리 2~4GB
- ZenRows가 외부에서 처리해주니까 강한 스펙 불필요

## 7.3 자동화 (Windows Task Scheduler)

매일 또는 매시간 자동 실행하려면:

### 1) 배치 파일 만들기

`run_scraper.bat`:
```batch
@echo off
cd C:\Users\Administrator\bestbuy_scraper
call venv\Scripts\activate
python main.py >> logs\scraper.log 2>&1
```

### 2) Task Scheduler 등록

1. Windows 시작 → "작업 스케줄러" 검색
2. "작업 만들기" 클릭
3. 트리거: 매일 또는 매시간
4. 동작: `run_scraper.bat` 실행
5. **"가장 높은 권한으로 실행"** 체크 (RDP 끊겨도 동작)

### ⚠️ 자동화 시 비용 폭주 주의

자동화하면 **호출이 매일 누적**됨. Part 2.4 시나리오 3 같은 일 발생.

자동화 전 반드시:
1. `estimate_cost()` 함수로 일일 호출 수 계산
2. 한 달 한도 ÷ 일일 호출 수 = 며칠 돌릴 수 있는지 확인
3. 한도 초과 안 나는 빈도로 스케줄링

```python
# 매일 1회 자동화 가능 여부 체크
daily_calls = estimate_cost(num_search_pages=1, num_skus=50)
monthly_calls = daily_calls * 30
print(f"매일 1회 자동화 시 월 {monthly_calls}회")
print(f"한도 내?: {monthly_calls <= 10000}")
```

## 7.4 로그와 데이터 저장

### 디렉터리 구조 (EC2 Windows)

```
C:\Users\Administrator\bestbuy_scraper\
├── venv\                  # 가상환경
├── .env                   # API 키
├── config.py
├── zenrows_client.py
├── ...
├── logs\                  # 로그 파일
│   └── scraper.log
└── data\                  # 수집 데이터
    └── bestbuy_cellphone_20251223_120000.json
```

### S3에 백업 (선택)

EC2 데이터 손실 방지로 S3 자동 업로드:

```python
import boto3

s3 = boto3.client("s3")
s3.upload_file(
    "data/bestbuy_xxx.json",
    "your-bucket-name",
    f"bestbuy/{datetime.now().strftime('%Y/%m/%d')}/xxx.json"
)
```

EC2 IAM Role에 S3 권한 부여하면 키 없이도 동작.

---
---

# Part 8. 레퍼런스

## 8.1 모든 GraphQL 쿼리 목록

> 이 목록은 실제 Best Buy 페이지(PDP + 검색결과)에서 추출한 **전체 34개 쿼리**입니다.
> 가이드에서 직접 사용하는 건 핵심 3개고, 나머지는 필요할 때 참고용.

### 🎯 우리가 직접 사용하는 핵심 3개

| 쿼리명 | 역할 | 입력 변수 | 가이드 위치 |
|---|---|---|---|
| `search` (PlpView_ProductList_Init 내부) | 검색결과 상품 리스트 | `query, page, sort, filter` | Part 3.3 |
| `productBySkuId` | 상품 상세 (이름/가격/리뷰/스펙) | `skuId` | Part 4.5 |
| `recommendationsV2` | 비교/보완 추천 SKU 목록 | `skuId, placement, site, storeIds` | Part 4.5 |

### 📋 PDP (상품 상세 페이지) 쿼리들 — 총 27개

브라우저로 Best Buy 상품 페이지(`/product/...`) 열면 호출되는 쿼리들.

#### 핵심 데이터

| 쿼리명 | 역할 |
|---|---|
| `PDP_ProductSkuIdComposite_Init` ⭐ | PDP 메인 — 25+ Fragment 한방에 (헤더/하이라이트/스펙/이미지 다) |
| `BsinFromSkuId` | SKU → BSIN 변환 (변형 묶음 마스터 ID) |
| `getProduct` | 기본 상품 정보 |
| `getProductActivatedPricingOptions` | 멤버십/캠페인 적용 가격 |

#### 가격

| 쿼리명 | 역할 |
|---|---|
| `PriceExperienceInit_GetProduct` | 표시 가격 + 프로모션 + 멤버십 업셀 + EcoRebate |
| `getMobileContracts` | 휴대폰 통신사 약정 가격 |

#### 리뷰/Q&A

| 쿼리명 | 역할 |
|---|---|
| `ReviewStats_Init` | 평점 + 리뷰 개수 (가볍게) |
| `QuestionsAndAnswers_Init` | Q&A 목록 + AI 답변 |

#### 미디어/이미지

| 쿼리명 | 역할 |
|---|---|
| `MediaGallery_Init` | 이미지 + AR 모델 + 비디오 |
| `BestMediaV3PdpSbb` | 광고/스폰서드 미디어 추천 |
| `ProductVideoSchema_Init` | 비디오 메타데이터 |
| `ProductSchema_init` | SEO용 JSON-LD 스키마 |

#### 스펙/설명

| 쿼리명 | 역할 |
|---|---|
| `ProductFeatures_Init` | 풀스펙 + 매뉴얼 + 설명 + EcoRebate |

#### 뱃지

| 쿼리명 | 역할 |
|---|---|
| `Personalized_Badge_Data` | "Top Deal", "New" 등 개인화 뱃지 |

#### 변형 (색상/용량)

| 쿼리명 | 역할 |
|---|---|
| `BsinProductVariationsV2_Init` | 같은 모델의 색상/용량 옵션 |

#### 배송/재고

| 쿼리명 | 역할 |
|---|---|
| `FulfillmentOptionHook_FulfillmentDynamicQuery` | 배송/픽업 옵션 |
| `AddToCart_FulfillmentDynamicQuery` | 장바구니 담기 시 배송 옵션 |
| `ShelfDisplay_Init` | 매장 진열 정보 |
| `NotifyMe_ProductBySkuId` | 재입고 알림 가능 여부 |
| `InviteSalesDynamicQuery` | 대기자 명단 |
| `FulfillmentEventsStaticQuery` | 진행 중/예정 이벤트 |

#### 트레이드인

| 쿼리명 | 역할 |
|---|---|
| `GetTradeInData` | 트레이드인 가능 여부 |
| `GetTradeInDataInit` | 트레이드인 초기 데이터 |

#### 추천

| 쿼리명 | 역할 |
|---|---|
| `RecommendationsAdDisplay_` ⭐ | **Compare 추천 + Complementary 추천** (핵심!) |

#### 부가 기능

| 쿼리명 | 역할 |
|---|---|
| `MPX_MoreBuyingOptionsEntry` | 마켓플레이스 셀러 옵션 |
| `SavedItemLists` | 위시리스트 (인증 필요) |
| `CustomerData` | 고객 프로필/멤버십 (인증 필요) |

### 📋 검색결과 페이지 쿼리들 — 총 13개

브라우저로 Best Buy 검색결과(`/site/searchpage.jsp?st=...`) 열면 호출되는 쿼리들.

| 쿼리명 | 역할 |
|---|---|
| `PlpView_ProductList_Init` ⭐ | **검색결과 메인** (상품 리스트 + 필터/정렬) |
| `PlpView_ProductListItem_Init` | 개별 상품 카드 (lazy load) |
| `PlpView_ParallelQuery` | 매장/카테고리 컨텍스트 |
| `FulfillmentSelectorContentQuery` | 배송/픽업 셀렉터 |
| `PriceBlockPlatmanQuery` | 가격 표시 설정 |
| `KeyValueNode` | 일반 설정 JSON |
| `MPX_MoreBuyingOptionsSimpleAvailabilityData` | 간단 재고 정보 |
| `Personalized_Badge_Data` | 검색결과 뱃지 (PDP와 공유) |
| `ReviewStats_Init` | 리뷰 통계 (PDP와 공유) |
| `NotifyMe_ProductBySkuId` | 재입고 알림 (PDP와 공유) |
| `MPX_MoreBuyingOptionsEntry` | 마켓플레이스 옵션 (PDP와 공유) |
| `FulfillmentEventsStaticQuery` | 이벤트 (PDP와 공유) |
| `CustomerData` | 고객 정보 (PDP와 공유) |
| `SavedItemLists` | 위시리스트 (PDP와 공유) |

### 🎯 추천(placement) 종류

`recommendationsV2`의 `placement` 파라미터:

| placement | 의미 |
|---|---|
| `pdp-compare-mp` | **Compare similar products** (우리가 쓰는 것) |
| `pdp-complementary-mp` | 함께 사면 좋은 상품 (보완 추천) |

### 💡 새 쿼리 활용 프롬프트

위 목록에서 쓰고 싶은 쿼리 발견했을 때 — 그대로 복붙:

```
가이드 Part 8.1 목록에서 [쿼리 이름]을 추가로 활용하고 싶어.

다음 단계로 해줘:

[1] 가이드 Part 6.2 절차 따라서 브라우저로 해당 쿼리가 호출되는 페이지 열고,
   Network 탭에서 [쿼리 이름] 찾기. 쿼리 본문 + 변수 추출.

[2] graphql_queries.py에 추가:
   - 단건 쿼리면 XXX_QUERY 상수로
   - 여러 SKU에 batch 가능하면 build_xxx_batch_query 함수로

[3] 기존 build_combined_batch_query에 묶을 수 있는지 확인:
   - 같은 productBySkuId 안에 들어가면 → 호출 수 그대로
   - 별도 호출 필요하면 → 호출 수 증가

[4] estimate_cost로 비용 영향 계산 (Part 2.7)

[5] 결정 후 코드 수정 + 작은 테스트
```

### ⚠️ 인증 필요한 쿼리들 (보통 무시)

다음 쿼리들은 로그인 토큰이 필요해서 스크래핑에 쓰기 어려움:

- `CustomerData` — 고객 프로필
- `SavedItemLists` — 위시리스트

ZenRows로 로그인 처리하려면 매우 복잡. 보통 안 씁니다.

---

## 8.2 필드 사전 (자주 쓰는 것)

### `productBySkuId` 응답의 주요 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `skuId` | String | SKU ID |
| `name.short` | String | 상품명 (짧은 버전) |
| `name.long` | String | 상품명 (긴 버전) |
| `brand` | String | 브랜드 |
| `url.pdp` | String | 상품 페이지 URL (상대경로) |
| `primaryImage.piscesHref` | String | 메인 이미지 URL |
| `images[]` | List | 추가 이미지들 |
| `price.customerPrice` | Number | 현재 판매가 |
| `price.regularPrice` | Number | 정가 |
| `customerReviews.averageRating` | Number | 평균 별점 (0~5) |
| `customerReviews.reviewCount` | Number | 리뷰 개수 (전체) |
| `specificationGroups[]` | List | 스펙 그룹들 |
| `description.short` | String | 짧은 설명 |
| `description.long` | String | 긴 설명 |
| `reviews(filter: {pageSize: N}).results[]` | List | 리뷰 본문 N개 |

### 리뷰 (`reviews().results[]`) 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `rating` | Number | 별점 (1~5) |
| `title` | String | 리뷰 제목 |
| `text` | String | 리뷰 본문 |
| `userNickname` | String | 작성자 닉네임 |
| `submissionTime` | String | 작성 시각 |

### `price()` 함수의 input

```graphql
price(input: { salesChannel: "LargeView" }) { ... }
```

- `salesChannel`:
  - `"LargeView"`: 데스크탑 가격
  - `"SmallView"`: 모바일 가격

**`salesChannel` 인자를 빼면 가격이 null로 나올 수 있어요. 꼭 넣으세요.**

---

## 8.3 에러 코드 사전

| 에러 | 원인 | 해결 |
|---|---|---|
| HTTP 403 | Akamai 차단 | ZenRows 세션 새로 만들기, 잠시 대기 |
| HTTP 429 | 너무 빠르게 호출 | `RATE_LIMIT_SECONDS` 늘리기 |
| HTTP 503 | 서버 일시 오류 | 잠시 후 재시도 |
| `Non-JSON response` | 차단 페이지 받음 | 응답에 "Reference #" 있는지 확인 |
| `GraphQL errors: NOT_FOUND` | 잘못된 SKU | SKU 존재 확인 |
| `GraphQL errors: BAD_REQUEST` | 변수 형식 오류 | variables dict 구조 확인 |
| `price is null` | salesChannel 빠짐 | `price(input: {salesChannel: ...})` 추가 |
| `documents is empty` | 검색 결과 없음 | 검색어, 필터, 페이지 번호 확인 |

---

## 8.4 자주 막히는 곳

### Q1. ZenRows 응답이 자꾸 차단당해요
- `session_id`를 자주 바꿔보세요 (`bb1`, `bb2`, `bb3`...)
- `proxy_country=us` 유지
- 호출 간격을 2~3초로 늘려보세요
- 한 세션에 너무 많이(50회+) 호출하지 마세요

### Q2. 가격이 null로 나와요
- `price(input: { salesChannel: "LargeView" })` 형태로 호출하세요
- `salesChannel` 없이는 null 자주 나옴

### Q3. Alias batch에서 쿼리가 너무 길다는 에러
- `chunk_size`를 줄이세요 (10 → 5)
- 가져오는 필드 수를 줄이세요

### Q4. 호출 수가 예상보다 많이 나와요 / 비용 폭증
- **Part 2.6의 설정 검증 절차 먼저 진행** (가장 흔한 원인)
- **Part 2.7의 `estimate_cost()` 함수 먼저 돌려보기**
- 같은 SKU 중복 호출 방지 (set으로 dedupe)
- `chunk_size`를 키워서 호출 수 줄이기 (10 → 15)
- ZenRows 대시보드에서 잔여 한도 확인 필수

### Q5. 응답은 200인데 데이터가 비어있어요
- `errors` 필드 확인
- GraphQL 쿼리 문법 에러일 수 있어요
- 변수 이름/타입 확인

### Q6. 검색 결과가 매번 다르게 나와요
- `zipCode`, `storeId`가 매장별로 다른 결과를 줘요
- 일관된 결과 원하면 항상 같은 값 사용

### Q7. SKU는 받았는데 productBySkuId가 안 되는 SKU가 있어요
- Open Box, 단종 상품일 수 있어요
- `try/except`로 개별 SKU 실패 처리

### Q8. ZenRows 호출당 비용이 너무 비싸 보여요 (x-request-cost 헤더)
**원인**: 거의 100% `js_render=true` + `premium_proxy=true` 둘 다 켜져있음 (= 25× 비용)

**확인 방법**:
1. 응답 헤더 `x-request-cost` 값 확인
2. 같은 호출에서 `js_render=false`로 바꿔 재호출
3. 두 값을 비교 — 2.5배 차이나면 진단 확정

**해결**: `js_render` 옵션을 `false`로. GraphQL은 JS 실행 불필요. 자세한 절차는 Part 2.6 참고.

### Q9. ZenRows 설정 어디서 바꿔야 하는지 모르겠어요
- `.env` 파일 또는 코드의 `params` dict 검색
- `js_render` 키워드로 grep
- 환경변수로 관리 안 하고 있으면 Part 2.6.6 참고해서 환경변수화 권장

---

## 8.5 빠른 참조: 자주 쓰는 코드 스니펫

### 검색해서 상위 N개만
```python
from search import search_products
result = search_products("cellphone", page=1, per_page=96)
top_10 = result["products"][:10]
```

### 특정 SKU들의 상세 + 리뷰 + 비교추천 (한방에)
```python
from product_detail import get_full_details
full = get_full_details(["6650408", "6665488"], review_count=20)

# 상품 1의 상세
product = full["products"]["6650408"]
print(product["name"], product["price"])
print(f"리뷰 {len(product['reviews'])}개")

# 상품 1의 비교 추천 SKU 목록
compare_skus = full["compare_map"]["6650408"]
```

### 한 SKU의 비교 추천만
```python
from product_detail import get_full_details
full = get_full_details(["6650408"])
compare_skus = full["compare_map"]["6650408"]
```

### 전체 파이프라인 실행
```python
from pipeline import run_full_pipeline, save_to_json
data = run_full_pipeline("cellphone", top_n=20)
save_to_json(data)
```

---

## 끝.

질문 생기면 이 가이드의 어느 섹션을 참고하면 되는지 함께 Claude Code에 던지세요.
예: "Part 3.5 참고해서 product.py 만들어줘"
