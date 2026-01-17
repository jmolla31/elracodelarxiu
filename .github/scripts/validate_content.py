#!/usr/bin/env python3
"""
Content Validator
Validates transformed blog posts for completeness and correctness
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import frontmatter


class ContentValidator:
    """Validates Hugo blog posts"""
    
    def __init__(self):
        self.repo_root = Path(__file__).parent.parent.parent
        self.posts_dir = self.repo_root / "content" / "posts"
        self.images_dir = self.repo_root / "static" / "images"
        self.errors = []
        self.warnings = []
        
    def validate_frontmatter(self, post_file: Path, metadata: Dict) -> bool:
        """Validate frontmatter has required fields"""
        required_fields = ['title', 'date', 'tags', 'categories', 'description', 'author']
        recommended_fields = ['ShowToc', 'TocOpen']
        
        valid = True
        
        # Check required fields
        for field in required_fields:
            if field not in metadata or not metadata[field]:
                self.errors.append(f"{post_file.name}: Missing required field '{field}'")
                valid = False
        
        # Check field types and constraints
        if 'description' in metadata:
            desc_len = len(metadata['description'])
            if desc_len < 150 or desc_len > 250:
                self.warnings.append(
                    f"{post_file.name}: Description length {desc_len} chars "
                    f"(should be 150-200 chars)"
                )
        
        if 'tags' in metadata:
            if not isinstance(metadata['tags'], list):
                self.errors.append(f"{post_file.name}: 'tags' should be a list")
                valid = False
            elif len(metadata['tags']) == 0:
                self.warnings.append(f"{post_file.name}: No tags specified")
        
        if 'categories' in metadata:
            if not isinstance(metadata['categories'], list):
                self.errors.append(f"{post_file.name}: 'categories' should be a list")
                valid = False
            elif len(metadata['categories']) == 0:
                self.warnings.append(f"{post_file.name}: No categories specified")
        
        # Check recommended fields
        for field in recommended_fields:
            if field not in metadata:
                self.warnings.append(f"{post_file.name}: Recommended field '{field}' not set")
        
        return valid
    
    def validate_images(self, post_file: Path, content: str) -> bool:
        """Validate that referenced images exist"""
        # Find all markdown images: ![alt](path)
        image_pattern = r'!\[.*?\]\(([^)]+)\)'
        images = re.findall(image_pattern, content)
        
        valid = True
        
        for image_path in images:
            # Skip external URLs
            if image_path.startswith('http://') or image_path.startswith('https://'):
                self.warnings.append(
                    f"{post_file.name}: External image URL not downloaded: {image_path}"
                )
                continue
            
            # Check if local image exists
            if image_path.startswith('/images/'):
                local_path = self.repo_root / "static" / image_path.lstrip('/')
            else:
                local_path = self.repo_root / image_path.lstrip('/')
            
            if not local_path.exists():
                self.errors.append(
                    f"{post_file.name}: Image not found: {image_path} "
                    f"(looked for {local_path})"
                )
                valid = False
        
        return valid
    
    def validate_links(self, post_file: Path, content: str) -> bool:
        """Validate internal links"""
        # Find all markdown links: [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        links = re.findall(link_pattern, content)
        
        valid = True
        
        for link_text, link_url in links:
            # Skip external URLs, anchors, and mailto links
            if (link_url.startswith('http://') or 
                link_url.startswith('https://') or 
                link_url.startswith('#') or
                link_url.startswith('mailto:')):
                continue
            
            # Check internal links
            if link_url.startswith('/'):
                # Absolute path from site root
                if link_url.startswith('/posts/'):
                    internal_path = self.posts_dir / link_url.replace('/posts/', '')
                else:
                    internal_path = self.repo_root / "content" / link_url.lstrip('/')
            else:
                # Relative path
                internal_path = post_file.parent / link_url
            
            # Remove .html extension if present (Hugo generates these)
            if internal_path.suffix == '.html':
                internal_path = internal_path.with_suffix('.md')
            
            if not internal_path.exists():
                self.warnings.append(
                    f"{post_file.name}: Internal link may be broken: {link_url}"
                )
        
        return valid
    
    def validate_shortcodes(self, post_file: Path, content: str) -> bool:
        """Validate Hugo shortcodes are properly formatted"""
        # Find all Hugo shortcodes: {{< shortcode params >}}
        shortcode_pattern = r'\{\{<\s*(\w+)\s*([^>]*?)\s*>\}\}'
        shortcodes = re.findall(shortcode_pattern, content)
        
        valid = True
        supported_shortcodes = ['youtube', 'instagram', 'figure', 'collapse']
        
        for shortcode_name, params in shortcodes:
            if shortcode_name not in supported_shortcodes:
                self.warnings.append(
                    f"{post_file.name}: Unknown shortcode '{shortcode_name}' "
                    f"(supported: {', '.join(supported_shortcodes)})"
                )
            
            # Validate YouTube shortcode has video ID
            if shortcode_name == 'youtube':
                if not params or len(params.strip()) < 10:
                    self.errors.append(
                        f"{post_file.name}: YouTube shortcode missing video ID"
                    )
                    valid = False
            
            # Validate Instagram shortcode has post ID
            if shortcode_name == 'instagram':
                if not params or len(params.strip()) < 5:
                    self.errors.append(
                        f"{post_file.name}: Instagram shortcode missing post ID"
                    )
                    valid = False
        
        # Check for malformed shortcodes (missing closing tags)
        malformed = re.findall(r'\{\{<\s*\w+(?!\s*>\}\})', content)
        if malformed:
            self.errors.append(
                f"{post_file.name}: Malformed shortcode detected (missing closing tag)"
            )
            valid = False
        
        return valid
    
    def validate_line_length(self, post_file: Path, content: str) -> bool:
        """Check for excessively long lines"""
        lines = content.split('\n')
        long_lines = []
        
        for i, line in enumerate(lines, 1):
            # Skip code blocks, headings, images, links, and shortcodes
            if (line.startswith('```') or 
                line.startswith('#') or 
                line.startswith('![') or
                line.startswith('{{<') or
                line.strip().startswith('-') or
                len(line) <= 120):
                continue
            
            if len(line) > 150:  # Allow some tolerance beyond 120
                long_lines.append((i, len(line)))
        
        if long_lines:
            for line_num, length in long_lines[:3]:  # Report first 3
                self.warnings.append(
                    f"{post_file.name}: Line {line_num} is {length} chars "
                    f"(recommend ~120 chars max)"
                )
        
        return True
    
    def validate_post(self, post_file: Path) -> bool:
        """Validate a single post"""
        print(f"Validating: {post_file.name}")
        
        try:
            with open(post_file, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
        except Exception as e:
            self.errors.append(f"{post_file.name}: Failed to parse: {e}")
            return False
        
        valid = True
        
        # Run all validation checks
        valid &= self.validate_frontmatter(post_file, post.metadata)
        valid &= self.validate_images(post_file, post.content)
        valid &= self.validate_links(post_file, post.content)
        valid &= self.validate_shortcodes(post_file, post.content)
        valid &= self.validate_line_length(post_file, post.content)
        
        return valid
    
    def get_changed_posts(self) -> List[Path]:
        """Get list of changed/new posts from git diff"""
        changed_file = self.repo_root / "changed_files.txt"
        
        if not changed_file.exists():
            # Validate all posts if no change list
            return list(self.posts_dir.glob("*.md"))
        
        with open(changed_file) as f:
            files = [line.strip() for line in f if line.strip()]
        
        changed_posts = []
        for file_path in files:
            if file_path.startswith('content/posts/'):
                full_path = self.repo_root / file_path
                if full_path.exists():
                    changed_posts.append(full_path)
        
        return changed_posts
    
    def run(self) -> int:
        """Run validation on changed posts"""
        posts = self.get_changed_posts()
        
        if not posts:
            print("No posts to validate")
            return 0
        
        print(f"Validating {len(posts)} post(s)...\n")
        
        all_valid = True
        for post_file in posts:
            valid = self.validate_post(post_file)
            all_valid &= valid
        
        # Print summary
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  • {error}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        if not self.errors and not self.warnings:
            print("\n✅ All validations passed!")
        elif not self.errors:
            print(f"\n✅ Validation passed with {len(self.warnings)} warning(s)")
        
        # Exit with error code if there are errors
        return 1 if self.errors else 0


if __name__ == "__main__":
    validator = ContentValidator()
    sys.exit(validator.run())
