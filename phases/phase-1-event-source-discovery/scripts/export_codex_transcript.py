"""Export a Codex session log (rollout JSONL) to readable markdown.

Usage: python3 scripts/export_codex_transcript.py <rollout.jsonl> <out.md> [title] [start_user]
start_user: first user message number to include (for one phase of a session).

Kept verbatim: user messages, assistant messages (including Codex's progress commentary).
Kept, shortened: tool calls, tool outputs, web searches (queries only), file patches (path only).
Left out: system/developer instructions, environment context, encrypted reasoning, token
accounting, and session metadata (which contains account IDs).
"""
import json
import sys

TOOL_INPUT_LIMIT = 3000
TOOL_RESULT_LIMIT = 1500


def cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated, {len(text) - limit} more characters]"


def main(src, out, title, start_user=1):
    lines = [f"# {title}", "",
             "Exported from the Codex session log. User and assistant messages are verbatim.",
             f"Tool inputs are cut at {TOOL_INPUT_LIMIT} and tool outputs at {TOOL_RESULT_LIMIT} characters.",
             "System instructions, environment context, reasoning, token accounting and account metadata are left out.", ""]
    n_user = 0
    for raw in open(src):
        d = json.loads(raw)
        t, p = d.get("type"), d.get("payload") or {}
        pt, ts = p.get("type"), d.get("timestamp", "")[:16].replace("T", " ")
        if t == "event_msg" and pt == "user_message":
            n_user += 1
        if n_user < start_user:
            continue
        if t == "event_msg" and pt == "user_message":
            lines += [f"## User {n_user} ({ts} UTC)", "", p.get("message", ""), ""]
        elif t == "event_msg" and pt == "agent_message":
            lines += ["### Assistant", "", p.get("message", ""), ""]
        elif t == "event_msg" and pt == "turn_aborted":
            lines += [f"[turn interrupted by user, {ts} UTC]", ""]
        elif t == "event_msg" and pt == "web_search_end":
            qs = (p.get("action") or {}).get("queries") or [p.get("query", "")]
            lines += ["Web search: " + " | ".join(q for q in qs if q), ""]
        elif t == "event_msg" and pt == "patch_apply_end":
            lines += ["File change: " + ", ".join(f"{v.get('type')} {k}" for k, v in (p.get("changes") or {}).items()), ""]
        elif t == "response_item" and pt == "custom_tool_call":
            lines += [f"Tool call: {p.get('name')}", "", "~~~", cut(str(p.get("input", "")), TOOL_INPUT_LIMIT), "~~~", ""]
        elif t == "response_item" and pt == "custom_tool_call_output":
            o = p.get("output")
            text = "\n".join(x.get("text", "") for x in o) if isinstance(o, list) else str(o)
            lines += ["Tool output:", "", "~~~", cut(text, TOOL_RESULT_LIMIT), "~~~", ""]
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"{out}: {n_user} user messages, {len(lines)} lines")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "Codex transcript",
         int(sys.argv[4]) if len(sys.argv) > 4 else 1)
