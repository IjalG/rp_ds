from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Label, Button
from textual.containers import Vertical, Horizontal
from db import get_setting, set_setting


class SettingsScreen(Screen):
    TITLE = "Settings"

    def compose(self):
        yield Header()
        yield Vertical(
            Label("API Key"),
            Input(
                placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                password=True,
                value=get_setting("api_key"),
                id="api_key_input",
            ),
            Label("API Base URL"),
            Input(
                placeholder="https://api.deepseek.com/v1",
                value=get_setting("api_base", "https://api.deepseek.com/v1"),
                id="api_base_input",
            ),
            Label("Model"),
            Input(
                placeholder="deepseek-v4-flash",
                value=get_setting("model", "deepseek-v4-flash"),
                id="model_input",
            ),
            Horizontal(
                Button("Save", variant="primary", id="save_btn"),
                Button("Back", id="back_btn"),
                classes="btn_row",
            ),
            id="settings_container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save_btn":
            for key, wid in [("api_key", "api_key_input"), ("api_base", "api_base_input"), ("model", "model_input")]:
                val = self.query_one(f"#{wid}", Input).value
                set_setting(key, val)
            self.notify("Settings saved")
        elif event.button.id == "back_btn":
            self.app.pop_screen()
