import time
from playwright.sync_api import sync_playwright, expect

def verify_chat_streaming():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            print("Navigating to Streamlit app...")
            page.goto("http://localhost:8501")

            # Wait for the app to load
            print("Waiting for title...")
            expect(page.get_by_role("heading", name="Fantasy Football Chatbot 🏈")).to_be_visible(timeout=15000)

            # Click a suggested question to trigger a chat
            print("Clicking suggested question...")
            # The suggested questions are buttons. Let's pick the first one.
            # "🏆 Who won the 2020 championship?" is in a button
            # Streamlit buttons are tricky, they are usually <button>
            # We look for the button with text partial match
            page.get_by_role("button", name="Who won the 2020 championship?").click()

            # Wait for the response
            # The response appears in a markdown element.
            print("Waiting for response...")
            # We expect the assistant message to appear.
            # Streamlit chat messages have specific classes, but text content is easier.
            # The backend returns "Hi there" or similar if it fails, or the actual answer.
            # We just wait for something new to appear.
            time.sleep(5)

            # Check for "Feedback recorded" or just buttons
            # We want to see the message.

            # Take screenshot
            print("Taking screenshot...")
            page.screenshot(path="/home/jules/verification/streaming_test.png", full_page=True)

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="/home/jules/verification/error_state.png")
            raise e
        finally:
            browser.close()

if __name__ == "__main__":
    verify_chat_streaming()
