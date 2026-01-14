import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const CSV_PATH = path.join(__dirname, '../../shared/test_set_conversations.csv');
const RESULTS_PATH = path.join(__dirname, '../../eval_results/raw_frontend_results.json');

function parseCsv(content: string) {
  const lines = content.trim().split('\n');
  const headers = lines[0].split(',');
  return lines.slice(1).map(line => {
    // Basic CSV split that handles some quotes, but this file seems simple
    const parts = line.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/);
    const obj: any = {};
    headers.forEach((h, i) => {
      obj[h.trim()] = parts[i]?.replace(/^"|"$/g, '').trim();
    });
    return obj;
  });
}

test.describe('E2E Frontend Evaluation', () => {
  const testCases = parseCsv(fs.readFileSync(CSV_PATH, 'utf-8'));
  const results: any[] = [];

  test.afterAll(async () => {
    if (!fs.existsSync(path.dirname(RESULTS_PATH))) {
      fs.mkdirSync(path.dirname(RESULTS_PATH), { recursive: true });
    }
    fs.writeFileSync(RESULTS_PATH, JSON.stringify(results, null, 2));
    console.log(`Saved ${results.length} results to ${RESULTS_PATH}`);
  });

  test('should process all conversations and capture data', async ({ page }) => {
    test.setTimeout(600000); // 10 minutes for full suite
    await page.goto('http://localhost:5173/');

    // Wait for system ready
    await expect(page.locator('[data-testid="status-indicator"]')).toHaveText('Ready', { timeout: 120000 });

    for (const tc of testCases) {
      console.log(`Testing: ${tc.question}`);
      const chatInput = page.locator('[data-testid="chat-input"]');

      // If it's a new conversation, we might want to refresh, 
      // but for multi-turn (turn_id > 1) we stay.
      if (tc.turn_id === '1') {
        await page.reload();
        await expect(page.locator('[data-testid="status-indicator"]')).toHaveText('Ready', { timeout: 120000 });
      }

      await chatInput.fill(tc.question);
      await chatInput.press('Enter');

      // Wait for status to return to 'Ready' (Idle)
      await expect(page.locator('[data-testid="status-indicator"]')).toHaveText('Ready', { timeout: 60000 });

      // Scrape last message
      const messages = page.locator('[data-testid^="message-"]');
      const lastMessage = messages.last();
      const answer = await lastMessage.locator('[data-testid="message-content"]').textContent();

      // Scrape SQL if present
      const sqlElement = lastMessage.locator('[data-testid="message-sql"]');
      let sql = "";
      if (await sqlElement.count() > 0) {
        sql = await sqlElement.textContent() || "";
      }

      results.push({
        ...tc,
        actual_answer: answer,
        actual_sql: sql
      });
    }
  });
});
