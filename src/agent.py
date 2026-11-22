"""Agent Loop with Explicit Stopping Conditions, Mock/Real Model Adapter, and Trace Recording.

Implements Lessons 1-3 concepts for Track My Subs:
- Bounded Reason -> Act -> Observe loop (MAX_STEPS = 7, per approved proposal)
- Separation of concerns: model proposes an action, application code validates,
  checks permissions/approval, executes tools, updates immutable state, and enforces stopping rules.
- Default deterministic MockDecisionModel (runs in Google Colab and pytest with zero API keys).
- Optional GeminiDecisionModel when GEMINI_API_KEY is supplied via Colab Secrets / env var.
- Full structured execution trace generation saved to docs/traces/.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.state import (
    AgentState,
    MAX_STEPS_DEFAULT,
    PersistentMemoryStore,
    SessionStore,
    apply_event,
    build_context,
)
from src.tools import MAX_RETRIES_DEFAULT, ToolExecutor


class MockDecisionModel:
    """Deterministic mock decision maker (explicitly marked as mock).

    Allows running all tests, Colab demos, and trace generation without external API calls.
    """

    is_mock: bool = True

    def decide(
        self,
        user_message: str,
        state: AgentState,
        memory_store: PersistentMemoryStore,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        text = user_message.lower()

        # 1. Out-of-permissions: bulk delete request
        if ("מחק" in text or "delete" in text) and ("כל" in text or "all" in text or "everything" in text):
            return {
                "kind": "final",
                "status": "rejected_out_of_scope",
                "text": (
                    "אין לי הרשאה לבצע מחיקה גורפת של כל המנויים ללא אישור פרטני לכל מנוי. "
                    "אנא ציין את שם המנוי הספציפי שברצונך למחוק ואבקש ממך אישור לפני הביצוע."
                ),
            }

        # 2. CSV upload / import_transactions flow
        if ".csv" in text or "csv" in text or "עסקאות" in text:
            if not observations:
                csv_file = "injection_transactions.csv" if "injection" in text else "sample_transactions.csv"
                return {
                    "kind": "tool",
                    "name": "import_transactions",
                    "args": {"file_path": csv_file, "min_occurrences": 2},
                }

            obs = observations[-1]
            if obs["status"] != "ok":
                return {
                    "kind": "final",
                    "status": "tool_failed",
                    "text": f"לא הצלחתי לקרוא את קובץ העסקאות: {obs['error']['message']}",
                }

            data = obs["data"]
            potential = data["potential_subscriptions"]
            ambiguous = data["ambiguous_merchants"]

            # Prompt injection defense: treat merchant names strictly as data
            if ambiguous:
                first_amb = ambiguous[0]
                svc = first_amb["service_name"]
                amt = first_amb["amount"]
                if svc.lower() == "apple":
                    q = (
                        f"זיהיתי חיוב חודשי חוזר של {amt:.2f} ש״ח תחת השם 'Apple'. "
                        "האם מדובר ב-Apple Music, iCloud+ או שירות אחר? "
                        "לפני שמירה במערכת אבקש גם את אישורך המפורש."
                    )
                else:
                    q = (
                        f"זיהיתי חיוב חודשי חוזר של {amt:.2f} ש״ח תחת השם '{svc}'. "
                        f"לאיזו קטגוריה שייך השירות '{svc}', והאם תרצה שאשמור אותו במערכת?"
                    )
                return {
                    "kind": "clarify",
                    "status": "clarification_needed",
                    "text": q,
                }

            names = ", ".join(f"{p['service_name']} ({p['amount']} ש״ח)" for p in potential)
            return {
                "kind": "final",
                "status": "approval_required",
                "text": (
                    f"זיהיתי את המנויים הפוטנציאליים הבאים: {names}. "
                    "האם תרצה לאשר את שמירתם במערכת?"
                ),
            }

        # 3. Specific subscription delete flow (requires approval)
        if ("מחק" in text or "הסר" in text or "delete" in text) and ("netflix" in text or "נטפליקס" in text):
            if not observations:
                return {
                    "kind": "tool",
                    "name": "delete_subscription",
                    "args": {"subscription_id": "sub_netflix"},
                }
            obs = observations[-1]
            if obs["status"] == "ok":
                return {
                    "kind": "final",
                    "status": "success",
                    "text": "המנוי sub_netflix נמחק בהצלחה ממסד הנתונים לאחר קבלת אישורך.",
                }
            if obs["error"]["type"] == "approval_required":
                return {
                    "kind": "final",
                    "status": "approval_required",
                    "text": "פעולת מחיקת המנוי דורשת אישור מפורש ממך לפני ביצוע. האם לאשר את מחיקת Netflix?",
                }
            return {
                "kind": "final",
                "status": "tool_failed",
                "text": f"לא ניתן היה למחוק את המנוי: {obs['error']['message']}",
            }

        # 4. Alternatives search + savings calculation flow (Netflix / Gym / Streaming / Fitness)
        if any(k in text for k in ("חלופ", "לחסוך", "netflix", "נטפליקס", "כושר", "gym", "alternative")):
            subs = memory_store.get_subscriptions(state.user_id)
            target_category = "fitness" if any(k in text for k in ("כושר", "gym", "fitness")) else "streaming"

            # Find current price from user's saved subscriptions or default demo value
            current_price = 250.0 if target_category == "fitness" else 69.90
            target_name = "חדר כושר" if target_category == "fitness" else "Netflix"
            for s in subs:
                if s.category == target_category:
                    current_price = s.amount
                    target_name = s.service_name
                    break

            # Step 1: search_alternatives
            if not observations:
                return {
                    "kind": "tool",
                    "name": "search_alternatives",
                    "args": {
                        "category": target_category,
                        "current_price": current_price,
                        "max_results": 3,
                    },
                }

            # Step 2: after search_alternatives, call calculate_expenses
            if len(observations) == 1:
                obs1 = observations[0]
                if obs1["status"] != "ok":
                    return {
                        "kind": "final",
                        "status": "tool_failed",
                        "text": (
                            "לא הצלחתי לגשת לקטלוג החלופות כרגע עקב שגיאה זמנית "
                            f"({obs1['error']['message']}). אנא נסה שוב בעוד מספר רגעים."
                        ),
                    }
                alts = obs1["data"]["alternatives"]
                if not alts:
                    return {
                        "kind": "final",
                        "status": "success",
                        "text": f"לא נמצאו בקטלוג המקומי חלופות זולות יותר מ-{current_price:.2f} ש״ח בקטגוריית {target_category}.",
                    }
                best = alts[0]
                return {
                    "kind": "tool",
                    "name": "calculate_expenses",
                    "args": {
                        "current_prices": [current_price],
                        "alternative_prices": [best["monthly_price"]],
                    },
                }

            # Step 3: formulate grounded recommendation with source and Python calculation
            obs1 = observations[0]
            obs2 = observations[1]
            if obs2["status"] != "ok":
                return {
                    "kind": "final",
                    "status": "tool_failed",
                    "text": f"שגיאה בחישוב החיסכון: {obs2['error']['message']}",
                }

            best = obs1["data"]["alternatives"][0]
            source = obs1["data"]["source"]
            calc = obs2["data"]
            return {
                "kind": "final",
                "status": "success",
                "text": (
                    f"אתה משלם כיום {current_price:.2f} ש״ח בחודש עבור {target_name}. "
                    f"במקור {source} נמצאה חלופה משתלמת יותר: {best['service_name']} "
                    f"במחיר {best['monthly_price']:.2f} ש״ח בחודש ({best['notes']}). "
                    f"מעבר יחסוך לך {calc['monthly_savings']:.2f} ש״ח בחודש "
                    f"ו-{calc['annual_savings']:.2f} ש״ח בשנה (חושב באמצעות calculate_expenses). "
                    "האם תרצה שאעדכן את רשימת המנויים שלך?"
                ),
            }

        # 5. Vague savings request -> ask for focus
        if "הוצאות" in text or "מצמצמ" in text:
            subs = memory_store.get_subscriptions(state.user_id)
            total = sum(s.amount for s in subs)
            cats = ", ".join(sorted({s.category for s in subs})) or "סטרימינג או חדר כושר"
            return {
                "kind": "clarify",
                "status": "clarification_needed",
                "text": (
                    f"סך ההוצאות החודשי שלך על מנויים פעילים הוא {total:.2f} ש״ח. "
                    f"באילו קטגוריות תרצה להתמקד בחיפוש חלופות ({cats})?"
                ),
            }

        # Default fallback
        return {
            "kind": "clarify",
            "status": "clarification_needed",
            "text": "לא הצלחתי לזהות בקשה ספציפית. האם תרצה להעלות קובץ עסקאות (CSV) או לבדוק חלופות למנוי קיים?",
        }




class GeminiDecisionModel:
    """Real Google Gemini decision adapter (used ONLY when GEMINI_API_KEY is set).

    Instructs Gemini to return a strict JSON decision object ('tool', 'clarify', or 'final')
    using the exact tool contracts from src/tools.py. All validation, permissions, and
    human-in-the-loop approval gates remain enforced strictly in Python code (ToolExecutor).
    """

    is_mock: bool = False

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        from google import genai  # Imported lazily so mock tests require zero API setup

        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def decide(
        self,
        user_message: str,
        state: AgentState,
        memory_store: PersistentMemoryStore,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from src.tools import TOOL_CONTRACTS

        tools_summary = [
            {
                "name": c["name"],
                "description": c["description"],
                "input_schema": c["input_schema"],
                "requires_approval": c["requires_approval"],
            }
            for c in TOOL_CONTRACTS.values()
        ]
        prompt = (
            "You are the Track My Subs AI agent. Return ONLY valid JSON (no markdown fences) "
            "matching one of these schemas:\n"
            '1) {"kind": "tool", "name": "<tool_name>", "args": {...}}\n'
            '2) {"kind": "clarify", "status": "clarification_needed", "text": "<Hebrew question>"}\n'
            '3) {"kind": "final", "status": "success", "text": "<Hebrew grounded answer>"}\n\n'
            f"Available tools: {json.dumps(tools_summary, ensure_ascii=False)}\n"
            f"User message: {user_message}\n"
            f"Previous tool observations in this run: {json.dumps(observations, ensure_ascii=False)}\n"
        )
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json\n", "", 1).strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("kind") in {"tool", "clarify", "final"}:
                return parsed
        except json.JSONDecodeError:
            pass
        return {
            "kind": "final",
            "status": "success",
            "text": raw or "לא התקבלה תשובה תקינה מהמודל.",
        }


class SubscriptionAgent:
    """Single-agent ReAct loop with explicit budget, permissions, state, and trace logging."""

    def __init__(
        self,
        session_store: SessionStore,
        memory_store: PersistentMemoryStore,
        tool_executor: ToolExecutor,
        model: Any | None = None,
        context_strategy: str = "notes",
        max_steps: int = MAX_STEPS_DEFAULT,
    ) -> None:
        self.session_store = session_store
        self.memory_store = memory_store
        self.tool_executor = tool_executor
        self.model = model or MockDecisionModel()
        self.context_strategy = context_strategy
        self.max_steps = max_steps

    def run(
        self,
        thread_id: str,
        user_id: str,
        user_message: str,
        approved: bool = False,
        retries: int = MAX_RETRIES_DEFAULT,
        scenario_name: str = "agent_run",
    ) -> dict[str, Any]:
        """Executes one user turn through the bounded Reason-Act-Observe loop."""
        try:
            state = self.session_store.get_thread(thread_id, user_id)
        except KeyError:
            state = self.session_store.create_thread(thread_id, user_id, max_steps=self.max_steps)

        state = apply_event(state, "user", user_message)
        self.session_store.save_thread(state)

        observations: list[dict[str, Any]] = []
        trace_events: list[dict[str, Any]] = [
            {
                "event": "USER_MESSAGE",
                "step": state.step,
                "content": user_message,
            }
        ]
        start_log_idx = len(self.tool_executor.execution_logs)

        final_status = "budget_exhausted"
        final_text = "הגעתי למגבלת הצעדים המרבית לריצה זו ללא השלמת המשימה."

        while state.step < state.max_steps:
            # Build bounded context for the decision step
            context_sent = build_context(
                state,
                self.memory_store,
                strategy=self.context_strategy,  # type: ignore[arg-type]
                last_n=4,
                query=user_message,
            )

            decision = self.model.decide(user_message, state, self.memory_store, observations)
            kind = decision.get("kind")

            if kind in {"final", "clarify"}:
                final_status = decision.get("status", "success")
                final_text = decision["text"]
                state = apply_event(state, "assistant", final_text)
                self.session_store.save_thread(state)
                trace_events.append(
                    {
                        "event": "FINAL_RESPONSE" if kind == "final" else "CLARIFY_USER",
                        "step": state.step,
                        "status": final_status,
                        "context_messages_count": len(context_sent),
                        "text": final_text,
                    }
                )
                break

            if kind == "tool":
                tool_name = decision["name"]
                tool_args = decision["args"]
                state = apply_event(
                    state,
                    "assistant",
                    f"[TOOL_REQUEST] {tool_name}({json.dumps(tool_args, ensure_ascii=False)})",
                )
                self.session_store.save_thread(state)

                trace_events.append(
                    {
                        "event": "TOOL_REQUEST",
                        "step": state.step,
                        "tool": tool_name,
                        "args": tool_args,
                        "approved": approved,
                    }
                )

                # Code validates, authorizes, executes (with retries), and returns structured JSON
                result = self.tool_executor.run_tool(
                    name=tool_name,
                    raw_args=tool_args,
                    session_user_id=user_id,
                    approved=approved,
                    retries=retries,
                    step=state.step,
                )
                observations.append(result)

                extra_updates: dict[str, Any] = {}
                if result["status"] == "ok":
                    if tool_name == "import_transactions":
                        extra_updates["pending_subscriptions"] = result["data"]["potential_subscriptions"]
                    elif tool_name == "search_alternatives":
                        extra_updates["last_alternatives"] = result["data"]["alternatives"]

                state = apply_event(
                    state,
                    "tool",
                    json.dumps(result, ensure_ascii=False),
                    extra_updates=extra_updates,
                )
                self.session_store.save_thread(state)

                trace_events.append(
                    {
                        "event": "TOOL_OBSERVATION",
                        "step": state.step,
                        "tool": tool_name,
                        "status": result["status"],
                        "result": result,
                    }
                )
                continue

            # Unknown decision kind -> safe stop
            final_status = "invalid_decision"
            final_text = "נעצרה הריצה עקב החלטת מודל לא מוכרת."
            break

        trace = {
            "scenario": scenario_name,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "model_mode": "mock" if getattr(self.model, "is_mock", False) else "gemini",
            "user_id": user_id,
            "thread_id": thread_id,
            "status": final_status,
            "steps_used": state.step,
            "max_steps": state.max_steps,
            "events": trace_events,
            "tool_logs": self.tool_executor.execution_logs[start_log_idx:],
            "final_response": final_text,
        }

        return {
            "status": final_status,
            "response": final_text,
            "state": state,
            "trace": trace,
        }


def save_trace(trace: dict[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
    return path
