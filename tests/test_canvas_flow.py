import sys
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append("c:\\Projects\\Vylarc")

# Mock dependencies
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["src.app.config"] = MagicMock()
# Mock fastapi package structure
mock_fastapi = MagicMock()
sys.modules["fastapi"] = mock_fastapi
sys.modules["fastapi.responses"] = MagicMock()
sys.modules["googleapiclient.discovery"] = MagicMock()
sys.modules["openai"] = MagicMock()
sys.modules["jose"] = MagicMock() # Mock jose to bypass security.py import error
sys.modules["passlib"] = MagicMock()
sys.modules["passlib.context"] = MagicMock()

from src.app.services import canvas_service, research_service

def test_canvas_flow():
    print("Testing Coding Canvas Flow...")
    
    # Mock Research Service
    research_service.perform_web_search = MagicMock(return_value=[
        {"title": "Snake Game Tutorial", "link": "http://example.com", "snippet": "Use pygame library."}
    ])
    research_service.summarize_search_results = MagicMock(return_value="Use Pygame. Create a loop.")
    
    # Mock OpenAI in Canvas Service
    # We need to mock the internal calls to openai_client.chat.completions.create
    # Since we can't easily mock the internal client variable of the imported module without patching,
    # we will patch the functions themselves or the client if accessible.
    
    # Let's patch the canvas_service functions directly for this high-level flow test
    # to verify orchestration logic.
    
    canvas_service.generate_project_structure = MagicMock(return_value=["main.py", "game.py"])
    canvas_service.generate_file_content = MagicMock(return_value="print('Hello World')")
    canvas_service.analyze_and_fix_code = MagicMock(return_value={"main.py": "print('Hello World')", "game.py": "print('Game')"})
    
    # Run the flow
    result = canvas_service.run_coding_canvas_flow("Build a snake game")
    
    # Verify
    assert result["research_summary"] == "Use Pygame. Create a loop."
    assert "main.py" in result["files"]
    assert "game.py" in result["files"]
    
    print("✅ Coding Canvas Flow Verified!")

if __name__ == "__main__":
    test_canvas_flow()
