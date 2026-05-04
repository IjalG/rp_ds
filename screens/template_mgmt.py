from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, ListView, ListItem, Label, Button
from textual.containers import Horizontal, Vertical
from db import list_templates, delete_template
from screens.template_form import TemplateForm


class TemplateMgmt(Screen):
    TITLE = "Template Management"

    def compose(self):
        yield Header()
        yield Vertical(
            Label("[bold]Templates[/bold]", id="title"),
            ListView(id="template_list"),
            Horizontal(
                Button("New", variant="primary", id="new_btn"),
                Button("Edit", id="edit_btn"),
                Button("Delete", variant="error", id="del_btn"),
                Button("Back", id="back_btn"),
                id="btn_row",
            ),
            id="main_container",
        )
        yield Footer()

    def on_screen_resume(self):
        self.refresh_list()

    def on_mount(self):
        self.refresh_list()

    def refresh_list(self):
        lv = self.query_one("#template_list", ListView)
        lv.clear()
        self.templates = list_templates()
        for t in self.templates:
            lv.append(ListItem(Label(f"{t.name}")))
        if self.templates:
            lv.index = 0

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "new_btn":
            self.app.push_screen(TemplateForm())
        elif event.button.id == "edit_btn":
            self.edit_selected()
        elif event.button.id == "del_btn":
            self.delete_selected()
        elif event.button.id == "back_btn":
            self.app.pop_screen()

    def get_selected(self):
        idx = self.query_one("#template_list", ListView).index
        if idx is None or not self.templates:
            self.notify("No template selected", severity="warning")
            return None
        return self.templates[idx]

    def edit_selected(self):
        t = self.get_selected()
        if t:
            self.app.push_screen(TemplateForm(t))

    def delete_selected(self):
        t = self.get_selected()
        if t:
            delete_template(t.id)
            self.notify(f"Deleted '{t.name}'")
            self.refresh_list()
