import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto('http://localhost:4322/quickstart/');
await page.waitForLoadState('networkidle');
const summary = await page.$('.sidebar-content summary');
const result = await page.evaluate(el => {
  const cs = window.getComputedStyle(el);
  return { justifyContent: cs.justifyContent, display: cs.display, alignItems: cs.alignItems };
}, summary);
console.log(JSON.stringify(result));
await browser.close();
