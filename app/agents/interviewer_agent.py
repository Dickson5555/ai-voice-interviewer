import json
import logging
import os
from typing import List, Dict, Any

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from app.prompts.interview_prompt import SYSTEM_PROMPT
from app.schemas.response_schema import InterviewResponse

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env or Render env vars.")

_llm = ChatGroq(
    model_name= "openai/gpt-oss-120b", #"llama-3.3-70b-versatile",
    groq_api_key=GROQ_API_KEY,
    temperature=0.7,
    # Force JSON mode so the model never returns prose around the JSON.
    model_kwargs={"response_format": {"type": "json_object"}},
)

_prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)
_chain = _prompt | _llm


# Fallback used if the LLM returns malformed JSON or validation fails.
_FALLBACK_RESPONSE: Dict[str, Any] = {
    "reaction": "I couldn't quite follow that.",
    "feedback": "Try to structure your answer and explain the key idea clearly.",
    "score": 0,
    "next_question": "Can you walk me through your approach to a typical ML problem?",
}


def _format_history(history: List[str]) -> str:
    """Turn the stored message list into a readable transcript for the prompt."""
    if not history:
        return "(no prior conversation)"
    return "\n".join(history)


def process_interview(
    answer: str,
    history: List[str],
    session_id: str | None = None,
) -> Dict[str, Any]:
    """
    Evaluate the candidate's answer and produce the next interviewer turn.
    Always returns a dict matching InterviewResponse.
    """
    try:
        raw = _chain.invoke({
            "history": _format_history(history),
            "answer": answer,
        })
        content = raw.content if hasattr(raw, "content") else str(raw)
        parsed = json.loads(content)
        validated = InterviewResponse(**parsed)
        return validated.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("LLM returned invalid JSON for session %s: %s", session_id, e)
        return dict(_FALLBACK_RESPONSE)
    except Exception as e:
        logger.exception("Interviewer agent failure for session %s: %s", session_id, e)
        return dict(_FALLBACK_RESPONSE)


def start_interview() -> Dict[str, Any]:
    """Kick off the interview with a welcome + first question."""
    return {
        "reaction": "Welcome to the interview!",
        "feedback": "Relax and take your time. I'll score each answer out of 10.",
        "score": 0,
        "next_question": (
            "To start: can you tell me the difference between "
            "supervised and unsupervised learning?"
        ),
    }