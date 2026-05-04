# RP DS

基于 DeepSeek V4 的角色扮演客户端，支持角色沉浸模式与纯分析模式切换。
使用 Flet 构建跨平台图形界面。

## 功能

- **模板管理** — 预设 System Prompt，创建对话时直接选用
- **双模式切换** — 角色沉浸（思考含括号内心独白）/ 纯分析（每条消息独立切换 Chat/Analysis 视图）
- **流式输出** — 实时渲染思考内容与 AI 回复，动作/言语/思考分段展示
- **消息操作** — 重新生成自动创建分支版本
- **SQLite 持久化** — 对话、模板、设置全部本地存储
- **响应式布局** — 宽屏左右分栏，窄屏移动端自动适配

## 运行

```bash
pip install flet textual httpx
python main_flet.py
```

首次使用按 `Ctrl+S` 填入 DeepSeek API Key，然后 `Ctrl+N` 创建对话。

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

通过 GitHub Actions 自动构建多平台可执行文件。推送 tag 或手动在 Actions 页面触发。

### 平台支持

| 平台 | 架构 | 格式 |
|---|---|---|
| Linux | amd64 / arm64 | .tar.gz |
| Windows | amd64 | .zip |
| macOS | amd64 / arm64 | .tar.gz |
| Android | arm64 | .apk |

### 本地构建

```bash
# 安装 flet-cli
pip install flet-cli

# 桌面端
flet build linux --module-name main_flet --yes
flet build windows --module-name main_flet --yes
flet build macos --module-name main_flet --yes

# Android APK（需要 Java 17 + Flutter SDK）
flet build apk --module-name main_flet --yes
```

## 数据

SQLite 数据库 `data.db` 存放在可执行文件同级目录。

## 开源许可

MIT
