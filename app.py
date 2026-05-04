from textual.app import App
from textual.widgets import Header, Footer
from db import init_db
from screens.chat import ChatScreen


class RPDsApp(App):
    TITLE = "RP DS"
    CSS_PATH = None

    CSS = """
Screen {
    layout: vertical;
}

#sidebar {
    width: 30;
    min-width: 20;
    max-width: 40;
    border-right: solid $primary;
    padding: 0 1;
}

#sidebar_title {
    padding: 1 0;
    text-align: center;
}

#conv_list {
    height: 1fr;
}

.sidebar_btn_row {
    height: 3;
    align: center middle;
}

#right_panel {
    width: 1fr;
    height: 1fr;
}

#content_row {
    height: 1fr;
}

#msg_area {
    width: 1fr;
    height: 1fr;
    overflow-y: auto;
    padding: 0 1;
}

#think_panel {
    width: 40;
    min-width: 30;
    max-width: 50;
    border-left: solid yellow;
    padding: 0 1;
    overflow-y: auto;
}

#input_bar {
    dock: bottom;
    margin: 0 1 1 1;
}

#form_container, #settings_container, #main_container {
    padding: 1 2;
}

#form_container Label, #settings_container Label {
    margin-top: 1;
}

#form_container Input, #settings_container Input, #form_container TextArea {
    width: 100%;
}

#form_container TextArea {
    height: 12;
}

#btn_row, .btn_row {
    height: 3;
    align: center middle;
    margin-top: 1;
}

#template_list {
    height: 8;
    border: solid $primary;
}

#title {
    text-align: center;
    padding: 1 0;
}

#settings_container Input {
    margin-bottom: 1;
}

Select {
    width: 100%;
}
"""

    def on_mount(self):
        init_db()
        self.push_screen(ChatScreen())
