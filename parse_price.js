const html = require('fs').readFileSync('bestbuy_universal.html', 'utf8');

// 가격 패턴 찾기
const prices = html.match(/\$[\d,]+\.?\d{0,2}/g);
console.log('All $ prices found:', prices ? prices.slice(0, 20) : 'none');

// data-testid 관련
const testIds = html.match(/data-testid="[^"]*price[^"]*"/gi);
console.log('\nPrice test IDs:', testIds ? testIds.slice(0, 10) : 'none');

// SKU 확인
const skuMatch = html.match(/skuId["\s:]+(\d+)/i);
console.log('\nSKU:', skuMatch ? skuMatch[1] : 'not found');

// 전체 HTML에서 가격 주변 컨텍스트
const priceContext = html.match(/.{0,100}(?:regularPrice|salePrice|currentPrice).{0,100}/gi);
console.log('\nPrice context:', priceContext ? priceContext.slice(0, 5) : 'none');
