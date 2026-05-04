from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Template:
    id: Optional[int] = None
    name: str = ""
    system_prompt: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Conversation:
    id: Optional[int] = None
    name: str = ""
    template_id: Optional[int] = None
    template_name: str = ""
    mode: str = "inner_os"  # inner_os | no_inner_os
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Message:
    id: Optional[int] = None
    conversation_id: int = 0
    parent_id: Optional[int] = None
    role: str = ""  # user | assistant
    content: str = ""
    think_content: str = ""
    branch_order: int = 0
    created_at: str = ""

    children: list["Message"] = field(default_factory=list)
