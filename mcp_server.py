import sys
import json
import traceback
from pathlib import Path
from ingest import run_ingest
from app import call_gemini, load_dotenv

# Log debug messages to stderr so they don't corrupt stdin/stdout JSON channel
def log(msg: str):
    sys.stderr.write(f"[Vid2Knowledge MCP] {msg}\n")
    sys.stderr.flush()

def scrape_youtube_video(url: str, lang: str = "en,es", whisper: bool = False) -> str:
    vault_root = Path(__file__).parent
    try:
        result = run_ingest(
            url=url,
            vault_root_path=vault_root,
            lang_prefs_str=lang,
            whisper=whisper
        )
        if result.get("success"):
            target_path = result.get("target_path", "")
            title = result.get("title", "")
            return f"Successfully scraped '{title}'. Saved transcript markdown to {target_path}."
        else:
            return f"Failed to scrape video: {result.get('error')}"
    except Exception as e:
        return f"Error during scraping: {str(e)}"

def generate_blog_post(transcript: str, title: str, channel: str = "") -> str:
    system_prompt = (
        "You are an expert educator, researcher, and technical writer. Your task is to transform the "
        "following video transcript into a comprehensive, highly detailed, and well-structured study guide "
        "and blog post. It must explain all key concepts fully, with clear sections, examples, detailed "
        "explanations, and key takeaways so that any student or researcher can use it as high-quality study notes. "
        "Use rich markdown formatting (headers, bolding, lists, blockquotes, and code blocks). "
        "Ensure the output is long, thorough, and explains everything discussed in the transcript in depth, "
        "translating raw speech into cohesive written notes."
    )
    user_prompt = (
        f"Video Title: {title}\n"
        f"Channel: {channel}\n\n"
        f"Transcript:\n{transcript}"
    )
    try:
        content = call_gemini(system_prompt, user_prompt, json_mode=False)
        return content
    except Exception as e:
        return f"Error generating study guide: {str(e)}"

# Handlers for JSON-RPC methods
def handle_initialize(msg_id, params):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "vid2knowledge-mcp",
                "version": "1.0.0"
            }
        }
    }

def handle_tools_list(msg_id, params):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "tools": [
                {
                    "name": "scrape_youtube_video",
                    "description": "Scrapes a YouTube video's transcript/subtitles and saves it as a local Markdown file.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The full YouTube video URL."
                            },
                            "lang": {
                                "type": "string",
                                "description": "Comma-separated language preference codes (default: 'en,es')."
                            },
                            "whisper": {
                                "type": "boolean",
                                "description": "Whether to fall back to Whisper transcript extraction if no subtitles exist."
                            }
                        },
                        "required": ["url"]
                    }
                },
                {
                    "name": "generate_blog_post",
                    "description": "Converts a video transcript into a structured, highly detailed study guide / blog post using Gemini.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "transcript": {
                                "type": "string",
                                "description": "The raw video transcript text."
                            },
                            "title": {
                                "type": "string",
                                "description": "The title of the video."
                            },
                            "channel": {
                                "type": "string",
                                "description": "The name of the YouTube channel (optional)."
                            }
                        },
                        "required": ["transcript", "title"]
                    }
                }
            ]
        }
    }

def handle_tools_call(msg_id, params):
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    log(f"Calling tool: {tool_name} with arguments: {arguments}")
    
    if tool_name == "scrape_youtube_video":
        url = arguments.get("url")
        lang = arguments.get("lang", "en,es")
        whisper = arguments.get("whisper", False)
        
        if not url:
            result_text = "Error: 'url' parameter is required."
        else:
            result_text = scrape_youtube_video(url, lang, whisper)
            
    elif tool_name == "generate_blog_post":
        transcript = arguments.get("transcript")
        title = arguments.get("title")
        channel = arguments.get("channel", "")
        
        if not transcript or not title:
            result_text = "Error: both 'transcript' and 'title' parameters are required."
        else:
            result_text = generate_blog_post(transcript, title, channel)
    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {tool_name}"
            }
        }
        
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": result_text
                }
            ]
        }
    }

def main():
    load_dotenv()
    log("Server starting up...")
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            line = line.strip()
            if not line:
                continue
            
            log(f"Received request: {line}")
            request = json.loads(line)
            
            msg_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            
            # Route method
            if method == "initialize":
                response = handle_initialize(msg_id, params)
            elif method == "notifications/initialized":
                # Notifications don't receive responses
                log("Received initialized notification")
                continue
            elif method == "tools/list":
                response = handle_tools_list(msg_id, params)
            elif method == "tools/call":
                response = handle_tools_call(msg_id, params)
            else:
                # Unknown method or standard protocol requests
                log(f"Unhandled method: {method}")
                if msg_id is not None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}"
                        }
                    }
                else:
                    continue
            
            # Send response
            response_str = json.dumps(response)
            log(f"Sending response: {response_str}")
            sys.stdout.write(response_str + "\n")
            sys.stdout.flush()
            
        except Exception as e:
            log(f"Error in main loop: {str(e)}")
            log(traceback.format_exc())

if __name__ == "__main__":
    main()
