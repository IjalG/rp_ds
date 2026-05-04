import asyncio
import re
import flet as ft
from db import (
    init_db, list_templates, save_template, delete_template,
    list_conversations, save_conversation, delete_conversation,
    save_message, get_active_branch, get_setting, set_setting,
    get_template, get_conversation,
)
from models import Template, Conversation, Message
from api import stream_chat, build_messages


def main():
    init_db()
    ft.app(target=RPDsApp)


class RPDsApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "RP DS"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.width = 1200
        self.page.window.height = 800
        self.page.padding = 0

        self.current_conv: Conversation | None = None
        self.messages: list[Message] = []
        self._streaming = False
        self._think_buf = ""

        # UI refs
        self.conv_list_view = ft.ListView(spacing=2, expand=True)
        self.msg_list_view = ft.ListView(spacing=8, expand=True, auto_scroll=True)
        self.input_field = ft.TextField(
            hint_text="Type a message...",
            multiline=False,
            on_submit=self.on_input_submit,
            disabled=True,
            expand=True,
        )
        self.think_panel = ft.Container(
            visible=False,
            width=300,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.PRIMARY),
            padding=10,
            content=ft.Column([
                ft.Text("Analysis", weight=ft.FontWeight.BOLD, size=14),
                ft.Container(expand=True, content=ft.Column([], scroll=ft.ScrollMode.AUTO)),
            ]),
        )
        self._page_container = ft.Container(expand=True)
        self._msg_view_mode: dict[int, str] = {}
        self._drawer_content = ft.Container(width=280, padding=10)
        self.page.drawer = ft.NavigationDrawer(controls=[self._drawer_content])  # msg_id -> "chat" | "analysis"

        self._build_layout()
        self.refresh_conv_list()
        self._apply_theme()

        page.on_resize = self._on_resize
        page.on_keyboard_event = self.on_keyboard

    def _is_mobile(self):
        return self.page.width <= 768

    def _build_layout(self):
        self._page_container.content = self._build_mobile() if self._is_mobile() else self._build_desktop()
        if self.page.controls:
            self.page.controls[0] = self._page_container
        else:
            self.page.add(self._page_container)
        self.page.update()

    def _on_resize(self, e=None):
        self._build_layout()

    def _build_desktop(self):
        self.think_panel.width = 300
        sidebar = ft.Container(
            width=240,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.PRIMARY),
            padding=10,
            content=ft.Column([
                ft.Text("RP DS", size=20, weight=ft.FontWeight.BOLD),
                ft.Divider(height=1),
                ft.Text("Conversations", size=12, color=ft.Colors.GREY),
                self.conv_list_view,
                ft.Divider(height=1),
                ft.Row([
                    ft.ElevatedButton("+ New", icon=ft.Icons.ADD, on_click=self.new_conversation, expand=True),
                ]),
                ft.Row([
                    ft.OutlinedButton("Templates", icon=ft.Icons.DASHBOARD, on_click=self.manage_templates, expand=True),
                    ft.IconButton(icon=ft.Icons.SETTINGS, on_click=self.open_settings),
                ]),
            ]),
        )
        msg_area = ft.Container(
            expand=True,
            padding=ft.padding.only(left=20, right=20, top=10),
            content=ft.Column([self.msg_list_view]),
            bgcolor=ft.Colors.with_opacity(0.01, ft.Colors.SURFACE),
        )
        input_row = ft.Container(
            padding=ft.padding.only(left=20, right=20, bottom=10, top=5),
            content=ft.Row([self.input_field, ft.IconButton(icon=ft.Icons.SEND, on_click=self.on_send_click)]),
        )
        right_col = ft.Column([
            ft.Row([msg_area, self.think_panel], expand=True),
            input_row,
        ], expand=True, spacing=0)
        return ft.Row([sidebar, ft.VerticalDivider(width=1), right_col], expand=True, spacing=0)

    def _build_mobile(self):
        self._drawer_content.content = ft.Column([
            ft.Text("RP DS", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(height=1),
            ft.Text("Conversations", size=12, color=ft.Colors.GREY),
            self.conv_list_view,
            ft.Divider(height=1),
            ft.ElevatedButton("+ New", icon=ft.Icons.ADD, on_click=self.new_conversation, expand=True),
            ft.OutlinedButton("Templates", icon=ft.Icons.DASHBOARD, on_click=self.manage_templates, expand=True),
        ])

        def open_drawer(e):
            self.page.show_drawer()
            self.page.update()

        return ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.MENU, on_click=open_drawer),
                ft.Text("RP DS", size=18, weight=ft.FontWeight.BOLD, expand=True),
                ft.IconButton(icon=ft.Icons.SETTINGS, on_click=self.open_settings),
            ]),
            ft.Container(expand=True, padding=ft.padding.only(left=12, right=12, top=8), content=self.msg_list_view),
            ft.Container(
                padding=ft.padding.only(left=12, right=12, bottom=8, top=4),
                content=ft.Row([self.input_field, ft.IconButton(icon=ft.Icons.SEND, on_click=self.on_send_click)]),
            ),
        ], expand=True, spacing=0)

    def _switch_tab(self, tab: str):
        if tab == "chat":
            self._chat_content.visible = True
            self._analysis_content.visible = False
        else:
            self._chat_content.visible = False
            self._analysis_content.visible = True
        self.page.update()

    def refresh_conv_list(self):
        self.conv_list_view.controls.clear()
        convs = list_conversations()
        for c in convs:
            label = f"{c.name}" + (f" [{c.mode}]" if c.mode else "")
            tile = ft.Container(
                content=ft.Text(label, size=14),
                padding=10,
                border_radius=8,
                ink=True,
                data=c,
                on_click=self.on_conv_selected,
                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.PRIMARY) if self.current_conv and self.current_conv.id == c.id else None,
            )
            self.conv_list_view.controls.append(tile)
        self.page.update()

    def on_conv_selected(self, e):
        conv = e.control.data
        if conv:
            self.load_conversation(conv)

    def load_conversation(self, conv: Conversation):
        self.current_conv = conv
        self.page.title = f"RP DS - {conv.name}"
        self.input_field.disabled = False
        asyncio.create_task(self.input_field.focus())
        self.load_messages()
        self.refresh_conv_list()

    def load_messages(self):
        if not self.current_conv:
            return
        chain = get_active_branch(self.current_conv.id)
        self.messages = chain
        self.msg_list_view.controls.clear()
        last_think = ""
        for m in chain:
            self.msg_list_view.controls.append(self._build_msg_widget(m))
            if m.role == "assistant" and m.think_content:
                last_think = m.think_content
        # think panel
        show_think = self.current_conv.mode == "no_inner_os"
        self.think_panel.visible = show_think
        if show_think:
            think_col = self.think_panel.content.controls[1].content  # Column inside Container
            think_col.controls.clear()
            if last_think:
                think_col.controls.append(ft.Text(last_think, size=13, selectable=True))
        self.page.update()

    def _build_msg_widget(self, m: Message):
        if m.role == "user":
            return self._user_bubble(m.content)
        else:
            return self._ai_bubble(m.id, m.content, m.think_content)

    def _user_bubble(self, text: str):
        return ft.Container(
            content=ft.Column([
                ft.Text("You", size=11, color=ft.Colors.BLUE, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Text(text, size=14, selectable=True, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE_900,
                    border_radius=ft.border_radius.only(top_left=16, top_right=4, bottom_left=16, bottom_right=16),
                    padding=12,
                ),
            ]),
            alignment=ft.Alignment(1, 0),
            margin=ft.margin.only(left=80),
        )

    def _ai_bubble(self, msg_id: int, content: str, think: str = ""):
        is_analysis = self.current_conv and self.current_conv.mode == "no_inner_os"
        show_think = self._msg_view_mode.get(msg_id, "chat") == "analysis"
        cols = []

        if is_analysis:
            # Per-message toggle row
            def make_toggler(tab):
                def onclick(e):
                    self._msg_view_mode[msg_id] = tab
                    # Rebuild this specific message
                    idx = None
                    for i, m in enumerate(self.messages):
                        if m.id == msg_id:
                            idx = i
                            break
                    if idx is not None:
                        self.msg_list_view.controls[idx] = self._ai_bubble(msg_id, content, think)
                        self.page.update()
                return ft.TextButton(
                    tab.capitalize(),
                    on_click=onclick,
                    style=ft.ButtonStyle(
                        color=ft.Colors.PRIMARY if self._msg_view_mode.get(msg_id, "chat") == tab else ft.Colors.GREY,
                    ),
                )
            cols.append(ft.Row([
                ft.Text("AI", size=11, color=ft.Colors.GREEN, weight=ft.FontWeight.BOLD),
                ft.Text("  |  ", size=11, color=ft.Colors.GREY),
                make_toggler("chat"),
                ft.Text("  ", size=11),
                make_toggler("analysis"),
            ]))

        if show_think and think:
            cols.append(ft.Text(think, size=13, selectable=True, color=ft.Colors.GREY_300))
        elif not show_think:
            # immersion mode: show think inline
            if not is_analysis and think:
                thoughts = self._parse_think(think)
                for t in thoughts:
                    cols.append(ft.Text(t, size=12, italic=True, color=ft.Colors.GREY))
            # parsed body
            parts = self._parse_body(content)
            for typ, seg in parts:
                if typ == "action":
                    cols.append(ft.Text(f"\u300e{seg[1:-1]}\u300f", italic=True, color=ft.Colors.GREY_300, size=14))
                else:
                    cols.append(ft.Text(seg, size=14, selectable=True))

        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column(cols, spacing=2),
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                    border_radius=ft.border_radius.only(top_left=4, top_right=16, bottom_left=16, bottom_right=16),
                    padding=12,
                ),
            ]),
            alignment=ft.Alignment(-1, 0),
            margin=ft.margin.only(right=80),
        )

    def _parse_body(self, text: str):
        parts = []
        last = 0
        for m in re.finditer(r"（[^）]*）|\([^)]*\)", text):
            if m.start() > last:
                parts.append(("text", text[last:m.start()]))
            parts.append(("action", m.group()))
            last = m.end()
        if last < len(text):
            parts.append(("text", text[last:]))
        return parts

    def _parse_think(self, text: str):
        return [m.group() for m in re.finditer(r"（[^）]*）|\([^)]*\)", text)]

    # ---- Message send ----

    def on_input_submit(self, e):
        self._do_send()

    def on_send_click(self, e):
        self._do_send()

    def _do_send(self):
        if self._streaming or not self.current_conv:
            return
        text = self.input_field.value.strip()
        if not text:
            return
        self.input_field.value = ""
        self.page.update()
        asyncio.create_task(self.send_message(text))

    async def send_message(self, text: str):
        try:
            conv = self.current_conv
            parent_id = self.messages[-1].id if self.messages else None

            user_msg = Message(conversation_id=conv.id, parent_id=parent_id, role="user", content=text)
            save_message(user_msg)
            self.messages.append(user_msg)
            self.msg_list_view.controls.append(self._user_bubble(text))
            self.page.update()

            await self._stream_from_user(user_msg)
        except Exception as e:
            self._streaming = False
            _ = ft.SnackBar(ft.Text(str(e)), bgcolor=ft.Colors.RED); self.page.show_dialog(_)
            self.page.update()

    async def _stream_from_user(self, user_msg: Message):
        conv = self.current_conv
        api_key = get_setting("api_key")
        if not api_key:
            self._streaming = False
            _ = ft.SnackBar(ft.Text("API key not set"), bgcolor=ft.Colors.RED); self.page.show_dialog(_)
            self.page.update()
            return

        template = get_template(conv.template_id) if conv.template_id else None
        system_prompt = template.system_prompt if template else ""

        history = []
        idx = None
        for i, m in enumerate(self.messages):
            if m.role == "user" and m.content == user_msg.content and m.parent_id == user_msg.parent_id:
                idx = i
                break
            history.append({"role": m.role, "content": m.content})

        api_msgs = build_messages(system_prompt, history, user_msg.content, conv.mode)

        ai_msg = Message(conversation_id=conv.id, parent_id=user_msg.id, role="assistant", content="", think_content="")
        save_message(ai_msg)
        self.messages.append(ai_msg)

        # Create placeholder AI bubble
        cols = []
        if conv.mode == "inner_os":
            self._think_texts = []  # list of Text controls for thoughts
        self._action_texts = []  # list of Text controls for actions
        self._speech_text = ft.Text("", size=14, selectable=True)
        cols.append(self._speech_text)

        bubble = ft.Container(
            content=ft.Column([
                ft.Text("AI", size=11, color=ft.Colors.GREEN, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column(cols, spacing=2),
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                    border_radius=ft.border_radius.only(top_left=4, top_right=16, bottom_left=16, bottom_right=16),
                    padding=12,
                ),
            ]),
            alignment=ft.Alignment(-1, 0),
            margin=ft.margin.only(right=80),
        )
        self.msg_list_view.controls.append(bubble)
        self.page.update()

        self._streaming = True
        content_buf = ""
        think_buf = ""

        def on_think(chunk):
            nonlocal think_buf
            think_buf += chunk
            ai_msg.think_content = think_buf

        def on_content(chunk):
            nonlocal content_buf
            content_buf += chunk
            ai_msg.content = content_buf
            self._speech_text.value = content_buf
            self.page.update()

        try:
            await stream_chat(api_key, api_msgs, on_content, on_think)
        except Exception as e:
            _ = ft.SnackBar(ft.Text(str(e)), bgcolor=ft.Colors.RED); self.page.show_dialog(_)

        self._streaming = False
        save_message(ai_msg)

        # Re-render with full parsed body
        idx = self.msg_list_view.controls.index(bubble)
        self.msg_list_view.controls[idx] = self._ai_bubble(ai_msg.id, ai_msg.content, ai_msg.think_content)

        # Update think panel for analysis mode
        if conv.mode == "no_inner_os" and ai_msg.think_content:
            think_col = self.think_panel.content.controls[1].content
            think_col.controls.clear()
            think_col.controls.append(ft.Text(ai_msg.think_content, size=13, selectable=True))
            self.think_panel.visible = True

        self.page.update()

    # ---- Actions ----

    def new_conversation(self, e=None):
        templates = list_templates()
        name_field = ft.TextField(label="Name", hint_text="My Roleplay")
        template_dd = ft.Dropdown(
            label="Template",
            options=[ft.dropdown.Option(str(t.id), t.name) for t in templates],
            width=300,
        )
        mode_dd = ft.Dropdown(
            label="Mode",
            options=[
                ft.dropdown.Option("inner_os", "Role Immersion"),
                ft.dropdown.Option("no_inner_os", "Pure Analysis"),
            ],
            value="inner_os",
            width=300,
        )

        def create_click(e):
            name = name_field.value.strip()
            if not name:
                return
            tid = int(template_dd.value) if template_dd.value and template_dd.value != "none" else None
            conv = Conversation(name=name, template_id=tid, mode=mode_dd.value or "inner_os")
            save_conversation(conv)
            dlg.open = False
            self.page.update()
            self.refresh_conv_list()
            self.load_conversation(conv)

        dlg = ft.AlertDialog(
            title=ft.Text("New Conversation"),
            content=ft.Column([
                name_field,
                template_dd,
                mode_dd,
            ], width=350, height=220, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update()),
                ft.FilledButton("Create", on_click=create_click),
            ],
        )
        self.page.show_dialog(dlg)
        self.page.update()

    def manage_templates(self, e=None):
        templates = list_templates()
        list_view = ft.ListView(expand=True, spacing=2)

        def refresh_list():
            list_view.controls.clear()
            for t in list_templates():
                list_view.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Text(t.name, weight=ft.FontWeight.BOLD, size=14),
                            ft.Text(t.system_prompt[:100] + "..." if len(t.system_prompt) > 100 else t.system_prompt,
                                    size=11, color=ft.Colors.GREY, no_wrap=False),
                            ft.Row([
                                ft.IconButton(ft.Icons.EDIT, icon_size=16, on_click=lambda _, t0=t: self._template_form(t0)),
                                ft.IconButton(ft.Icons.DELETE, icon_size=16, on_click=lambda _, t0=t: [delete_template(t0.id), refresh_list(), self.page.update()]),
                            ]),
                        ]),
                        padding=8,
                        border_radius=8,
                        bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.PRIMARY),
                    )
                )
            self.page.update()

        refresh_list()

        dlg = ft.AlertDialog(
            title=ft.Text("Templates"),
            content=ft.Container(list_view, width=450, height=400),
            actions=[
                ft.FilledButton("New", on_click=lambda e: [setattr(dlg, 'open', False), self.page.update(), self._template_form()]),
                ft.TextButton("Close", on_click=lambda e: [setattr(dlg, 'open', False), self.page.update()]),
            ],
        )
        self.page.show_dialog(dlg)
        self.page.update()

    def _template_form(self, template=None):
        t = template or Template()
        name_field = ft.TextField(label="Name", value=t.name)
        prompt_field = ft.TextField(label="System Prompt", value=t.system_prompt, multiline=True, min_lines=6, max_lines=15)

        def save_click(e):
            name = name_field.value.strip()
            if not name:
                return
            t.name = name
            t.system_prompt = prompt_field.value
            save_template(t)
            dlg.open = False
            self.page.update()
            self.manage_templates()

        dlg = ft.AlertDialog(
            title=ft.Text("Edit Template" if template else "New Template"),
            content=ft.Column([
                name_field,
                prompt_field,
            ], width=450, height=300, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update()),
                ft.FilledButton("Save", on_click=save_click),
            ],
        )
        self.page.show_dialog(dlg)
        self.page.update()

    def open_settings(self, e=None):
        key_field = ft.TextField(label="API Key", password=True, value=get_setting("api_key"), width=400)
        base_field = ft.TextField(label="API Base URL", value=get_setting("api_base", "https://api.deepseek.com/v1"), width=400)
        model_field = ft.TextField(label="Model", value=get_setting("model", "deepseek-v4-flash"), width=400)
        current_theme = get_setting("theme", "system")
        theme_dd = ft.Dropdown(
            label="Theme",
            options=[
                ft.dropdown.Option("dark", "Dark"),
                ft.dropdown.Option("light", "Light"),
                ft.dropdown.Option("system", "Follow System"),
            ],
            value=current_theme,
            width=400,
        )

        def save_click(e):
            set_setting("api_key", key_field.value)
            set_setting("api_base", base_field.value)
            set_setting("model", model_field.value)
            set_setting("theme", theme_dd.value or "dark")
            dlg.open = False
            self.page.update()
            self._apply_theme()
            _ = ft.SnackBar(ft.Text("Settings saved"), bgcolor=ft.Colors.GREEN); self.page.show_dialog(_)

        dlg = ft.AlertDialog(
            title=ft.Text("Settings"),
            content=ft.Column([
                key_field,
                base_field,
                model_field,
                theme_dd,
            ], width=450, height=350, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: setattr(dlg, 'open', False) or self.page.update()),
                ft.FilledButton("Save", on_click=save_click),
            ],
        )
        self.page.show_dialog(dlg)
        self.page.update()

    def on_keyboard(self, e: ft.KeyboardEvent):
        if self.input_field.focus:
            return
        if e.ctrl and e.key == "N":
            self.new_conversation()
        elif e.ctrl and e.key == "T":
            self.manage_templates()
        elif e.ctrl and e.key == "S":
            self.open_settings()
        elif e.ctrl and e.key == "D":
            self.delete_current_conv()
        elif e.ctrl and e.key == "R":
            self.regenerate()
        elif e.key == "Escape":
            self.back_to_list()

    def _apply_theme(self):
        mode = get_setting("theme", "system")
        theme_map = {"dark": ft.ThemeMode.DARK, "light": ft.ThemeMode.LIGHT, "system": ft.ThemeMode.SYSTEM}
        self.page.theme_mode = theme_map.get(mode, ft.ThemeMode.DARK)
        self.page.update()

    def delete_current_conv(self):
        if not self.current_conv:
            return
        delete_conversation(self.current_conv.id)
        self.current_conv = None
        self.messages = []
        self.msg_list_view.controls.clear()
        self.input_field.disabled = True
        self.think_panel.visible = False
        self.refresh_conv_list()
        self.page.update()

    def regenerate(self):
        if self._streaming or not self.current_conv or len(self.messages) < 2:
            return
        last_user = None
        last_ai = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == "user" and last_user is None:
                last_user = self.messages[i]
            elif self.messages[i].role == "assistant" and last_user is not None and last_ai is None:
                last_ai = self.messages[i]
        if not last_user or not last_ai:
            return
        # remove last AI from list and UI
        self.messages.remove(last_ai)
        if self.msg_list_view.controls:
            self.msg_list_view.controls.pop()
        self.page.update()
        asyncio.create_task(self._stream_from_user(last_user))

    def back_to_list(self):
        self.current_conv = None
        self.messages = []
        self.msg_list_view.controls.clear()
        self.input_field.disabled = True
        self.think_panel.visible = False
        self.refresh_conv_list()
        self.page.title = "RP DS"
        self.page.update()
