import logging
from googleapiclient.discovery import build
from openai import OpenAI
from src.app.config import get_settings

settings = get_settings()

# Initialize OpenAI
try:
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
except Exception as e:
    logging.error(f"Failed to initialize OpenAI client in research_service: {e}")
    openai_client = None

def perform_web_search(query: str, num_results: int = 5) -> list[dict]:
    """
    Performs a Google Custom Search for the given query.
    Returns a list of dicts with 'title', 'link', and 'snippet'.
    """
    if not settings.GOOGLE_SEARCH_API_KEY or not settings.GOOGLE_SEARCH_CX:
        logging.warning("Google Search API keys are missing. Skipping deep search.")
        return []

    try:
        service = build("customsearch", "v1", developerKey=settings.GOOGLE_SEARCH_API_KEY)
        res = service.cse().list(q=query, cx=settings.GOOGLE_SEARCH_CX, num=num_results).execute()
        
        items = res.get("items", [])
        results = []
        for item in items:
            results.append({
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet")
            })
        return results

    except Exception as e:
        logging.error(f"Google Search failed: {e}")
        return []

def summarize_search_results(query: str, search_results: list[dict]) -> str:
    """
    Uses OpenAI to summarize the search results into a technical briefing
    for the coding task.
    """
    if not search_results:
        return "No external research was available for this task."

    if not openai_client:
        return "AI service unavailable for summarization."

    # Prepare context
    context_text = ""
    for i, res in enumerate(search_results):
        context_text += f"Source {i+1}: {res['title']}\nURL: {res['link']}\nSummary: {res['snippet']}\n\n"

    prompt = (
        f"You are a technical researcher. The user wants to build: '{query}'.\n"
        f"Here are some search results relevant to this topic:\n\n"
        f"{context_text}\n"
        f"Synthesize this information into a concise technical guide on how to build this project. "
        f"Focus on libraries, architecture patterns, and key implementation details. "
        f"Do not write code yet, just the high-level technical approach."
    )

    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful technical assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        return completion.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"Summarization failed: {e}")
        return "Failed to summarize research results."
