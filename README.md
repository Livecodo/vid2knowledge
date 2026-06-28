# 🎒 Vid2Knowledge — Local AI Study Ingestion Agent

> An AI-powered local study concierge that extracts YouTube video transcripts and restructures them into highly detailed, offline-accessible Markdown notes and study guides using Google Gemini.

Vid2Knowledge is built for students, researchers, and developers who want to reclaim data sovereignty over educational content and build local-first personal knowledge repositories. It also features a zero-dependency Model Context Protocol (MCP) server integration to allow other AI tools to execute scraping and blog generation commands.

---

## ⚡ Features

- **Local-First Scraping:** Extract YouTube transcripts and subtitles safely, saving them directly into your local Markdown folder.
- **Gemini Restructuring:** Convert raw speech transcripts into cohesive, beautifully styled study blogs and research summaries using the fast, reliable `gemini-2.5-flash` model.
- **Zero-Dependency stdio MCP Server:** A custom-engineered Model Context Protocol server written completely using standard Python libraries, making it fully compatible with Python 3.9+ and easy to connect to Claude Desktop, Cursor, or other MCP-capable clients.
- **Security-First Architecture:** Keeps your API keys safe in environment files and strictly binds web server execution to localhost (`127.0.0.1`) to ensure data privacy.

---

## 📐 System Architecture

```
                                      +------------------+
                                      |   YouTube Video  |
                                      +--------+---------+
                                               |
                                               v
                                      +--------+---------+
                                      | Subtitle Scraper |  (ingest.py)
                                      +--------+---------+
                                               |
                                               v
                                      +--------+---------+
                                      |  FastAPI Server  |  (app.py)
                                      +---+----+---------+
                                          |    ^
               +--------------------------+    |
               | (Gemini REST Call)            | (FastAPI UI)
               v                               v
      +--------+---------+            +--------+---------+
      |  Gemini 2.5 API  |            |  Local Web App   |  (index.html)
      +--------+---------+            +------------------+
               |
               v
      +--------+---------+
      | Markdown Output  |  (Offline Study Vault)
      +------------------+
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
Ensure you have Python 3.9+ installed on your system.

### 2. Clone and Setup Environment
Navigate to the directory and set up a Python virtual environment:
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
Install all required python packages:
```powershell
pip install -r requirements.txt
```

### 4. Configure API Keys
Create a `.env` file in the root directory (or edit the existing one) to specify your Gemini API Key:
```env
# Gemini Configuration
GEMINI_API_KEY=your_gemini_api_key

# Comma-separated fallback chain — tried left to right
GEMINI_MODELS=gemini-2.5-flash
```

---

## 💻 How to Run

### Option A: The Web Application UI
Run the FastAPI backend server:
```powershell
python app.py
```
Open your browser and navigate to:  
👉 **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)**

Enter a YouTube URL, click **Scrape Video**, and see your transcript get saved locally as a Markdown file. The app will automatically render a beautifully formatted AI-generated blog draft summarizing the video.

### Option B: The Stdio MCP Server
Run the MCP server locally over stdio:
```powershell
python mcp_server.py
```

#### Integrating with Claude Desktop
To expose Vid2Knowledge tools directly inside Claude Desktop, add this config to your `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "vid2knowledge": {
      "command": "d:\\free local llm\\Agent 3\\.venv\\Scripts\\python.exe",
      "args": [
        "d:\\free local llm\\Agent 3\\mcp_server.py"
      ]
    }
  }
}
```
Once saved and restarted, you can ask Claude to "scrape this youtube video URL" or "convert this transcript to a study guide" and it will invoke the local agent tools.

---

## 📚 Kaggle Course Concept Alignment

This project applies the following concepts taught in Kaggle’s *5-Day AI Agents: Intensive Vibe Coding Course with Google*:

| Course Concept | Implementation Detail |
| :--- | :--- |
| **Agent / Multi-agent system (ADK)** | Coordinates tasks between subtitle extraction, file ingestion, and Gemini-based formatting. |
| **MCP Server** | Implemented a custom JSON-RPC stdio server (`mcp_server.py`) to expose internal tools to global agent ecosystems. |
| **Security Features** | Environment variable isolation via `.env`, and strictly localhost-bound FastAPI uvicorn runner. |
| **Deployability** | Self-contained local-first structure running with simple scripts and zero heavy database dependencies. |
| **Antigravity Vibe Coding** | Co-designed, refined, and refactored under the direct pair-programming guidance of Google DeepMind's Antigravity assistant. |

---

## 🤝 Collaboration Acknowledgement
Vid2Knowledge was built and polished using **Vibe Coding** methodologies in pair-programming collaboration with **Antigravity**, Google DeepMind's agentic coding assistant.
