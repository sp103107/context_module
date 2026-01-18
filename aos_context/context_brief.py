from __future__ import annotations

from typing import Any, Dict, List, Optional


def render_context_brief(
    ws: Dict[str, Any],
    *,
    ltm_results: Optional[List[Dict[str, Any]]] = None,
    min_confidence: float = 0.8,
) -> str:
    """Render a deterministic, model-friendly Context Brief.

    Do not dump raw JSON. Provide consistent headings.
    """

    ltm_results = ltm_results or []

    lines: List[str] = []
    lines.append("# CONTEXT BRIEF")
    lines.append("")
    lines.append("## 1. OBJECTIVE")
    lines.append(ws.get("objective", "").strip() or "(unset)")
    lines.append("")

    lines.append("## 2. ACCEPTANCE CRITERIA")
    for ac in ws.get("acceptance_criteria", []) or []:
        lines.append(f"- {ac}")
    if not ws.get("acceptance_criteria"):
        lines.append("- (none)")
    lines.append("")

    lines.append("## 3. CONSTRAINTS & BUDGETS")
    for c in ws.get("constraints", []) or []:
        lines.append(f"- {c}")
    if not ws.get("constraints"):
        lines.append("- (none)")
    lines.append("")

    lines.append("## 4. PINNED CONTEXT")
    pinned = ws.get("pinned_context", []) or []
    if pinned:
        for item in pinned:
            if isinstance(item, dict):
                content = str(item.get("content", "")).strip()
                sid = str(item.get("id", "")).strip()
                sr = str(item.get("source_ref", "")).strip()
                suffix = f" (id={sid})" if sid else ""
                if sr:
                    suffix += f" source={sr}"
                lines.append(f"- {content}{suffix}")
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## 5. RECENT / SLIDING CONTEXT")
    sliding = ws.get("sliding_context", []) or []
    if sliding:
        for item in sliding:
            if isinstance(item, dict):
                content = str(item.get("content", "")).strip()
                pri = item.get("priority", 0)
                ts = item.get("timestamp", "")
                lines.append(f"- {content} (pri={pri} ts={ts})")
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## 6. RETRIEVED LONG-TERM MEMORY")
    shown = 0
    for mem in ltm_results:
        try:
            conf = float(mem.get("confidence", 0))
        except Exception:
            conf = 0.0
        if conf < min_confidence:
            continue
        content = str(mem.get("content", "")).strip()
        mid = str(mem.get("memory_id", "")).strip()
        lines.append(f"- {content} (memory_id={mid} conf={conf:.2f})")
        shown += 1
    if shown == 0:
        lines.append("- (none)")
    lines.append("")

    lines.append("## 7. STATUS")
    lines.append(f"- status: {ws.get('status','')}")
    lines.append(f"- stage: {ws.get('current_stage','')}")
    lines.append(f"- next_action: {ws.get('next_action','')}")
    if ws.get("blockers"):
        lines.append("- blockers:")
        for b in ws.get("blockers", []):
            lines.append(f"  - {b}")
    else:
        lines.append("- blockers: (none)")

    return "\n".join(lines).strip() + "\n"
