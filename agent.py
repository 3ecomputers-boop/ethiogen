import os
import google.generativeai as genai
from playwright.sync_api import sync_playwright

# Configure API Key
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Global browser instance state for the session
playwright_mgr = sync_playwright().start()
browser = playwright_mgr.chromium.launch(headless=False)
page = browser.new_page()

# Define the Python execution code for your tools
def interact_with_web(action: str, target: str, text_input: str = None):
    """Executes the actual browser controls requested by Gemini"""
    print(f"🤖 Agent Action: {action} on {target}")
    try:
        if action == "navigate":
            page.goto(target)
            return {"status": "success", "content": "Page loaded successfully."}
        elif action == "click":
            page.click(target)
            return {"status": "success", "content": f"Clicked {target}"}
        elif action == "type":
            page.fill(target, text_input)
            return {"status": "success", "content": f"Typed text into {target}"}
        elif action == "screenshot":
            page.screenshot(path=target)
            return {"status": "success", "content": f"Screenshot saved to {target}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def update_source_code(file_path: str, new_code: str):
    """Allows the agent to overwrite or fix code based on test failures"""
    print(f"💻 Agent Modifying: {file_path}")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_code)
        return {"status": "success", "message": f"Successfully updated {file_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Map tools into Gemini's configuration
model = genai.GenerativeModel(
    model_name='gemini-1.5-pro',
    tools=[interact_with_web, update_source_code]
)

# Start a chat session that retains memory of test steps
chat = model.start_chat(enable_automatic_function_calling=True)

# Example Prompt triggering the autonomous feedback loop
response = chat.send_message(
    "Go to http://localhost:3000. Test the login form by entering 'admin' and 'wrong_password'. "
    "If the page crashes or displays an error that isn't handled correctly, locate 'login.js' "
    "and update the code to handle errors gracefully."
)

print("\nFinal Agent Summary:\n", response.text)

# Clean up
browser.close()
playwright_mgr.stop()