from playwright.sync_api import Page, expect, sync_playwright
import time

def verify_chat(page: Page):
    # 1. Navigate to Streamlit
    print("Navigating to frontend...")
    page.goto("http://localhost:8501")

    # 2. Wait for app to load (Streamlit sometimes takes a moment)
    print("Waiting for title...")
    # Streamlit usually puts the title in an h1
    expect(page.get_by_role("heading", name="Fantasy Football Chatbot")).to_be_visible(timeout=20000)

    # 3. Find Chat Input
    print("Finding chat input...")
    # Streamlit chat input is usually a textarea or input with specific attributes.
    # Using get_by_placeholder if possible, or just get_by_role
    # The app code has: st.chat_input("Ask me about fantasy football...")
    chat_input = page.get_by_placeholder("Ask me about fantasy football...")
    expect(chat_input).to_be_visible()

    # 4. Type and Submit
    print("Sending message...")
    chat_input.fill("Who won the championship in 2020?")
    chat_input.press("Enter")

    # 5. Wait for Response
    print("Waiting for response...")
    # The response will appear in a chat message.
    # The "running" state might show a spinner. We want to wait for text.
    # The response we expect (from my previous curl test) is "I couldn't find..."

    # We look for the assistant's avatar or just the text content appearing in the chat container
    # Streamlit chat messages have a specific structure, but we can just search for text.
    expect(page.get_by_text("I couldn't find")).to_be_visible(timeout=30000)

    print("Response found!")

    # 6. Screenshot
    page.screenshot(path="verification/verification.png")
    print("Screenshot saved.")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        try:
            verify_chat(page)
        except Exception as e:
            print(f"Test failed: {e}")
            page.screenshot(path="verification/error.png")
        finally:
            browser.close()
