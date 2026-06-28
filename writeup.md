# 🎒 Vid2Knowledge — Local AI Study Ingestion Agent

## Subtitle
An AI-powered local study concierge that extracts YouTube video transcripts and restructures them into detailed, offline-accessible Markdown notes and study guides using Google Gemini.

## 📌 Track Selection
**Concierge Agents** (or **Freestyle**)
*Why:* Vid2Knowledge is designed to act as a personal study concierge, extracting educational video transcripts and transforming them into beautifully structured offline-accessible Markdown notes and study blogs. It prioritizes user privacy and data sovereignty by saving all outputs locally and binding running servers strictly to localhost (`127.0.0.1`).

---

## 📖 Project Overview & Problem Statement
With the explosion of high-quality educational content on YouTube, students and researchers spend hours watching videos, pausing to write notes, or dealing with poorly formatted transcripts. Standard transcript grabbers output raw, unstructured wall-of-text blocks with zero organization, styling, or context. 

Existing solutions are either expensive SaaS products that store your data on external databases, or complex command-line pipelines that are hard to configure and use.

**Vid2Knowledge** solves this by providing a local-first, zero-dependency AI-powered study concierge that:
1. Extracts YouTube video transcripts/subtitles cleanly using a robust fallback chain (`yt-dlp` and `youtube-transcript-api`).
2. Converts raw transcripts into detailed, well-structured, beautifully formatted Markdown notes and study blogs using the fast and reliable `gemini-2.5-flash` model.
3. Integrates with the **Model Context Protocol (MCP)**, allowing other AI tools (such as Claude Desktop or Cursor) to trigger transcript scraping and blog generation.
4. Provides a gorgeous, responsive, glassmorphic Web UI for manual use.

---

## 📐 System Architecture

The Vid2Knowledge architecture is designed for speed, modularity, and security:

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

### Flow of Execution:
1. **User Action:** The user inputs a YouTube URL into the Local Web App (`index.html`) or requests their AI assistant (e.g. Claude) to ingest a video.
2. **Scraping Phase (`ingest.py`):** The scraper attempts to download manual/auto subtitles using `yt-dlp`. If that fails, it falls back to `youtube-transcript-api`. If no subtitles exist, it generates a clean placeholder stub.
3. **Structured Storage:** The cleaned transcript is normalized and saved locally in `External Inputs/YouTube/<channel-slug>/<date>-<title-slug>.md`.
4. **AI Generation Phase (`app.py`):** The transcript is sent to the Google Gemini API with a specialized education prompt, generating a comprehensive study blog.
5. **Interactive UI Display:** The user views the beautifully rendered AI study guide immediately in the browser.

---

## 💻 Technical Implementation & Code Breakdown

The codebase is organized into four main components:
- **`ingest.py`**: The extraction engine that downloads, cleans, and structures raw subtitles.
- **`app.py`**: The FastAPI backend server coordinating the scraping and calling the Gemini API.
- **`mcp_server.py`**: A custom-engineered stdio Model Context Protocol (MCP) server.
- **`index.html`**: A premium, glassmorphic UI using modern HSL colors, Outfit typography, and micro-animations.

### 🔑 Security-First Approach
- No hardcoded keys: API keys and configuration parameters are loaded dynamically from a local `.env` file.
- Strict binding: The FastAPI server runs exclusively on `127.0.0.1` (`localhost`) to prevent unauthorized network access to your local notes and scrapers.

---

## 🎓 Kaggle Course Concept Alignment

This project applies several core concepts from Kaggle’s **5-Day AI Agents: Intensive Vibe Coding Course**:

| Key Concept | Implementation Details |
| :--- | :--- |
| **Agent / Multi-agent system (ADK)** | Coordinates tasks between subtitle extraction, file ingestion, and Gemini-based formatting. |
| **MCP Server** | Implemented a custom JSON-RPC stdio server (`mcp_server.py`) to expose internal tools to global agent ecosystems. |
| **Antigravity Vibe Coding** | Co-designed, refined, and refactored under the direct pair-programming guidance of Google DeepMind's Antigravity assistant. |
| **Security Features** | Environment variable isolation via `.env`, and strictly localhost-bound FastAPI uvicorn runner. |
| **Deployability** | Self-contained local-first structure running with simple scripts and zero heavy database dependencies. |
| **Agent Skills** | Extensible scraping logic (`ingest.py`) designed to interface easily with CLI workflows. |

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
Create a `.env` file in the root directory:
```env
# Gemini Configuration
GEMINI_API_KEY=your_gemini_api_key

# Comma-separated fallback chain
GEMINI_MODELS=gemini-2.5-flash
```

### 5. Running the Application
Run the FastAPI backend server:
```powershell
python app.py
```
Open your browser and navigate to:  
👉 **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)**
