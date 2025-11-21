import logging
import json
from openai import OpenAI
from src.app.config import get_settings
from src.app.services import research_service

settings = get_settings()

# Initialize OpenAI
try:
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
except Exception as e:
    logging.error(f"Failed to initialize OpenAI client in canvas_service: {e}")
    openai_client = None

def generate_project_structure(prompt: str, research_summary: str) -> list[str]:
    """
    Generates a list of filenames for the project based on the prompt and research.
    """
    if not openai_client:
        return []

    system_prompt = (
        "You are a senior software architect. "
        "Based on the user's request and the provided technical research, "
        "output a JSON list of filenames required to build the project. "
        "Do not include directories in the list, just the full relative paths (e.g., 'src/main.py'). "
        "Only return the JSON array, no markdown."
    )
    
    user_prompt = f"User Request: {prompt}\n\nResearch Summary: {research_summary}"

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
        )
        content = completion.choices[0].message.content.strip()
        # Clean up potential markdown code blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        
        return json.loads(content)
    except Exception as e:
        logging.error(f"Failed to generate project structure: {e}")
        return []

def generate_file_content(filename: str, prompt: str, research_summary: str, file_list: list[str]) -> str:
    """
    Generates the code content for a specific file.
    """
    if not openai_client:
        return "# Error: AI service unavailable."

    system_prompt = (
        "You are an expert developer. "
        f"You are writing the file '{filename}' for a project with these files: {file_list}. "
        "Use the provided research to guide your implementation. "
        "Return ONLY the code for this file. No markdown, no explanations."
    )
    
    user_prompt = f"Project Goal: {prompt}\n\nResearch Context: {research_summary}"

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
        )
        content = completion.choices[0].message.content.strip()
        if content.startswith("```"):
            # Remove first line (```language) and last line (```)
            lines = content.split("\n")
            if len(lines) > 2:
                content = "\n".join(lines[1:-1])
        return content
    except Exception as e:
        logging.error(f"Failed to generate content for {filename}: {e}")
        return f"# Error generating content: {e}"

def analyze_and_fix_code(files: dict[str, str]) -> dict[str, str]:
    """
    Analyzes the generated code for errors and inconsistencies, and returns the fixed code.
    """
    if not openai_client:
        return files

    # Convert files dict to a string representation for the AI
    files_str = json.dumps(files, indent=2)

    system_prompt = (
        "You are a QA Lead and Senior Developer. "
        "Review the following project files for syntax errors, logical bugs, and import issues. "
        "If everything is perfect, return the JSON as is. "
        "If there are issues, fix them and return the corrected JSON object mapping filenames to content. "
        "Return ONLY the JSON."
    )

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": files_str}
            ],
            temperature=0.2,
        )
        content = completion.choices[0].message.content.strip()
        if content.startswith("```"):
             content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        
        return json.loads(content)
    except Exception as e:
        logging.error(f"Code analysis failed: {e}")
        return files # Return original files if analysis fails

def run_coding_canvas_flow(prompt: str) -> dict:
    """
    Orchestrates the Coding Canvas flow: Search -> Build -> Analyze.
    """
    # 1. Research
    logging.info(f"Canvas: Starting research for '{prompt}'...")
    search_results = research_service.perform_web_search(prompt)
    research_summary = research_service.summarize_search_results(prompt, search_results)
    
    # 2. Plan
    logging.info("Canvas: Generating project structure...")
    file_list = generate_project_structure(prompt, research_summary)
    
    # 3. Build
    logging.info(f"Canvas: Generating {len(file_list)} files...")
    files = {}
    for filename in file_list:
        content = generate_file_content(filename, prompt, research_summary, file_list)
        files[filename] = content
        
    # 4. Analyze & Fix
    logging.info("Canvas: Analyzing and fixing code...")
    final_files = analyze_and_fix_code(files)
    
    return {
        "research_summary": research_summary,
        "files": final_files
    }
