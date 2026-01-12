import { test, expect } from '@playwright/test';

test.describe('Frontend SPA Verification', () => {
  test.beforeEach(async ({ page }) => {
    // Go to the app
    await page.goto('http://localhost:5173/'); // Vite default port
  });

  test('should load the app and show the chat interface', async ({ page }) => {
    // Check for a known element, e.g., the chat input or a header
    // Assuming there's an input for chat
    const chatInput = page.locator('input[type="text"]');
    await expect(chatInput).toBeVisible();

    // Check that system is ready (Agent.init sets status to idle and adds "System Ready.")
    // Depending on UI implementation, we might see "System Ready" in the thoughts or logs
    // Let's assume there is a status indicator or we wait for the input to be enabled
  });

  test('should execute a simple query', async ({ page }) => {
    const chatInput = page.locator('input[type="text"]');
    await expect(chatInput).toBeVisible();

    await chatInput.fill('Who won the championship in 2022?');
    await chatInput.press('Enter');

    // Wait for response
    // We expect some thought process or a final answer
    // This is a "smoke test" so we just want to ensure it doesn't crash
    // and produces *some* output.

    // Assuming there is a message list
    const messages = page.locator('.message');
    // Wait for at least 2 messages (user + assistant)
    await expect(messages).toHaveCount(2, { timeout: 30000 }); // Give it time to load models
  });
});
