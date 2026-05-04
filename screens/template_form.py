from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Label, Button, TextArea
from textual.containers import Vertical, Horizontal
from models import Template
from db import save_template


class TemplateForm(Screen):
    TITLE = "Edit Template"

    def __init__(self, template: Template | None = None):
        super().__init__()
        self.template = template or Template()

    def compose(self):
        yield Header()
        yield Vertical(
            Label("Template Name"),
            Input(value=self.template.name, placeholder="e.g. 傲娇女高中生", id="name_input"),
            Label("System Prompt"),
            TextArea(self.template.system_prompt, id="prompt_input"),
            Horizontal(
                Button("Save", variant="primary", id="save_btn"),
                Button("Cancel", id="cancel_btn"),
                id="btn_row",
            ),
            id="form_container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save_btn":
            name = self.query_one("#name_input", Input).value.strip()
            prompt = self.query_one("#prompt_input", TextArea).text.strip()
            if not name:
                self.notify("Name is required", severity="error")
                return
            self.template.name = name
            self.template.system_prompt = prompt
            save_template(self.template)
            self.notify(f"Template '{name}' saved")
            self.app.pop_screen()
        elif event.button.id == "cancel_btn":
            self.app.pop_screen()
