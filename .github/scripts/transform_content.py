#!/usr/bin/env python3
"""
Blog Content Transformer
Uses LLM (GitHub Models API) to transform source_docs/ into Hugo posts
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List
import frontmatter
import requests
from openai import OpenAI


class BlogTransformer:
    """Transforms raw markdown from source_docs/ into Hugo posts using LLM"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent.parent
        self.source_dir = self.repo_root / "source_docs"
        self.posts_dir = self.repo_root / "content" / "posts"
        self.images_dir = self.repo_root / "static" / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.posts_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize GitHub Models API client
        github_token = os.environ.get('GITHUB_TOKEN')
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
            
        self.client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=github_token,
        )
        
        # Load BlogEditor agent instructions
        self.agent_instructions = self.load_agent_instructions()
    
    def load_agent_instructions(self) -> str:
        """Load BlogEditor agent instructions from .github/agents/"""
        agent_file = self.repo_root / ".github" / "agents" / "BlogEditor.agent.md"
        
        if not agent_file.exists():
            print("Warning: BlogEditor.agent.md not found, using default instructions")
            return """You are a Blog Editor Agent. Transform the provided raw blog post into a well-structured Hugo markdown post.

Follow these rules:
- Keep main text verbatim, only format and organize
- Use professional style for investigative/historical content
- Generate proper Hugo frontmatter with: title, date (at 12:00 PM), tags (list), categories (list), description (150-200 chars), author: "El Racó de l'Arxiu", ShowToc: true, TocOpen: true
- Note any image URLs for later download
- Wrap lines to ~120 characters
- Use Hugo shortcodes for YouTube ({{< youtube VIDEO_ID >}}) and Instagram ({{< instagram POST_ID >}})
- Add table of contents structure with headings
- Format bibliographic references as unordered list at the end
- Output ONLY the complete Hugo markdown file with YAML frontmatter"""
        
        with open(agent_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract the actual instructions (remove frontmatter)
        parts = content.split('---', 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content
    
    def get_changed_files(self) -> List[Path]:
        """Read changed files from git diff"""
        changed_file = self.repo_root / "changed_files.txt"
        if not changed_file.exists():
            # If no change tracking, process all source docs
            return list(self.source_dir.glob("*.md"))
            
        with open(changed_file) as f:
            files = [line.strip() for line in f if line.strip()]
            
        return [self.repo_root / f for f in files if f.startswith('source_docs/')]
    
    def transform_with_llm(self, source_content: str, source_filename: str) -> str:
        """Use GitHub Models API to transform content with BlogEditor instructions"""
        print(f"🤖 Sending to LLM (GPT-4o via GitHub Models)...")
        
        user_prompt = f"""Transform this raw blog post into a Hugo-formatted markdown post.

Source filename: {source_filename}
Current date: {datetime.now().strftime('%Y-%m-%d')}

Raw content:
{source_content}

CRITICAL REQUIREMENTS:
1. Generate YAML frontmatter at the top with these EXACT fields:
   - title: "Post Title"
   - date: {datetime.now().strftime('%Y-%m-%d')}T12:00:00+01:00
   - draft: false
   - tags: ["tag1", "tag2", "tag3"]
   - categories: ["Història"]
   - author: "El Racó de l'Arxiu"
   - description: "150-200 character summary"
   - ShowToc: true
   - TocOpen: true

2. Keep the main text content VERBATIM from the source
3. Format for readability with proper headings (##, ###)
4. If there are YouTube URLs, convert to: {{{{< youtube VIDEO_ID >}}}}
5. If there are Instagram URLs, convert to: {{{{< instagram POST_ID >}}}}
6. Wrap long text lines to ~120 characters
7. Format bibliography as unordered list (- item) at the end

Return ONLY the complete Hugo markdown file with frontmatter enclosed in --- markers."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.agent_instructions},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            transformed_content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            print(f"✅ LLM transformation complete ({tokens_used} tokens used)")
            return transformed_content
            
        except Exception as e:
            print(f"❌ Error calling GitHub Models API: {e}", file=sys.stderr)
            raise
    
    def download_image(self, url: str, post_slug: str) -> str:
        """Download image from URL and return local path"""
        try:
            print(f"  📥 Downloading image: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Extract filename from URL
            filename = os.path.basename(url.split('?')[0])
            if not filename or not any(filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                filename = f"{post_slug}_image.jpg"
            else:
                # Prefix with post slug to avoid conflicts
                filename = f"{post_slug}_{filename}"
            
            local_path = self.images_dir / filename
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
                
            print(f"  ✅ Saved: {filename}")
            return f"/images/{filename}"
            
        except Exception as e:
            print(f"  ⚠️  Failed to download {url}: {e}")
            return url  # Return original URL if download fails
    
    def process_images(self, content: str, post_slug: str) -> str:
        """Download external images and update references"""
        # Match markdown images: ![alt](url)
        image_pattern = r'!\[([^\]]*)\]\((https?://[^\)]+)\)'
        
        def replace_image(match):
            alt_text = match.group(1)
            url = match.group(2)
            local_path = self.download_image(url, post_slug)
            return f"![{alt_text}]({local_path})"
        
        return re.sub(image_pattern, replace_image, content)
    
    def generate_slug(self, title: str) -> str:
        """Generate URL-friendly slug from title"""
        # Remove accents and convert to lowercase
        slug = title.lower()
        # Replace spaces and special chars with hyphens
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    def transform_content(self, source_file: Path) -> None:
        """Transform a single source document into a Hugo post using LLM"""
        print(f"\n{'='*60}")
        print(f"📝 Transforming: {source_file.name}")
        print(f"{'='*60}")
        
        # Read source file
        with open(source_file, 'r', encoding='utf-8') as f:
            source_content = f.read()
        
        # Transform with LLM
        transformed_content = self.transform_with_llm(source_content, source_file.name)
        
        # Parse the LLM output to extract frontmatter and content
        try:
            post = frontmatter.loads(transformed_content)
            print(f"✅ Parsed frontmatter successfully")
        except Exception as e:
            print(f"⚠️  Could not parse LLM output as frontmatter: {e}")
            print("Raw LLM output:")
            print(transformed_content[:500])
            raise
        
        # Generate slug from title
        title = post.metadata.get('title', source_file.stem)
        slug = self.generate_slug(title)
        print(f"📎 Slug: {slug}")
        
        # Process images (download any external URLs)
        images_before = len(re.findall(r'!\[[^\]]*\]\((https?://[^\)]+)\)', post.content))
        if images_before > 0:
            print(f"🖼️  Processing {images_before} external image(s)...")
            post.content = self.process_images(post.content, slug)
        
        # Write to content/posts/
        output_file = self.posts_dir / f"{slug}.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))
        
        print(f"✅ Created: content/posts/{slug}.md")
        print(f"{'='*60}\n")
    
    def run(self):
        """Main transformation process"""
        changed_files = self.get_changed_files()
        
        if not changed_files:
            print("No source documents to transform")
            return
        
        print(f"\n🚀 Starting content transformation")
        print(f"📂 Found {len(changed_files)} file(s) to transform\n")
        
        for source_file in changed_files:
            try:
                self.transform_content(source_file)
            except Exception as e:
                print(f"❌ Error transforming {source_file}: {e}", file=sys.stderr)
                sys.exit(1)
        
        print("\n🎉 Transformation complete!")


if __name__ == "__main__":
    transformer = BlogTransformer()
    transformer.run()
