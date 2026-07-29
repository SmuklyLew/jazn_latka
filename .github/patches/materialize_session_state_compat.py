from __future__ import annotations

from pathlib import Path


path = Path("latka_jazn/core/runtime_session.py")
text = path.read_text(encoding="utf-8")

old_import = "from __future__ import annotations\nfrom dataclasses import asdict\n"
new_import = "from __future__ import annotations\n\nimport inspect\nfrom dataclasses import asdict\n"
if text.count(old_import) != 1:
    raise SystemExit("unexpected runtime_session import block")
text = text.replace(old_import, new_import, 1)

old_anchor = 'SCHEMA_VERSION = schema_version("runtime_session")\n\nclass JaznRuntimeSession:'
new_anchor = '''SCHEMA_VERSION = schema_version("runtime_session")


def _update_runtime_session_state(
    state: Any,
    *,
    user_text: str,
    visible_text: str,
    intent: str,
    route: str,
) -> None:
    """Update canonical and minimal session-state implementations compatibly.

    The canonical RuntimeSessionState accepts ``visible_text`` and persists it as
    ``last_visible_text``. A few integrity tests intentionally use a minimal state
    double with the older ``update(user_text, intent, route)`` signature. Detect
    support before calling instead of converting a valid runtime turn into a
    TypeError. Minimal mutable states still receive ``last_visible_text`` when
    possible, preserving live-turn continuity without weakening canonical writes.
    """

    update = getattr(state, "update")
    kwargs: dict[str, Any] = {
        "user_text": user_text,
        "intent": intent,
        "route": route,
    }
    try:
        parameters = inspect.signature(update).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    supports_visible_text = any(
        parameter.name == "visible_text"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    if supports_visible_text:
        kwargs["visible_text"] = visible_text
    update(**kwargs)
    if not supports_visible_text:
        try:
            setattr(state, "last_visible_text", visible_text)
        except (AttributeError, TypeError):
            pass


class JaznRuntimeSession:'''
if text.count(old_anchor) != 1:
    raise SystemExit("unexpected JaznRuntimeSession anchor")
text = text.replace(old_anchor, new_anchor, 1)

old_call = '''                self.state.update(
                    user_text=user_text,
                    visible_text=str(result.get("final_visible_text") or ""),
                    intent=str(decision.get("detected_user_intent") or "unknown"),
                    route=str(decision.get("route") or "unknown"),
                )'''
new_call = '''                _update_runtime_session_state(
                    self.state,
                    user_text=user_text,
                    visible_text=str(result.get("final_visible_text") or ""),
                    intent=str(decision.get("detected_user_intent") or "unknown"),
                    route=str(decision.get("route") or "unknown"),
                )'''
if text.count(old_call) != 1:
    raise SystemExit("unexpected state.update block")
text = text.replace(old_call, new_call, 1)

path.write_text(text, encoding="utf-8")
print({"updated": str(path), "compat_helper": True})
