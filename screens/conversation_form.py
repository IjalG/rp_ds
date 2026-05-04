from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Label, Button, ListView, ListItem, Select
from textual.containers import Vertical, Horizontal
from db import list_templates, save_conversation
from models import Conversation


class ConversationForm(Screen):
    TITLE = "New Conversation"

    def compose(self):
        self.templates = list_templates()
        yield Header()
        yield Vertical(
            Label("Conversation Name"),
            Input(placeholder="My Roleplay", id="name_input"),
            Label("Template"),
            ListView(*[ListItem(Label(t.name)) for t in self.templates], id="template_list"),
            Label("Mode"),
            Select(
                [(v, v) for v in ["inner_os", "no_inner_os"]],
                prompt="Select mode",
                value="inner_os",
                id="mode_select",
            ),
            Horizontal(
                Button("Create", variant="primary", id="create_btn"),
                Button("Cancel", id="cancel_btn"),
                classes="btn_row",
            ),
            id="form_container",
        )
        yield Footer()

    def on_mount(self):
        self.query_one("#template_list", ListView).index = 0 if self.templates else None

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "create_btn":
            name = self.query_one("#name_input", Input).value.strip()
            if not name:
                self.notify("Name is required", severity="error")
                return
            tid = None
            idx = self.query_one("#template_list", ListView).index
            if idx is not None and self.templates:
                tid = self.templates[idx].id
            mode = self.query_one("#mode_select", Select).value or "inner_os"
            conv = Conversation(name=name, template_id=tid, mode=mode)
            save_conversation(conv)
            self.dismiss(conv)
        elif event.button.id == "cancel_btn":
            self.dismiss(None)
