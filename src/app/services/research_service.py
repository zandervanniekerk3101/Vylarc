"""Research helpers for the Coding Canvas.

All Google API usage has been removed. Instead of doing live
web searches, we simply echo back the user's prompt as
"research context" so the AI can still generate projects.
"""

from openai import OpenAI
from src.app.config import get_settings

settings = get_settings()

try:
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
except Exception:
    openai_client = None


def perform_web_search(query: str, num_results: int = 5) -> list[dict]:  # noqa: ARG001
    """Stubbed web search.

    Returns an empty list; we no longer call Google Search.
    """

    return []


def summarize_search_results(query: str, search_results: list[dict]) -> str:  # noqa: ARG002
    """Return a lightweight research summary without external APIs.

    If OpenAI is available, we let it hallucinate a short
    technical brief from the prompt alone; otherwise we
    return a static message so the canvas flow still works.
    """

    if not openai_client:
        return (
            "External research is disabled, but you can still build this "
            f"project based on the prompt: {query}"
        )

    prompt = (
        "You are a senior technical architect. The user wants to build: "
        f"'{query}'. Without using live web data, outline a concise "
        "technical plan: key components, libraries, and steps."
    )

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful technical assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return (
            "External research is disabled, but you can still build this "
            f"project based on the prompt: {query}"
        )
