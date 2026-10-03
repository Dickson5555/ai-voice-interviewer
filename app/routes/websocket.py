"""
WebSocket endpoint for the AI voice interview.

Message contract (client -> server):
  { "action": "start" }
  { "action": "answer", "message": "<transcript>" }
  { "action": "reset" }
  { "action": "end" }

Server -> client:
  { "type": "interview", "reaction": ..., "feedback": ..., "score": ..., "next_question": ... }
  { "type": "error", "message": "..." }
  { "type": "ended", "message": "..." }
"""
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.interviewer_agent import process_interview, start_interview
from app.services.memory_service import memory_store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    logger.info("WebSocket connected: %s", session_id)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            # ---------- START ----------
            if action == "start":
                result = start_interview()
                memory_store.add_message(session_id, "AI", result["next_question"])
                await websocket.send_json({"type": "interview", **result})

            # ---------- ANSWER ----------
            elif action == "answer":
                user_answer = (data.get("message") or "").strip()
                if not user_answer:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Empty answer received.",
                    })
                    continue

                history = memory_store.get_history(session_id)
                memory_store.add_message(session_id, "Candidate", user_answer)

                result = process_interview(
                    answer=user_answer,
                    history=history,
                    session_id=session_id,
                )
                memory_store.add_message(session_id, "AI", result["next_question"])

                await websocket.send_json({"type": "interview", **result})

            # ---------- RESET ----------
            elif action == "reset":
                memory_store.clear_session(session_id)
                result = start_interview()
                memory_store.add_message(session_id, "AI", result["next_question"])
                await websocket.send_json({"type": "interview", **result})

            # ---------- END ----------
            elif action == "end":
                history = memory_store.get_history(session_id)
                memory_store.clear_session(session_id)
                await websocket.send_json({
                    "type": "ended",
                    "message": "Interview ended. Thanks for participating!",
                    "turns": len(history),
                })
                logger.info("Interview ended for %s (%d turns)", session_id, len(history))
                break

            # ---------- UNKNOWN ----------
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action!r}",
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", session_id)
    except Exception as e:
        logger.exception("WebSocket error for %s: %s", session_id, e)
        try:
            await websocket.send_json({"type": "error", "message": "Server error."})
        except Exception:
            pass
    finally:
        # Always clean up on disconnect to avoid a leak.
        memory_store.clear_session(session_id)