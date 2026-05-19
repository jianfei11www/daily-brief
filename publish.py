#!/usr/bin/env python3
"""
链研观察 — 自动发布到 GitHub Pages
Usage:
  完整晨报: python3 publish.py --title "标题" --date "2026-05-14" --desc "简介" --body "HTML内容"
  私密板块: python3 publish.py --title "标题" --date "2026-05-14" --desc "简介" --body "HTML内容" --section chain|launch|hkipo
  三段式:   python3 publish.py --title "标题" --date "2026-05-14" --desc "简介" --part1 "HTML" --part2 "HTML" --part3 "HTML"
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
    'stock': {'dir': 'stock', 'name': '股票投研'},
    'gpt': {'dir': 'gpt', 'name': 'GPT每日简报'},
}


def load_index(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_index(posts, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def html_to_text(html):
    """Strip HTML tags for meta description."""
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:160]


def format_date(date_str):
    """Format YYYY-MM-DD to Chinese display."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
        # Avoid locale-dependent strftime behavior with non-ASCII literals.
        # Some environments return empty strings for formats like '%Y年%m月%d日'.
        date_cn = f"{dt.year}年{dt.month:02d}月{dt.day:02d}日"
        return f"{date_cn} {weekdays[dt.weekday()]}"
    except:
        return date_str


def publish_page(template_path, output_path, title, date_display, desc, body):
    """Generate and write a single HTML page."""
    with open(template_path) as f:
        template = f.read()
    html = template.replace('{{TITLE}}', title)
    html = html.replace('{{DATE}}', date_display)
    html = html.replace('{{DESC}}', desc)
    html = html.replace('{{CONTENT}}', body)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


def git_push(commit_msg):
    """Git add, commit, push."""
    os.chdir(REPO_DIR)
    subprocess.run(['git', 'add', '.'], check=True)
    result = subprocess.run(['git', 'commit', '-m', commit_msg],
                           capture_output=True, text=True)
    if result.returncode != 0:
        if 'nothing to commit' in result.stdout + result.stderr:
            print('⚠️ Nothing to commit')
            return
        print(f'❌ Commit failed: {result.stderr[:200]}')
        return
    result = subprocess.run(['git', 'push'], capture_output=True, text=True)
    if result.returncode == 0:
        print('✅ Pushed to GitHub Pages')
    else:
        print(f'⚠️ Push issue: {result.stderr[:200]}')


def main():
    parser = argparse.ArgumentParser(description='Publish daily brief')
    parser.add_argument('--title', required=True, help='Article title')
    parser.add_argument('--date', required=True, help='Date (YYYY-MM-DD)')
    parser.add_argument('--desc', default='', help='Short description')
    parser.add_argument('--body', default='', help='Full HTML body')
    parser.add_argument('--part1', default='', help='Part1 区块链 HTML')
    parser.add_argument('--part2', default='', help='Part2 港股打新 HTML')
    parser.add_argument('--part3', default='', help='Part3 宏观科技 HTML')
    parser.add_argument('--section', choices=['chain', 'launch', 'hkipo', 'stock', 'gpt'],
                        default=None, help='Private section')
    parser.add_argument('--no-push', action='store_true', help='Skip git push')
    args = parser.parse_args()

    date_prefix = args.date.replace('-', '')
    date_display = format_date(args.date)
    desc = args.desc or '区块链/港股/宏观科技 每日简报'

    # 三段式模式：同时生成公开页+私密页
    if args.part1 or args.part2 or args.part3:
        published = []

        # 公开页（Part1 区块链部分，去掉敏感投资建议）
        full_body = ''
        if args.part1:
            full_body += args.part1
        if args.part2:
            full_body += '\n<hr>\n' + args.part2
        if args.part3:
            full_body += '\n<hr>\n' + args.part3

        if full_body:
            # 公开版（完整三段）
            slug = f"{date_prefix}-brief"
            output = publish_page(
                os.path.join(POSTS_DIR, 'template.html'),
                os.path.join(POSTS_DIR, f'{slug}.html'),
                args.title, date_display, desc, full_body
            )
            published.append(output)

            # 更新公开index
            posts = load_index(INDEX_JSON)
            posts = [p for p in posts if p.get('date') != args.date]
            posts.insert(0, {
                'slug': slug, 'title': args.title,
                'date': args.date, 'desc': desc
            })
            save_index(posts, INDEX_JSON)

        # 私密页（各Part单独存档）
        priv_template = os.path.join(PRIVATE_DIR, 'template.html')

        if args.part2:
            sec_dir = os.path.join(PRIVATE_DIR, 'hkipo')
            slug2 = f"{date_prefix}-hkipo"
            out2 = publish_page(priv_template,
                os.path.join(sec_dir, f'{slug2}.html'),
                f'港股打新 {args.date}', date_display, '港股打新', args.part2)
            published.append(out2)
            idx = load_index(os.path.join(sec_dir, 'index.json'))
            idx = [p for p in idx if p.get('date') != args.date]
            idx.insert(0, {'slug': slug2, 'title': f'港股打新 {args.date}',
                           'date': args.date, 'desc': '港股打新日报'})
            save_index(idx, os.path.join(sec_dir, 'index.json'))

        if args.part1:
            sec_dir = os.path.join(PRIVATE_DIR, 'chain')
            slug1 = f"{date_prefix}-chain"
            out1 = publish_page(priv_template,
                os.path.join(sec_dir, f'{slug1}.html'),
                f'链上热点 {args.date}', date_display, '链上热点扫描', args.part1)
            published.append(out1)
            idx = load_index(os.path.join(sec_dir, 'index.json'))
            idx = [p for p in idx if p.get('date') != args.date]
            idx.insert(0, {'slug': slug1, 'title': f'链上热点 {args.date}',
                           'date': args.date, 'desc': '区块链行业动态'})
            save_index(idx, os.path.join(sec_dir, 'index.json'))

        if not args.no_push:
            git_push(f'📊 {args.date} 每日简报（三段式）')

        for p in published:
            print(f'✅ Published: {p}')
        return

    # 单页模式（兼容旧调用）
    if not args.body or not args.body.strip():
        print('❌ Error: --body is empty, aborting')
        sys.exit(1)

    if args.section:
        section_info = SECTION_MAP[args.section]
        section_dir = os.path.join(PRIVATE_DIR, section_info['dir'])
        template_path = os.path.join(PRIVATE_DIR, 'template.html')
        index_path = os.path.join(section_dir, 'index.json')
        slug = f"{date_prefix}-{args.section}"
        output_path = os.path.join(section_dir, f'{slug}.html')
        commit_msg = f'🔒 {args.date} {section_info["name"]}'
    else:
        template_path = os.path.join(POSTS_DIR, 'template.html')
        index_path = INDEX_JSON
        slug = f"{date_prefix}-brief"
        output_path = os.path.join(POSTS_DIR, f'{slug}.html')
        commit_msg = f'📝 {args.date} 每日简报'

    desc = args.desc or html_to_text(args.body)[:120]
    publish_page(template_path, output_path, args.title, date_display, desc, args.body)

    posts = load_index(index_path)
    posts = [p for p in posts if p.get('date') != args.date]
    posts.insert(0, {
        'slug': slug, 'title': args.title,
        'date': args.date, 'desc': desc
    })
    save_index(posts, index_path)

    if not args.no_push:
        git_push(commit_msg)

    print(f'✅ Published: {output_path}')


if __name__ == '__main__':
    main()
