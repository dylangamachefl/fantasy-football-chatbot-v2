import { test, expect } from '@playwright/test';

test.describe('Frontend SPA Verification', () => {
  test.beforeEach(async ({ page }) => {
    // Go to the app
    await page.goto('http://localhost:5173/'); // Vite default port
  });

  test('should load the app and show the chat interface', async ({ page }) => {
    // Check for a known element, e.g., the chat input or a header
    const chatInput = page.locator('[data-testid="chat-input"]');
    await expect(chatInput).toBeVisible();

    // Check that system is ready (Agent.init sets status to Ready)
    const statusIndicator = page.locator('[data-testid="status-indicator"]');
    await expect(statusIndicator).toHaveText('Ready', { timeout: 120000 });
  });

  test('should execute a simple query', async ({ page }) => {
    const chatInput = page.locator('[data-testid="chat-input"]');
    await expect(chatInput).toBeVisible();

    await chatInput.fill('Who won the championship in 2022?');
    await chatInput.press('Enter');

    // Wait for response
    // We expect some thought process or a final answer
    // Assuming there is a message list
    const messages = page.locator('[data-testid^="message-"]');
    // Wait for at least 2 messages (user + assistant)
    await expect(messages).toHaveCount(2, { timeout: 90000 }); // Give it time to load models
  });
});
