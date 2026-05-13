#!/usr/bin/env python3
"""
链研观察 — 自动发布到 GitHub Pages
Usage:
  公开简报: python3 publish.py --title "标题" --date "2026-05-13" --desc "简介" --body "HTML内容"
  私密板块: python3 publish.py --title "标题" --date "2026-05-13" --desc "简介" --body "HTML内容" --section chain|launch|hkipo
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
PRIVATE_DIR = os.path.join(REPO_DIR, 'private')
INDEX_JSON = os.path.join(POSTS_DIR, 'index.json')

SECTION_MAP = {
    'chain': {'dir': 'chain', 'name': '链上热点扫描'},
    'launch': {'dir': 'launch', 'name': 'Crypto Launch & 融资'},
    'hkipo': {'dir': 'hkipo', 'name': '港股打新日报'},
}

def load_index(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []

def save_index(posts, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

def slugify(text):
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
    parser.add_argument('--section', choices=['chain', 'launch', 'hkipo'], default=None,
                        help='Private section (omit for public brief)')
    parser.add_argument('--no-push', action='store_true', help='Skip git push')
    args = parser.parse_args()

    # Validate body is not empty
    if not args.body or not args.body.strip():
        print('❌ Error: --body is empty, aborting')
        sys.exit(1)

    # Determine output directory and template
    date_prefix = args.date.replace('-', '')

    if args.section:
        # Private section
        section_info = SECTION_MAP[args.section]
        section_dir = os.path.join(PRIVATE_DIR, section_info['dir'])
        os.makedirs(section_dir, exist_ok=True)
        template_path = os.path.join(PRIVATE_DIR, 'template.html')
        index_path = os.path.join(section_dir, 'index.json')
        slug = f"{date_prefix}-{args.section}"
        output_path = os.path.join(section_dir, f'{slug}.html')
        commit_msg = f'🔒 {args.date} {section_info["name"]}'
    else:
        # Public brief
        template_path = os.path.join(POSTS_DIR, 'template.html')
        index_path = INDEX_JSON
        slug = f"{date_prefix}-{slugify(args.title)}"
        output_path = os.path.join(POSTS_DIR, f'{slug}.html')
        commit_msg = f'📝 {args.date} 每日简报'

    desc = args.desc or html_to_text(args.body)[:120]

    # Load template
    with open(template_path) as f:
        template = f.read()

    # Format date for display
    try:
        dt = datetime.strptime(args.date, '%Y-%m-%d')
        weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        date_display = f"{dt.strftime('%Y年%m月%d日')} {weekdays[dt.weekday()]}"
    except:
        date_display = args.date

    # Build HTML
    html = template.replace('{{TITLE}}', args.title)
    html = html.replace('{{DATE}}', date_display)
    html = html.replace('{{DESC}}', desc)
    html = html.replace('{{CONTENT}}', args.body)

    # Write article file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    # Update index
    posts = load_index(index_path)
    posts = [p for p in posts if p.get('date') != args.date]
    posts.insert(0, {
        'slug': slug,
        'title': args.title,
        'date': args.date,
        'desc': desc
    })
    save_index(posts, index_path)

    # Git commit & push
    if not args.no_push:
        os.chdir(REPO_DIR)
        subprocess.run(['git', 'add', '.'], check=True)
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
        result = subprocess.run(['git', 'push'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f'✅ Published: {output_path}')
        else:
            print(f'⚠️ Git push issue: {result.stderr[:200]}')
    else:
        print(f'✅ Written (no push): {output_path}')

if __name__ == '__main__':
    main()
