# RP DS

基于 DeepSeek V4 的角色扮演 TUI 客户端，支持角色沉浸模式与纯分析模式切换。

## 功能

- **模板管理** — 预设 System Prompt，创建对话时直接选用
- **双模式切换** — 角色沉浸（思考含括号内心独白）/ 纯分析（思考在右侧面板展示）
- **流式输出** — 实时渲染思考内容与 AI 回复，动作/言语/思考分段展示
- **消息操作** — 重新生成自动创建分支版本
- **SQLite 持久化** — 对话、模板、设置全部本地存储

## 运行

```bash
pip install textual httpx
python main.py
```

首次使用先按 `Ctrl+S` 填入 DeepSeek API Key。

## 快捷键

| 键 | 功能 |
|---|---|
| `Ctrl+N` | 新建对话 |
| `Ctrl+T` | 管理模板 |
| `Ctrl+S` | 设置 |
| `Ctrl+D` | 删除当前对话 |
| `Ctrl+R` | 重新生成 |
| `Esc` | 返回对话列表 |

## 构建

```bash
pip install pyinstaller
pyinstaller --onefile --name rp_ds main.py
```

或通过 GitHub Actions 自动构建多平台可执行文件（见 `.github/workflows/build.yml`）。

## 开源许可

MIT
