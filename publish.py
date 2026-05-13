#!/usr/bin/env python3
"""
旺财每日简报 — 自动发布到 GitHub Pages
Usage: python3 publish.py --title "标题" --date "2026-05-13" --desc "简介" --body "HTML内容"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(REPO_DIR, 'posts')
INDEX_JSON = os.path.join(POSTS_DIR, 'index.json')

def load_index():
    if os.path.exists(INDEX_JSON):
        with open(INDEX_JSON) as f:
            return json.load(f)
    return []

def save_index(posts):
    with open(INDEX_JSON, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

def slugify(text):
    # Date-prefix ensures uniqueness; title part can be empty (use 'brief' as fallback)
    return 'brief'

def html_to_text(html):
    """Strip HTML tags for meta description."""
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:160]

def main():
    parser = argparse.ArgumentParser(description='Publish daily brief to GitHub Pages')
    parser.add_argument('--title', required=True, help='Article title')
    parser.add_argument('--date', required=True, help='Date (YYYY-MM-DD)')
    parser.add_argument('--desc', default='', help='Short description')
    parser.add_argument('--body', required=True, help='HTML body content')
    args = parser.parse_args()

    # Generate slug (date-prefixed for uniqueness)
    date_prefix = args.date.replace('-', '')
    slug = f"{date_prefix}-{slugify(args.title)}"
    desc = args.desc or html_to_text(args.body)[:120]

    # Load template
    template_path = os.path.join(POSTS_DIR, 'template.html')
    with open(template_path) as f:
        template = f.read()

    # Format date for display
    try:
        dt = datetime.strptime(args.date, '%Y-%m-%d')
        date_display = dt.strftime('%Y年%m月%d日 %A')
    except:
        date_display = args.date

    # Build HTML
    html = template.replace('{{TITLE}}', args.title)
    html = html.replace('{{DATE}}', date_display)
    html = html.replace('{{DESC}}', desc)
    html = html.replace('{{CONTENT}}', args.body)

    # Write article file
    article_path = os.path.join(POSTS_DIR, f'{slug}.html')
    with open(article_path, 'w', encoding='utf-8') as f:
        f.write(html)

    # Update index
    posts = load_index()
    # Remove existing entry for same date
    posts = [p for p in posts if p.get('date') != args.date]
    posts.insert(0, {
        'slug': slug,
        'title': args.title,
        'date': args.date,
        'desc': desc
    })
    save_index(posts)

    # Git commit & push
    os.chdir(REPO_DIR)
    subprocess.run(['git', 'add', '.'], check=True)
    subprocess.run(['git', 'commit', '-m', f'📝 {args.date} 每日简报'], check=True)
    result = subprocess.run(['git', 'push'], capture_output=True, text=True)
    if result.returncode == 0:
        print(f'✅ Published: {slug}.html')
    else:
        print(f'⚠️ Git push issue: {result.stderr[:200]}')

if __name__ == '__main__':
    main()
