#!/usr/bin/env python3
"""
ingest.py: YouTube-to-vault normalizer for the ingest-youtube skill.

Takes a YouTube URL (and optional vault root), shells out to yt-dlp for
metadata + subtitles, cleans VTT timing markers into prose, and writes
External Inputs/YouTube/<channel-slug>/<YYYY-MM-DD>-<video-slug>.md.

Stdout: human-readable summary.
Exit non-zero on any failure (no silent partial writes).

Usage:
    python3 ingest.py <youtube-url> [--vault <path>] [--lang <code>]

Defaults:
    --vault: $VAULT_ROOT or current dir
    --lang:  en,es (try English first, then Spanish; matches a common
             EN+ES bilingual default for users with multilingual content)
    --whisper: accepted as a future fallback flag; this version writes a stub
               if subtitles are unavailable
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

# Ensure the virtual environment's bin/Scripts directory is in PATH so subprocesses can find installed tools like yt-dlp
_venv_bin = os.path.dirname(sys.executable)
if _venv_bin and _venv_bin not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = _venv_bin + os.pathsep + os.environ.get("PATH", "")

VTT_TIMING_RE = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*")
VTT_HEADER_RE = re.compile(r"^(WEBVTT|Kind:|Language:|NOTE\s|X-TIMESTAMP-MAP)", re.MULTILINE)
SLUG_RE = re.compile(r"[^a-z0-9]+")
YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
SUBPROCESS_TIMEOUT_SECONDS = 60
SEED_KEYWORDS = (
    "decision", "framework", "model", "principle", "the lesson is",
    "playbook", "anti-pattern", "case study", "what i learned",
    "the trick is", "the insight is",
)


def validate_youtube_url(raw_url: str) -> str:
    if not raw_url or raw_url.startswith("-") or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw_url):
        raise ValueError("URL must be a valid http(s) YouTube video URL")

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")

    host = parsed.hostname.lower() if parsed.hostname else ""
    video_id = ""

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) >= 2 and parts[0] in {"shorts", "embed", "v"}:
            video_id = parts[1]
    elif host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/", 1)[0]

    if not YOUTUBE_VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError("URL must point to a single YouTube video")

    return urlunparse(("https", "www.youtube.com", "/watch", "", f"v={video_id}", ""))


def run_ytdlp(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )


def yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return '""'
    return json.dumps(str(value), ensure_ascii=False)


def markdown_text(value: object) -> str:
    text = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|-])", r"\\\1", text)


def slugify(text: str, max_len: int = 60) -> str:
    s = SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def require_bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.stderr.write(
            f"Error: {name} not installed. Install with `brew install {name}` "
            f"(macOS) or `pip3 install --user {name}`.\n"
        )
        sys.exit(2)
    return path


def fetch_metadata(url: str, ytdlp: str) -> dict:
    proc = run_ytdlp([ytdlp, "--ignore-config", "--skip-download", "--print-json", "--no-warnings", "--", url])
    if proc.returncode != 0:
        sys.stderr.write(f"yt-dlp metadata fetch failed:\n{proc.stderr}\n")
        sys.exit(3)
    return json.loads(proc.stdout)


def list_subs(url: str, ytdlp: str) -> str:
    proc = run_ytdlp([ytdlp, "--ignore-config", "--list-subs", "--skip-download", "--no-warnings", "--", url])
    return proc.stdout


def parse_available_subs(listing: str) -> tuple[set[str], set[str]]:
    """Return (manual_langs, auto_langs) from --list-subs output."""
    manual: set[str] = set()
    auto: set[str] = set()
    section = None
    for line in listing.splitlines():
        low = line.strip().lower()
        if "available subtitles" in low:
            section = "manual"
            continue
        if "available automatic captions" in low:
            section = "auto"
            continue
        if not line.strip() or line.startswith("Language"):
            continue
        if section in ("manual", "auto"):
            code = line.split()[0] if line.split() else ""
            if re.fullmatch(r"[a-z]{2,3}(-[a-zA-Z0-9]+)?", code):
                (manual if section == "manual" else auto).add(code)
    return manual, auto


def pick_lang(prefs: list[str], manual: set[str], auto: set[str]) -> tuple[str, str] | None:
    """Return (lang_code, source) where source is 'manual' or 'auto', or None."""
    for code in prefs:
        if code in manual:
            return code, "manual"
    for code in prefs:
        if code in auto:
            return code, "auto"
    if manual:
        return next(iter(sorted(manual))), "manual"
    if auto:
        return next(iter(sorted(auto))), "auto"
    return None


def download_subs(url: str, lang: str, source: str, ytdlp: str, workdir: Path) -> Path:
    flag = "--write-sub" if source == "manual" else "--write-auto-sub"
    out_template = str(workdir / "%(id)s.%(ext)s")
    proc = run_ytdlp([
        ytdlp, "--ignore-config", flag, "--sub-lang", lang, "--skip-download",
        "--sub-format", "vtt", "-o", out_template, "--no-warnings", "--", url,
    ])
    if proc.returncode != 0:
        sys.stderr.write(f"yt-dlp subtitle download failed:\n{proc.stderr}\n")
        raise RuntimeError(f"yt-dlp subtitle download failed (lang={lang}, source={source}): {proc.stderr.strip()}")
    matches = list(workdir.glob("*.vtt"))
    if not matches:
        sys.stderr.write("yt-dlp reported success but no .vtt file landed\n")
        raise RuntimeError(f"No subtitles available for this video (lang={lang}). Try a different language or enable Whisper transcription.")
    return matches[0]


def clean_vtt(vtt_path: Path) -> str:
    raw = vtt_path.read_text(encoding="utf-8", errors="replace")
    lines = []
    seen_phrases: set[str] = set()
    for line in raw.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if VTT_TIMING_RE.match(line) or VTT_HEADER_RE.match(line):
            continue
        if line.isdigit():
            continue
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if not cleaned:
            continue
        if cleaned in seen_phrases:
            continue
        seen_phrases.add(cleaned)
        lines.append(cleaned)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", text)
    return "\n\n".join(s.strip() for s in sentences if s.strip())


def detect_seeds(transcript: str) -> list[str]:
    low = transcript.lower()
    return [kw for kw in SEED_KEYWORDS if kw in low]


def write_vault_file(
    vault_root: Path, channel_slug: str, upload_date: str,
    video_slug: str, frontmatter: dict, body: str,
) -> Path:
    target_dir = vault_root / "External Inputs" / "YouTube" / channel_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{upload_date}-{video_slug}.md"
    yaml_lines = ["---"]
    for k, v in frontmatter.items():
        yaml_lines.append(f"{k}: {yaml_scalar(v)}")
    yaml_lines.append("---")
    target.write_text("\n".join(yaml_lines) + "\n\n" + body + "\n", encoding="utf-8")
    return target


def write_seed_stub(
    vault_root: Path, upload_date: str, channel_slug: str, video_id: str,
    seeds: list[str], video_url: str, video_title: str,
) -> Path:
    captures_dir = vault_root / "Meta" / "Captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{upload_date}-youtube-{channel_slug}-{video_id}.md"
    target = captures_dir / fname
    body = (
        "---\n"
        "type: capture\n"
        "source: youtube\n"
        f"video_url: {yaml_scalar(video_url)}\n"
        f"detected_at: {yaml_scalar(datetime.now(timezone.utc).isoformat())}\n"
        f"keywords: {yaml_scalar(', '.join(seeds))}\n"
        "status: open\n"
        "---\n\n"
        f"# Capture seed: {markdown_text(video_title)}\n\n"
        f"Trigger keywords detected in transcript: {markdown_text(', '.join(seeds))}.\n\n"
        f"Source: {markdown_text(video_url)}\n\n"
        "## Notes\n\n(fill in)\n"
    )
    target.write_text(body, encoding="utf-8")
    return target


def run_ingest(
    url: str,
    vault_root_path: Path | str | None = None,
    lang_prefs_str: str = "en,es",
    whisper: bool = False,
) -> dict:
    if isinstance(vault_root_path, str):
        vault_root = Path(vault_root_path).resolve()
    else:
        vault_root = Path(vault_root_path or os.environ.get("VAULT_ROOT") or ".").resolve()

    if not vault_root.is_dir():
        return {"success": False, "error": f"Vault root not a directory: {vault_root}"}

    try:
        youtube_url = validate_youtube_url(url)
    except ValueError as exc:
        return {"success": False, "error": f"Invalid YouTube URL: {exc}"}

    try:
        ytdlp = require_bin("yt-dlp")
    except SystemExit:
        return {"success": False, "error": "yt-dlp is not installed on this system."}

    prefs = [c.strip() for c in lang_prefs_str.split(",") if c.strip()]

    try:
        meta = fetch_metadata(youtube_url, ytdlp)
    except SystemExit:
        return {"success": False, "error": "Failed to fetch metadata using yt-dlp."}

    video_id = meta.get("id", "unknown")
    title = meta.get("title", "Untitled")
    channel = meta.get("channel") or meta.get("uploader") or "unknown-channel"
    channel_slug = slugify(channel)
    video_slug = slugify(title)
    upload_date_raw = meta.get("upload_date", "")
    upload_date = (
        f"{upload_date_raw[:4]}-{upload_date_raw[4:6]}-{upload_date_raw[6:8]}"
        if len(upload_date_raw) == 8 else
        datetime.now().strftime("%Y-%m-%d")
    )

    listing = list_subs(youtube_url, ytdlp)
    manual, auto = parse_available_subs(listing)
    pick = pick_lang(prefs, manual, auto)

    sub_source = "none"
    transcript = ""
    lang_code = "und"

    if pick:
        lang_code, sub_source = pick
        try:
            with tempfile.TemporaryDirectory() as td:
                vtt = download_subs(youtube_url, lang_code, sub_source, ytdlp, Path(td))
                transcript = clean_vtt(vtt)
        except Exception as exc:
            sys.stderr.write(f"yt-dlp subtitle download failed: {exc}. Trying fallback...\n")
            pick = None

    if not pick:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            sys.stderr.write("Attempting transcript retrieval via youtube-transcript-api...\n")
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            
            t_obj = None
            for p_lang in prefs:
                try:
                    t_obj = transcript_list.find_manually_created_transcript([p_lang])
                    break
                except Exception:
                    pass
            if not t_obj:
                for p_lang in prefs:
                    try:
                        t_obj = transcript_list.find_generated_transcript([p_lang])
                        break
                    except Exception:
                        pass
            if not t_obj:
                try:
                    t_obj = transcript_list.find_transcript(prefs)
                except Exception:
                    try:
                        t_obj = next(iter(transcript_list))
                    except Exception:
                        pass
                        
            if t_obj:
                lang_code = t_obj.language_code
                sub_source = "manual" if not t_obj.is_generated else "auto"
                data = t_obj.fetch()
                lines = []
                seen_phrases = set()
                for entry in data:
                    text_line = ""
                    if hasattr(entry, 'text'):
                        text_line = entry.text
                    elif isinstance(entry, dict):
                        text_line = entry.get('text', '')
                    else:
                        text_line = str(entry)
                    
                    text_line = text_line.strip()
                    if not text_line:
                        continue
                    text_line = re.sub(r"<[^>]+>", "", text_line).strip()
                    if text_line in seen_phrases:
                        continue
                    seen_phrases.add(text_line)
                    lines.append(text_line)
                
                joined_text = " ".join(lines)
                joined_text = re.sub(r"\s+", " ", joined_text).strip()
                sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", joined_text)
                transcript = "\n\n".join(s.strip() for s in sentences if s.strip())
        except Exception as exc:
            sys.stderr.write(f"youtube-transcript-api fallback failed: {exc}\n")

    if not transcript:
        if whisper:
            sys.stderr.write("Whisper fallback requested but not yet implemented in v0.1.\n")
            sub_source = "none"
        else:
            sys.stderr.write("No subtitles available and --whisper not set. Writing stub.\n")
            sub_source = "none"

    word_count = len(transcript.split()) if transcript else 0
    seeds = detect_seeds(transcript) if transcript else []

    body = transcript or (
        f"# {markdown_text(title)}\n\n"
        f"No subtitles or auto-captions available for this video.\n\n"
        "To capture this transcript, add captions to the source video or transcribe the audio "
        "with your local Whisper workflow and re-run ingest.\n\n"
        f"Source: {markdown_text(youtube_url)}\n"
    )

    fm = {
        "type": "external-input",
        "source": "youtube",
        "video_id": video_id,
        "url": youtube_url,
        "channel": channel,
        "channel_url": meta.get("channel_url", ""),
        "title": title,
        "upload_date": upload_date,
        "duration_seconds": meta.get("duration", 0),
        "language": lang_code,
        "subtitle_source": sub_source,
        "word_count": word_count,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    target = write_vault_file(vault_root, channel_slug, upload_date, video_slug, fm, body)
    seed_paths = []
    if seeds:
        seed_paths.append(
            write_seed_stub(vault_root, upload_date, channel_slug, video_id, seeds, youtube_url, title)
        )

    return {
        "success": True,
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "channel_url": meta.get("channel_url", ""),
        "upload_date": upload_date,
        "duration_seconds": meta.get("duration", 0),
        "language": lang_code,
        "subtitle_source": sub_source,
        "word_count": word_count,
        "target_path": str(target),
        "seed_paths": [str(p) for p in seed_paths],
        "transcript": transcript,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a YouTube video transcript into the vault")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--vault", default=None, help="Vault root path (default: $VAULT_ROOT or .)")
    parser.add_argument("--lang", default="en,es", help="Comma-separated language preference")
    parser.add_argument("--whisper", action="store_true", help="Enable Whisper fallback if no subs")
    args = parser.parse_args()

    result = run_ingest(args.url, args.vault, args.lang, args.whisper)
    if not result.get("success"):
        sys.stderr.write(f"Ingest failed: {result.get('error')}\n")
        return 1

    seed_paths = result.get("seed_paths", [])
    seed_str = f" Seeds at: {', '.join(seed_paths)}." if seed_paths else ""
    print(
        f"Wrote {result.get('word_count')} words to {result.get('target_path')}. "
        f"Language: {result.get('language')}. Subtitle source: {result.get('subtitle_source')}.{seed_str}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
