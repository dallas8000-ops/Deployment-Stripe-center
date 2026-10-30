---
name: webapp-testing
description: >-
  Tests local web apps using Playwright — loads pages, takes screenshots, finds
  selectors, clicks through flows, and fills forms. Use when you need to verify
  UI behavior, confirm a feature works in the browser, check for visual
  regressions, or test a golden path end-to-end. Triggers on: "test this in
  the browser", "verify the UI", "screenshot the app", "click through the
  flow", "does this render correctly", or any manual QA request for a running
  web frontend.
metadata:
  short-description: Browser-test local web apps with Playwright

---

## Setup

Check for Playwright before writing any test code:

```bash
npx playwright --version 2>/dev/null || npm install -D @playwright/test && npx playwright install chromium
```

If the project has an existing test config (`playwright.config.ts` / `playwright.config.js`), read it first — don't override baseURL or timeouts that are already set.

## Process

1. **Start the dev server** if it isn't running. Look for the start command in `package.json` scripts (`dev`, `start`, `preview`). Run it in the background and wait for the port to respond:
   ```bash
   # find the port from vite/next config or package.json, default 3000 / 5173
   curl -s --retry 10 --retry-connrefused http://localhost:5173 -o /dev/null
   ```

2. **Navigate and screenshot first** — always take a baseline screenshot before interacting:
   ```ts
   await page.goto('http://localhost:5173');
   await page.screenshot({ path: 'screenshot-baseline.png', fullPage: true });
   ```

3. **Find selectors robustly** — prefer in order:
   - `getByRole` (most stable, accessibility-friendly)
   - `getByLabel`, `getByPlaceholder`, `getByText`
   - `data-testid` attributes
   - CSS selectors last (brittle — avoid `nth-child`, generated class names)

4. **Assert after every action** — don't chain clicks without checking intermediate state:
   ```ts
   await page.getByRole('button', { name: 'Submit' }).click();
   await expect(page.getByText('Success')).toBeVisible();
   ```

5. **Screenshot after key steps** — saves evidence and helps debug failures.

6. **Report findings** — list what passed, what failed, and attach screenshot paths.

## Common patterns

```ts
// Fill a form
await page.getByLabel('Email').fill('test@example.com');
await page.getByLabel('Password').fill('secret');
await page.getByRole('button', { name: 'Log in' }).click();

// Wait for navigation
await page.waitForURL('**/dashboard');

// Check a toast or alert
await expect(page.getByRole('alert')).toContainText('Saved');

// Intercept a network request
await page.route('**/api/charge', route => route.fulfill({ status: 200, body: '{}' }));
```

## Rules

- Never leave a test browser open — always `await browser.close()` or use the test runner's teardown.
- If the server isn't running and can't be started, say so clearly rather than failing silently.
- Don't write Playwright tests to files unless the user asks — run ad-hoc scripts when the goal is just to verify behavior.
- After testing, kill any background dev server you started.
