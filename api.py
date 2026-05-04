import json
import httpx
from typing import Callable

DEEPSEEK_BASE = "https://api.deepseek.com/v1"

INNER_OS_MARKER = (
    "\n\n【角色沉浸要求】在你的思考过程（<think>标签内）中，请遵守以下规则：\n"
    "1. 请以角色第一人称进行内心独白，用括号包裹内心活动，例如\"（心想：……）\"或\"(内心OS：……)\"\n"
    "2. 用第一人称描写角色的内心感受，例如\"我心想\"\"我觉得\"\"我暗自\"等\n"
    "3. 思考内容应沉浸在角色中，通过内心独白分析剧情和规划回复"
)
NO_INNER_OS_MARKER = (
    "\n\n【思维模式要求】在你的思考过程（<think>标签内）中，请遵守以下规则：\n"
    "1. 禁止使用圆括号包裹内心独白，例如\"（心想：……）\"或\"(内心OS：……)\"，所有分析内容直接陈述即可\n"
    "2. 禁止以角色第一人称描写内心活动，例如\"我心想\"\"我觉得\"\"我暗自\"等，请用分析性语言替代\n"
    "3. 思考内容应聚焦于剧情走向分析和回复内容规划，不要在思考中进行角色扮演式的内心戏表演"
)


def build_messages(system_prompt: str, history: list[dict], user_msg: str, mode: str) -> list[dict]:
    msgs = [{"role": "system", "content": system_prompt}]
    msgs.extend(history)
    content = user_msg
    if mode == "inner_os":
        content += INNER_OS_MARKER
    elif mode == "no_inner_os":
        content += NO_INNER_OS_MARKER
    msgs.append({"role": "user", "content": content})
    return msgs


async def stream_chat(
    api_key: str,
    messages: list[dict],
    on_content: Callable[[str], None],
    on_think: Callable[[str], None],
    model: str = "deepseek-v4-flash",
):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    buffer = ""
    in_think = False
    think_buf = ""
    content_buf = ""

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{DEEPSEEK_BASE}/chat/completions", headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                error_text = await resp.aread()
                raise RuntimeError(f"API error {resp.status_code}: {error_text.decode()}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                reasoning = delta.get("reasoning_content", "")

                if reasoning:
                    on_think(reasoning)
                    think_buf += reasoning

                if content:
                    buffer += content
                    while True:
                        if not in_think:
                            idx = buffer.find("<think>")
                            if idx >= 0:
                                if idx > 0:
                                    on_content(buffer[:idx])
                                    content_buf += buffer[:idx]
                                buffer = buffer[idx + 7:]
                                in_think = True
                            else:
                                if buffer:
                                    on_content(buffer)
                                    content_buf += buffer
                                    buffer = ""
                                break
                        else:
                            idx = buffer.find("</think>")
                            if idx >= 0:
                                think = buffer[:idx]
                                if think:
                                    on_think(think)
                                    think_buf += think
                                buffer = buffer[idx + 8:]
                                in_think = False
                            else:
                                break

                if choices[0].get("finish_reason") == "stop":
                    break

    # flush remaining buffer
    if buffer:
        if in_think:
            on_think(buffer)
            think_buf += buffer
        else:
            on_content(buffer)
            content_buf += buffer

    return content_buf, think_buf
