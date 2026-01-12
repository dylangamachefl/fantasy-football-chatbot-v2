from playwright.sync_api import sync_playwright

def verify_app():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            print("Navigating to app...")
            page.goto("http://localhost:4173")

            print("Waiting for key elements...")
            # Check for header
            page.wait_for_selector("text=Local SQL Agent", timeout=10000)

            # Check for start button
            page.wait_for_selector("button:has-text('Start Engine')")

            # Check for model selector
            page.wait_for_selector("select")

            print("Taking screenshot...")
            page.screenshot(path="verification/app_start.png")
            print("Screenshot saved to verification/app_start.png")

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="verification/error.png")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_app()
