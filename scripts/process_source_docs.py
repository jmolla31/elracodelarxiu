#!/usr/bin/env python3
"""Process changed source docs into Hugo posts using the BlogEditor instructions."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
BLOG_EDITOR_AGENT = REPO_ROOT / ".github" / "agents" / "BlogEditor.agent.md"
OUTPUT_DIR = REPO_ROOT / "content" / "posts"
REPORT_PATH = REPO_ROOT / ".github" / "tmp" / "blog-editor-report.md"

BASE_REF = os.getenv("BLOG_EDITOR_BASE_REF", "origin/master")
PROVIDER = os.getenv("BLOG_EDITOR_PROVIDER", "github").strip().lower()

if PROVIDER == "github":
    MODEL = os.getenv("BLOG_EDITOR_MODEL", "openai/gpt-4.1-mini")
    API_URL = os.getenv(
        "BLOG_EDITOR_API_URL",
        "https://models.inference.ai.azure.com/chat/completions",
    )
    API_KEY = os.getenv("BLOG_EDITOR_API_KEY") or os.getenv("GITHUB_TOKEN")
elif PROVIDER == "openai":
    MODEL = os.getenv("BLOG_EDITOR_MODEL", "gpt-4o-mini")
    API_URL = os.getenv("BLOG_EDITOR_API_URL", "https://api.openai.com/v1/chat/completions")
    API_KEY = os.getenv("BLOG_EDITOR_API_KEY")
else:
    raise RuntimeError(
        "Unsupported BLOG_EDITOR_PROVIDER. Use 'github' or 'openai'."
    )


@dataclass
class GeneratedPost:
    source_path: Path
    output_path: Path
    title: str
    author: str
    tags: list[str]
    categories: list[str]
    summary: str
    formatting_notes: list[str]


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def changed_source_docs() -> list[Path]:
    diff_output = run_git("diff", "--name-status", f"{BASE_REF}...HEAD", "--", "source_docs")
    docs: list[Path] = []

    for line in diff_output.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            candidate = parts[2]
        elif len(parts) >= 2:
            candidate = parts[1]
        else:
            continue

        if status[0] not in {"A", "M", "R"}:
            continue

        path = REPO_ROOT / candidate
        if path.suffix.lower() == ".md" and path.exists():
            docs.append(path)

    return docs


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", text)
        text = re.sub(r"\n```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Model response did not contain valid JSON")

    return json.loads(match.group(0))


def sanitize_slug(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("_", "-")
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9\-àèéíïòóúüç]", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    if not value:
        raise ValueError("Generated slug is empty")
    return value


def noon_cet_iso() -> str:
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    return noon.isoformat()


def call_model(agent_definition: str, source_name: str, source_markdown: str) -> dict[str, Any]:
    if not API_KEY:
        if PROVIDER == "github":
            raise RuntimeError("Missing token. Set GITHUB_TOKEN or BLOG_EDITOR_API_KEY")
        raise RuntimeError("Missing BLOG_EDITOR_API_KEY secret")

    response_schema = {
        "type": "object",
        "required": [
            "title",
            "slug",
            "author",
            "description",
            "tags",
            "categories",
            "date",
            "content_markdown",
            "summary",
            "formatting_notes",
        ],
        "properties": {
            "title": {"type": "string"},
            "slug": {"type": "string"},
            "author": {"type": "string"},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "categories": {"type": "array", "items": {"type": "string"}},
            "date": {"type": "string"},
            "content_markdown": {"type": "string"},
            "summary": {"type": "string"},
            "formatting_notes": {"type": "array", "items": {"type": "string"}},
        },
    }

    payload = {
        "model": MODEL,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert markdown editor. Follow this agent definition exactly:\n\n"
                    f"{agent_definition}\n\n"
                    "Return only a JSON object matching the required schema. "
                    "Do not include markdown code fences or additional commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Process source document: {source_name}\n\n"
                    "Ensure the final body contains markdown content only (without frontmatter).\n"
                    "Use current day at 12:00:00+01:00 if date is uncertain.\n"
                    "Include concise formatting_notes describing key structural edits.\n\n"
                    "RAW SOURCE:\n"
                    f"{source_markdown}"
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "blog_editor_output",
                "schema": response_schema,
                "strict": True,
            },
        },
    }

    req = request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=180) as res:
            data = json.loads(res.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Model request failed ({exc.code}): {body}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected model response: {json.dumps(data)[:1200]}") from exc

    return extract_json_object(content)


def to_quoted(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def format_frontmatter(payload: dict[str, Any]) -> str:
    title = str(payload["title"]).strip()
    author = str(payload["author"]).strip()
    description = str(payload["description"]).strip()
    date = str(payload.get("date") or "").strip() or noon_cet_iso()

    tags = [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()]
    categories = [str(cat).strip() for cat in payload.get("categories", []) if str(cat).strip()]

    tags_line = ", ".join(to_quoted(tag) for tag in tags)
    categories_line = ", ".join(to_quoted(cat) for cat in categories)

    return "\n".join(
        [
            "---",
            f"title: {to_quoted(title)}",
            f"date: {date}",
            "draft: false",
            f"tags: [{tags_line}]",
            f"categories: [{categories_line}]",
            f"author: {to_quoted(author)}",
            f"description: {to_quoted(description)}",
            "ShowToc: true",
            "TocOpen: true",
            "---",
            "",
        ]
    )


def write_post(payload: dict[str, Any], source_path: Path) -> GeneratedPost:
    slug = sanitize_slug(str(payload["slug"]))
    output_path = OUTPUT_DIR / f"{slug}.md"
    body = str(payload["content_markdown"]).strip() + "\n"
    full_doc = format_frontmatter(payload) + body
    output_path.write_text(full_doc, encoding="utf-8")

    return GeneratedPost(
        source_path=source_path,
        output_path=output_path,
        title=str(payload["title"]).strip(),
        author=str(payload["author"]).strip(),
        tags=[str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()],
        categories=[str(cat).strip() for cat in payload.get("categories", []) if str(cat).strip()],
        summary=str(payload.get("summary") or "").strip(),
        formatting_notes=[
            str(note).strip() for note in payload.get("formatting_notes", []) if str(note).strip()
        ],
    )


def write_report(posts: list[GeneratedPost]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "## Automated Blog Publishing",
        "",
        f"Generated on {datetime.utcnow().isoformat(timespec='seconds')}Z by workflow run.",
        "",
        "### Summary",
        "",
        f"- Source docs processed: {len(posts)}",
        f"- Hugo posts generated: {len(posts)}",
        "- Formatter: BlogEditor agent definition in `.github/agents/BlogEditor.agent.md`",
        "",
        "### Post Details",
        "",
    ]

    for post in posts:
        lines.extend(
            [
                f"#### {post.title}",
                f"- Source file: `{post.source_path.relative_to(REPO_ROOT).as_posix()}`",
                f"- Generated file: `{post.output_path.relative_to(REPO_ROOT).as_posix()}`",
                f"- Author: {post.author}",
                f"- Categories: {', '.join(post.categories) if post.categories else '(none)'}",
                f"- Tags: {', '.join(post.tags) if post.tags else '(none)'}",
                f"- Description: {post.summary or '(not provided)'}",
                "- Formatting notes:",
            ]
        )

        if post.formatting_notes:
            lines.extend([f"  - {note}" for note in post.formatting_notes])
        else:
            lines.append("  - No additional notes provided by formatter")

        lines.append("")

    REPORT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def append_github_output(posts: list[GeneratedPost]) -> None:
    output_file = os.getenv("GITHUB_OUTPUT")
    if not output_file:
        return

    generated_paths = ",".join(
        post.output_path.relative_to(REPO_ROOT).as_posix() for post in posts
    )
    with open(output_file, "a", encoding="utf-8") as fh:
        fh.write(f"processed_count={len(posts)}\n")
        fh.write(f"report_path={REPORT_PATH.relative_to(REPO_ROOT).as_posix()}\n")
        fh.write(f"generated_paths={generated_paths}\n")


def main() -> int:
    if not BLOG_EDITOR_AGENT.exists():
        raise FileNotFoundError(f"Missing agent definition: {BLOG_EDITOR_AGENT}")

    docs = changed_source_docs()
    if not docs:
        print("No changed markdown files under source_docs/.")
        append_github_output([])
        return 0

    agent_text = BLOG_EDITOR_AGENT.read_text(encoding="utf-8")
    generated_posts: list[GeneratedPost] = []

    for doc in docs:
        raw_source = doc.read_text(encoding="utf-8")
        payload = call_model(agent_text, doc.name, raw_source)
        generated = write_post(payload, doc)
        generated_posts.append(generated)
        print(f"Generated {generated.output_path.relative_to(REPO_ROOT).as_posix()} from {doc.name}")

    write_report(generated_posts)
    append_github_output(generated_posts)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover - used for workflow diagnostics
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)