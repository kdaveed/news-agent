"""Export a Claude Code session transcript (JSONL) to readable markdown.

Usage: python3 scripts/export_claude_transcript.py <session.jsonl> <out.md> [title]

Kept verbatim: user messages, assistant text replies.
Kept, shortened: tool calls (input) and tool results (output), truncated above a limit.
Left out: model thinking, harness/system reminders, injected skill text, internal bookkeeping records.
"""
import json
import sys

TOOL_INPUT_LIMIT = 3000
TOOL_RESULT_LIMIT = 1500


def cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated, {len(text) - limit} more characters]"


def is_harness(text: str) -> bool:
    t = text.lstrip()
    return t.startswith("<system-reminder>") or t.startswith("<ide_") or t.startswith("<browser_instruction>")


def result_text(block) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", f"[{x.get('type')}]") for x in c)
    return ""


def main(src, out, title):
    lines = [f"# {title}", "",
             "Exported from the Claude Code session log. User messages and assistant replies are verbatim.",
             f"Tool inputs are cut at {TOOL_INPUT_LIMIT} and tool results at {TOOL_RESULT_LIMIT} characters.",
             "Model thinking, harness reminders and injected skill text are left out.", ""]
    n_user = 0
    for raw in open(src):
        d = json.loads(raw)
        kind, ts = d.get("type"), d.get("timestamp", "")[:16].replace("T", " ")
        if kind not in ("user", "assistant"):
            continue
        content = d["message"]["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        for b in blocks:
            bt = b.get("type")
            if kind == "user" and bt == "text":
                text = b["text"]
                if is_harness(text):
                    continue
                if text.startswith("Base directory for this skill"):
                    lines += [f"[skill loaded, {ts} UTC]", ""]
                    continue
                if text.startswith("<task-notification>"):
                    lines += [f"## [background agent finished, {ts} UTC]", "", cut(text, TOOL_RESULT_LIMIT), ""]
                    continue
                n_user += 1
                lines += [f"## User {n_user} ({ts} UTC)", "", text, ""]
            elif kind == "user" and bt == "tool_result":
                lines += ["Tool result:", "", "~~~", cut(result_text(b), TOOL_RESULT_LIMIT), "~~~", ""]
            elif kind == "assistant" and bt == "text" and b["text"].strip():
                lines += ["### Assistant", "", b["text"], ""]
            elif kind == "assistant" and bt == "tool_use":
                inp = json.dumps(b.get("input", {}), ensure_ascii=False, indent=1)
                lines += [f"Tool call: {b.get('name')}", "", "~~~", cut(inp, TOOL_INPUT_LIMIT), "~~~", ""]
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"{out}: {n_user} user messages, {len(lines)} lines")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "Claude transcript")
