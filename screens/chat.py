import asyncio
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Input, Button, ListView, ListItem, Label, Static,
)
from textual.containers import Horizontal, Vertical
from rich.panel import Panel
from rich.markup import escape
from db import (
    list_conversations, delete_conversation,
    save_message, get_active_branch, get_setting,
    get_template,
)
from models import Message, Conversation
from api import stream_chat, build_messages
from widgets.message import MessageWidget


class ChatScreen(Screen):
    TITLE = "Chat"

    BINDINGS = [
        ("ctrl+n", "new_conversation", "New"),
        ("ctrl+t", "templates", "Templates"),
        ("ctrl+s", "settings", "Settings"),
        ("ctrl+d", "delete_conversation", "Delete"),
        ("ctrl+r", "regenerate", "Regen"),
        ("escape", "back_to_list", "Back"),
    ]

    def __init__(self):
        super().__init__()
        self.current_conv: Conversation | None = None
        self.conversations: list[Conversation] = []
        self.messages: list[Message] = []
        self._streaming = False
        self._current_ai_msg: Message | None = None
        self._think_buf = ""

    def compose(self):
        yield Header()
        yield Horizontal(
            Vertical(
                Label("[bold]Conversations[/bold]", id="sidebar_title"),
                ListView(id="conv_list"),
                Horizontal(
                    Button("+", id="new_conv_btn", variant="primary"),
                    Button("⚙", id="settings_btn"),
                    classes="sidebar_btn_row",
                ),
                id="sidebar",
            ),
            Vertical(
                Horizontal(
                    Vertical(id="msg_area"),
                    Static(id="think_panel"),
                    id="content_row",
                ),
                Input(placeholder="Type a message and press Enter...", id="input_bar"),
                id="right_panel",
            ),
        )
        yield Footer()

    def on_screen_resume(self):
        self.call_after_refresh(self.refresh_conv_list)

    def on_mount(self):
        self.call_after_refresh(self.refresh_conv_list)
        self.query_one("#input_bar", Input).disabled = True

    def refresh_conv_list(self):
        lv = self.query_one("#conv_list", ListView)
        lv.clear()
        self.conversations = list_conversations()
        for c in self.conversations:
            lv.append(ListItem(Label(f"{c.name} [{c.mode}]")))
        if self.conversations:
            lv.index = 0

    def on_list_view_selected(self, event: ListView.Selected):
        if event.list_view.id == "conv_list":
            idx = self.query_one("#conv_list", ListView).index
            if idx is not None and idx < len(self.conversations):
                self.load_conversation(self.conversations[idx])

    def load_conversation(self, conv: Conversation):
        self.current_conv = conv
        self.TITLE = conv.name
        self.load_messages()
        self.query_one("#input_bar", Input).disabled = False
        self.query_one("#input_bar", Input).focus()

    def load_messages(self):
        if not self.current_conv:
            return
        chain = get_active_branch(self.current_conv.id)
        self.messages = chain
        msg_area = self.query_one("#msg_area", Vertical)
        msg_area.remove_children()
        msg_area.mount(*[
            MessageWidget(m, self.current_conv.mode) for m in chain
        ])
        tp = self.query_one("#think_panel", Static)
        if self.current_conv.mode == "no_inner_os":
            tp.display = True
        else:
            tp.display = False

    def action_new_conversation(self):
        from screens.conversation_form import ConversationForm
        self.app.push_screen(ConversationForm(), self._on_conv_created)

    def _on_conv_created(self, conv: Conversation | None):
        if conv:
            self.refresh_conv_list()
            self.load_conversation(conv)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "new_conv_btn":
            self.action_new_conversation()
        elif event.button.id == "settings_btn":
            self.action_settings()

    def action_templates(self):
        from screens.template_mgmt import TemplateMgmt
        self.app.push_screen(TemplateMgmt())

    def action_settings(self):
        from screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen())

    def action_delete_conversation(self):
        if not self.current_conv:
            return
        delete_conversation(self.current_conv.id)
        self.current_conv = None
        self.refresh_conv_list()
        self.query_one("#msg_area", Vertical).remove_children()
        self.query_one("#think_panel", Static).display = False
        self.query_one("#input_bar", Input).disabled = True

    def on_input_submitted(self, event: Input.Submitted):
        if not self.current_conv or self._streaming:
            return
        text = event.value.strip()
        if not text:
            return
        self.query_one("#input_bar", Input).value = ""
        self._run_async(self.send_message(text))

    def _run_async(self, coro):
        task = asyncio.ensure_future(coro)
        task.add_done_callback(lambda t: self._handle_task_error(t))

    def _handle_task_error(self, task):
        exc = task.exception()
        if exc:
            self._streaming = False
            self.notify(f"{exc}", severity="error")
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)

    async def send_message(self, text: str):
        try:
            conv = self.current_conv
            parent_id = self.messages[-1].id if self.messages else None

            user_msg = Message(
                conversation_id=conv.id,
                parent_id=parent_id,
                role="user",
                content=text,
            )
            save_message(user_msg)
            self.messages.append(user_msg)

            msg_area = self.query_one("#msg_area", Vertical)
            user_w = MessageWidget(user_msg, conv.mode)
            await msg_area.mount(user_w)

            await self._stream_from_user(user_msg)
        except Exception as e:
            self._streaming = False
            self.notify(f"send_message failed: {e}", severity="error")
            import traceback
            traceback.print_exc()

    async def _stream_from_user(self, user_msg: Message):
        conv = self.current_conv
        msg_area = self.query_one("#msg_area", Vertical)

        api_key = get_setting("api_key")
        if not api_key:
            self.notify("API key not set. Go to Settings.", severity="error")
            self._streaming = False
            return

        template = get_template(conv.template_id) if conv.template_id else None
        system_prompt = template.system_prompt if template else ""

        # build history from messages before user_msg
        history = []
        idx = None
        for i, m in enumerate(self.messages):
            if m.role == "user" and m.content == user_msg.content and m.parent_id == user_msg.parent_id:
                idx = i
                break
            history.append({"role": m.role, "content": m.content})
        if idx is None:
            # user_msg not found, use all but last
            for m in self.messages[:-1]:
                history.append({"role": m.role, "content": m.content})

        api_msgs = build_messages(system_prompt, history, user_msg.content, conv.mode)

        ai_msg = Message(
            conversation_id=conv.id,
            parent_id=user_msg.id,
            role="assistant",
            content="",
            think_content="",
        )
        save_message(ai_msg)
        self.messages.append(ai_msg)
        self._current_ai_msg = ai_msg
        self._think_buf = ""

        ai_w = MessageWidget(ai_msg, conv.mode, id=f"msg_{ai_msg.id}")
        await msg_area.mount(ai_w)
        msg_area.scroll_end(animate=False)

        self._streaming = True
        try:
            if conv.mode == "no_inner_os":
                await self._stream_analysis_mode(api_key, api_msgs, ai_msg, ai_w)
            else:
                await self._stream_inner_os_mode(api_key, api_msgs, ai_msg, ai_w)
        finally:
            self._streaming = False
            save_message(ai_msg)

    async def _stream_inner_os_mode(self, api_key, api_msgs, ai_msg, ai_w):
        content_buf = ""
        think_buf = ""

        def on_think(chunk):
            nonlocal think_buf
            think_buf += chunk
            ai_msg.think_content = think_buf
            ai_w.render_content()

        def on_content(chunk):
            nonlocal content_buf
            content_buf += chunk
            ai_msg.content = content_buf
            ai_w.render_content()

        try:
            await stream_chat(api_key, api_msgs, on_content, on_think)
        except Exception as e:
            self.notify(str(e), severity="error")

    async def _stream_analysis_mode(self, api_key, api_msgs, ai_msg, ai_w):
        content_buf = ""
        think_buf = ""

        def on_think(chunk):
            nonlocal think_buf
            think_buf += chunk
            ai_msg.think_content = think_buf
            self._update_think_panel()

        def on_content(chunk):
            nonlocal content_buf
            content_buf += chunk
            ai_msg.content = content_buf
            ai_w.render_content()

        try:
            await stream_chat(api_key, api_msgs, on_content, on_think)
        except Exception as e:
            self.notify(str(e), severity="error")

    def _update_think_panel(self):
        if self._current_ai_msg:
            tp = self.query_one("#think_panel", Static)
            tp.update(Panel(
                escape(self._current_ai_msg.think_content),
                title="Analysis",
                border_style="yellow",
            ))

    def action_regenerate(self):
        if self._streaming or not self.current_conv or len(self.messages) < 2:
            return
        last_user = None
        last_ai = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == "user" and last_user is None:
                last_user = self.messages[i]
            elif self.messages[i].role == "assistant" and last_user is not None and last_ai is None:
                last_ai = self.messages[i]
        if not last_user:
            return
        # remove old AI message from display
        if last_ai:
            msg_area = self.query_one("#msg_area", Vertical)
            for child in list(msg_area.children):
                if hasattr(child, "message") and child.message.id == last_ai.id:
                    child.remove()
                    break
            self.messages.remove(last_ai)
        self._run_async(self._stream_from_user(last_user))

    def action_edit_message(self):
        pass  # TODO

    def action_back_to_list(self):
        self.current_conv = None
        self.messages = []
        self.query_one("#msg_area", Vertical).remove_children()
        self.query_one("#think_panel", Static).display = False
        self.query_one("#input_bar", Input).disabled = True
        self.refresh_conv_list()
