import re
from textual.widgets import Static
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from rich.text import Text
from rich.panel import Panel
from rich.markup import escape


def parse_body(text: str):
    """Parse AI body text: extract parenthesized actions, render as『』blocks."""
    parts = []
    last_end = 0
    for m in re.finditer(r"（[^）]*）|\([^)]*\)", text):
        if m.start() > last_end:
            seg = text[last_end : m.start()]
            parts.append(("text", seg))
        parts.append(("action", m.group()))
        last_end = m.end()
    if last_end < len(text):
        parts.append(("text", text[last_end:]))
    return parts


def render_body(text: str) -> Text:
    t = Text()
    for i, (typ, seg) in enumerate(parse_body(text)):
        if typ == "action":
            t.append(f"『{seg[1:-1]}』\n", style="italic grey")
        else:
            t.append(escape(seg) + "\n")
    return t


def parse_think(text: str):
    """Extract parenthesized inner thoughts from think content."""
    thoughts = []
    for m in re.finditer(r"（[^）]*）|\([^)]*\)", text):
        thoughts.append(m.group())
    return thoughts


class MessageWidget(Static):
    def __init__(self, message, mode: str = "inner_os", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.mode = mode

    def on_mount(self):
        self.render_content()

    def render_content(self):
        m = self.message
        if m.role == "user":
            self.update(Panel(escape(m.content), title="You", border_style="blue"))
        else:
            if self.mode == "inner_os" and m.think_content:
                thoughts = parse_think(m.think_content)
                think_blocks = "\n".join(
                    f"[dim]{t}[/dim]"
 for t in thoughts
                ) if thoughts else ""
            else:
                think_blocks = ""

            body = render_body(m.content)
            if think_blocks:
                content = Text.assemble(
                    Text.from_markup(think_blocks + "\n\n"),
                    body,
                )
            else:
                content = body

            self.update(Panel(content, title="AI", border_style="green"))
