// Optional: captures README screenshots from a running mock-mode build.
//   NEXT_PUBLIC_MOCK=1 npm run build && NEXT_PUBLIC_MOCK=1 npx next start -p 3100 &
//   npm i --no-save playwright-core && CHROME_PATH=/usr/bin/google-chrome node scripts/screenshots.mjs
// Also fails loudly if the browser reports a Content-Security-Policy violation.
import { chromium } from "playwright-core";

const BASE = process.env.BASE_URL ?? "http://localhost:3100";
const out = process.env.OUT ?? new URL("../screenshots/", import.meta.url).pathname;
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH ?? "/usr/bin/google-chrome", args: ["--no-sandbox"] });
const violations = [];

const settled = (page) => page.waitForFunction(() => !document.querySelector('[aria-busy="true"]'), null, { timeout: 20000 });

async function ask(page, text) {
  await page.getByRole("textbox").fill(text);
  await page.getByRole("button", { name: /^(Send|भेजें|Bhejein|அனுப்பு)/ }).click();
  await page.waitForTimeout(400);
  await settled(page);
}

for (const [name, viewport] of [["desktop", { width: 1280, height: 900 }], ["mobile", { width: 375, height: 800 }]]) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  page.on("console", (m) => /Content Security Policy|Refused to/i.test(m.text()) && violations.push(m.text()));
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  await page.screenshot({ path: `${out}home-${name}.png` });

  // English conversation with result cards, then the "restarted conversation" notice.
  await page.getByRole("button", { name: /My mother is 62/ }).click();
  await page.waitForSelector("text=You qualify", { timeout: 20000 });
  await settled(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${out}chat-${name}-top.png` });
  await page.screenshot({ path: `${out}chat-${name}-full.png`, fullPage: true });
  await page.getByRole("button", { name: "Why this answer?" }).last().click();
  await page.screenshot({ path: `${out}trace-${name}.png`, fullPage: true });
  await page.getByRole("button", { name: "Why this answer?" }).last().click();
  await ask(page, "mock:expire Yes, she has a bank account and no income tax");
  await page.waitForSelector("text=restarted");
  await page.waitForTimeout(1200);
  await page.locator('[role="note"]').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${out}restarted-${name}.png` });
  await page.screenshot({ path: `${out}restarted-${name}-full.png`, fullPage: true });
  await page.close();

  // Hindi conversation.
  const hp = await ctx.newPage();
  hp.on("console", (m) => /Content Security Policy|Refused to/i.test(m.text()) && violations.push(m.text()));
  await hp.goto(BASE + "/", { waitUntil: "networkidle" });
  await hp.getByRole("button", { name: "हिन्दी" }).click();
  await hp.screenshot({ path: `${out}home-hindi-${name}.png` });
  await hp.getByRole("button", { name: /मेरी माँ 62 साल/ }).click();
  await hp.waitForSelector("text=आप पात्र हैं", { timeout: 20000 });
  await settled(hp);
  await hp.evaluate(() => window.scrollTo(0, 0));
  await hp.screenshot({ path: `${out}chat-hindi-${name}-top.png` });
  await hp.screenshot({ path: `${out}chat-hindi-${name}-full.png`, fullPage: true });
  await hp.close();

  const p2 = await ctx.newPage();
  await p2.goto(BASE + "/schemes", { waitUntil: "networkidle" });
  await p2.screenshot({ path: `${out}schemes-${name}.png`, fullPage: true });
  await p2.goto(BASE + "/schemes/ignwps", { waitUntil: "networkidle" });
  await p2.screenshot({ path: `${out}scheme-detail-${name}.png`, fullPage: true });
  await p2.goto(BASE + "/about", { waitUntil: "networkidle" });
  await p2.screenshot({ path: `${out}about-${name}.png`, fullPage: true });
  await ctx.close();
}
await browser.close();
if (violations.length) {
  console.error("CSP violations:\n" + violations.join("\n"));
  process.exit(1);
}
