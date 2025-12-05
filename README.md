# YouTube 技术洞察报告生成器

这是一个 Python 脚本，可以从指定的 YouTube 视频链接中自动提取字幕，利用大语言模型（LLM）生成一份专业的技术洞察报告。

本工具特别适合需要快速消化和理解技术类视频核心内容的开发者、研究人员和学生。

## 主要功能

- **自动提取字幕**：支持多种语言，并优先选择中文字幕。
- **智能分析报告**：调用 LLM API（兼容 OpenAI 格式）对字幕内容进行深度分析，生成结构化的技术报告。
- **处理长视频**：当字幕内容过长时，会自动进行分块总结，然后将摘要整合后进行最终分析，有效避免了超出模型上下文长度限制的问题。
- **灵活的认证方式**：支持自动从本地浏览器读取登录凭据（Cookies），轻松访问需要登录才能观看的视频（如会员视频、年龄限制视频），无需安装任何浏览器插件。
- **高度可配置**：通过 `config.yaml` 文件，可以轻松配置 API、模型、提示词和输出格式等。

## 环境要求

- Python 3.7+
- `pip` 包管理器

## 安装步骤

1. **克隆项目**
   ```bash
   git clone <your-repo-url>
   cd youtube-report
   ```

2. **创建并激活虚拟环境** (推荐)
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **安装依赖库**
   ```bash
   pip install -r requirements.txt
   ```

## 配置说明

首次运行前，请配置 `config.yaml` 文件。

1. **LLM API 配置**:
   - `base_url`: 你的 LLM API 地址。
   - `api_key`: 你的 API Key。**（必需）**
   - `model`: 你希望使用的模型名称。

2. **访问需要登录的视频** (重要)

   为了分析有年龄限制或需要会员登录的视频，脚本需要你的 YouTube 登录信息。你有以下两种方式配置，推荐使用**方法1**。

   **方法1：自动从浏览器读取 (推荐，无需插件)**
   这是最简单、最安全的方式。`yt-dlp` 可以直接从你电脑上安装的浏览器中读取有效的 YouTube Cookies。

   - **操作步骤**:
     1. 在你的电脑上正常登录 YouTube 网站。
     2. 打开 `config.yaml` 文件。
     3. 在 `subtitle` 配置块中，找到 `browser_for_cookies` 字段。
     4. 填入你的浏览器名称（全小写）。
        ```yaml
        subtitle:
          # 支持: chrome, firefox, opera, edge, safari, vivaldi, brave
          browser_for_cookies: "chrome" 
        ```
   - 程序运行时会自动加载相应浏览器的 Cookies，无需任何额外操作。

   **方法2：使用 `cookies.txt` 文件 (备用)**
   如果你无法或不想使用方法1，可以手动从浏览器导出一个 `cookies.txt` 文件。

   - **操作步骤**:
     1. 你需要一个浏览器插件来导出 Cookies。常用的插件是 **"Get cookies.txt"**（适用于 Chrome 和 Firefox）。
     2. 在浏览器中访问 YouTube 网站。
     3. 点击 "Get cookies.txt" 插件图标，选择 "Export"。
     4. 将导出的内容保存为一个文件，例如 `youtube-cookies.txt`。
     5. 打开 `config.yaml` 文件，在 `subtitle` 配置块中，找到 `cookies_file` 字段，并填入你保存的 `cookies.txt` 文件的 **绝对路径**。
        ```yaml
        subtitle:
          cookies_file: "/Users/yourname/Documents/youtube-cookies.txt"
        ```

   > **注意**: 脚本会优先使用 `browser_for_cookies` 的配置。如果该项为空，才会尝试使用 `cookies_file`。

## 使用方法

配置完成后，通过以下命令运行脚本：

```bash
python3 yt_report.py "YOUTUBE_VIDEO_URL"
```

**示例:**
```bash
python3 yt_report.py "https://www.youtube.com/watch?v=some-video-id"
```

你还可以通过命令行参数覆盖部分配置：

- `--config`: 指定其他配置文件的路径。
- `--api-key`: 临时提供一个 API Key，其优先级最高。

报告和原始字幕（如果开启）会默认保存在 `reports` 目录下。
