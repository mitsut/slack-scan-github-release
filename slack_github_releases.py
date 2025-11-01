#!/usr/bin/env python3
"""
Slackチャンネルから1週間分のGitHubリリース通知を抽出するスクリプト
"""

import os
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackGitHubReleaseScanner:
    def __init__(self, token: str, channel_name: str = "notification-development"):
        """
        Args:
            token: Slack Bot Token (xoxb-で始まるトークン)
            channel_name: スキャンするチャンネル名
        """
        self.client = WebClient(token=token)
        self.channel_name = channel_name
        self.channel_id = None

    def get_channel_id(self) -> str:
        """チャンネル名からチャンネルIDを取得"""
        if self.channel_id:
            return self.channel_id

        try:
            # チャンネル一覧を取得
            result = self.client.conversations_list(types="public_channel,private_channel")
            for channel in result["channels"]:
                if channel["name"] == self.channel_name:
                    self.channel_id = channel["id"]
                    return self.channel_id

            raise ValueError(f"チャンネル '{self.channel_name}' が見つかりません")
        except SlackApiError as e:
            raise Exception(f"チャンネルID取得エラー: {e.response['error']}")

    def fetch_messages(self, days: int = 7) -> List[Dict]:
        """
        指定した日数分のメッセージを取得

        Args:
            days: 過去何日分のメッセージを取得するか（デフォルト: 7日）

        Returns:
            メッセージのリスト
        """
        print(f"チャンネル '{self.channel_name}' から過去{days}日分のメッセージを取得中...")
        channel_id = self.get_channel_id()
        oldest = (datetime.now() - timedelta(days=days)).timestamp()

        messages = []
        try:
            # チャンネルの履歴を取得
            result = self.client.conversations_history(
                channel=channel_id,
                oldest=oldest,
                limit=1000  # 最大1000件
            )
            messages = result["messages"]

            # ページネーション対応
            while result.get("has_more"):
                result = self.client.conversations_history(
                    channel=channel_id,
                    oldest=oldest,
                    cursor=result["response_metadata"]["next_cursor"],
                    limit=1000
                )
                messages.extend(result["messages"])

            return messages
        except SlackApiError as e:
            raise Exception(f"メッセージ取得エラー: {e.response['error']}")

    def parse_release_notifications(self, messages: List[Dict]) -> List[Dict]:
        """
        メッセージからGitHubリリース通知を抽出

        Returns:
            抽出したリリース情報のリスト
            [{
                'repository': 'owner/repo',
                'version': 'v1.0.0',
                'release_date': datetime,
                'url': 'https://github.com/...'
            }, ...]
        """
        releases = []

        for message in messages:
            # メッセージの添付ファイルから "New release" を検索
            attachments = message.get("attachments", [])

            # Attachmentの中にリリース通知があるか確認
            has_release = False
            for attachment in attachments:
                fallback = attachment.get("fallback", "")
                if "New release" in fallback:
                    has_release = True
                    break

            # リリース通知が見つからない場合はスキップ
            if not has_release:
                continue

            # タイムスタンプを日時に変換
            ts = float(message.get("ts", 0))
            msg_datetime = datetime.fromtimestamp(ts)

            # リポジトリ名、バージョン、URLの初期化
            repo_match = None
            version_match = None
            url_match = None

            # パターン定義
            repo_pattern = r'(?:in|for)\s+([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)'
            version_pattern = r'\b(v?\d+\.\d+\.\d+(?:[.-][a-zA-Z0-9]+)?)\b'
            # URLパターン: /releases/tag/xxx まで（|などの特殊文字を除外）
            url_pattern = r'https://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+/releases/tag/[a-zA-Z0-9_.-]+'

            # attachmentsから情報を取得
            for attachment in attachments:
                fallback = attachment.get("fallback", "")
                title = attachment.get("title", "")
                text = attachment.get("text", "")
                title_link = attachment.get("title_link", "")

                # Fallback、Title、Textから情報を抽出
                search_text = f"{fallback} {title} {text}"

                if not repo_match:
                    repo_match = re.search(repo_pattern, search_text)
                if not version_match:
                    version_match = re.search(version_pattern, search_text)
                if not url_match:
                    url_match = re.search(url_pattern, search_text)

                # title_linkからURLを取得
                if not url_match and title_link:
                    if "github.com" in title_link and "/releases/" in title_link:
                        # |などの特殊文字の前で終了
                        clean_link = title_link.split('|')[0].split('>')[0].strip()
                        url_match = re.search(url_pattern, clean_link)

            # blocksからも情報を取得
            blocks = message.get("blocks", [])
            for block in blocks:
                if block.get("type") == "section" and block.get("text"):
                    block_text = block["text"].get("text", "")
                    if not repo_match:
                        repo_match = re.search(repo_pattern, block_text)
                    if not version_match:
                        version_match = re.search(version_pattern, block_text)
                    if not url_match:
                        url_match = re.search(url_pattern, block_text)

            # リポジトリ名の取得
            repository = None
            if repo_match:
                repository = repo_match.group(1)
            elif url_match:
                # URLからリポジトリ名を抽出
                url = url_match.group(0)
                url_repo_match = re.search(r'github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)', url)
                if url_repo_match:
                    repository = url_repo_match.group(1)

            # リリース情報を追加
            release_info = {
                'repository': repository or 'Unknown',
                'version': version_match.group(1) if version_match else 'Unknown',
                'release_date': msg_datetime,
                'url': url_match.group(0) if url_match else None,
            }
            releases.append(release_info)

        # リリース日時でソート（新しい順）
        releases.sort(key=lambda x: x['release_date'], reverse=True)

        return releases

    def fetch_release_notes(self, url: str) -> Optional[str]:
        """
        GitHubのリリースURLからリリースノートを取得

        Args:
            url: GitHubのリリースURL

        Returns:
            リリースノート（取得失敗時はNone）
        """
        if not url:
            return None

        try:
            # GitHub API URLに変換
            # https://github.com/owner/repo/releases/tag/v1.0.0
            # → https://api.github.com/repos/owner/repo/releases/tags/v1.0.0
            match = re.search(r'github\.com/([^/]+)/([^/]+)/releases/tag/(.+)', url)
            if not match:
                print(f"  ⚠️ URL形式が不正: {url}")
                return None

            owner, repo, tag = match.groups()
            # URLデコードされている場合があるので、タグ部分をクリーンアップ
            tag = tag.split('?')[0].split('#')[0].strip()

            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"

            # GitHub APIにリクエスト
            headers = {}
            github_token = os.environ.get("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"token {github_token}"

            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                body = data.get("body", "")
                if body:
                    return body
                else:
                    print(f"  ℹ️ リリースノートが空です")
                    return None
            else:
                print(f"  ⚠️ GitHub API エラー (status={response.status_code}): {api_url}")
                return None

        except Exception as e:
            print(f"  ⚠️ リリースノート取得エラー ({url}): {e}")
            return None

    def scan_releases(self, days: int = 7, fetch_notes: bool = False) -> List[Dict]:
        """
        指定した期間のリリース情報をスキャン

        Args:
            days: 過去何日分をスキャンするか
            fetch_notes: リリースノートを取得するか

        Returns:
            リリース情報のリスト
        """
        messages = self.fetch_messages(days)
        print(f"{len(messages)}件のメッセージを取得しました")

        print("GitHubリリース通知を解析中...")
        releases = self.parse_release_notifications(messages)
        print(f"{len(releases)}件のリリース通知を見つけました")

        # リリースノートを取得
        if fetch_notes and releases:
            print("\nリリースノートを取得中...")
            for i, release in enumerate(releases, 1):
                if release.get('url'):
                    print(f"  [{i}/{len(releases)}] {release['repository']} {release['version']} - {release['url']}")
                    notes = self.fetch_release_notes(release['url'])
                    release['notes'] = notes
                    if notes:
                        print(f"  ✓ 取得成功 ({len(notes)} 文字)")
                else:
                    release['notes'] = None

        return releases


def print_releases(releases: List[Dict]):
    """リリース情報を整形して出力"""
    if not releases:
        print("\nリリース通知が見つかりませんでした")
        return

    print("\n" + "="*80)
    print(f"GitHubリリース一覧 (合計: {len(releases)}件)")
    print("="*80 + "\n")

    for i, release in enumerate(releases, 1):
        print(f"{i}. {release['repository']}")
        print(f"   バージョン: {release['version']}")
        print(f"   リリース日時: {release['release_date'].strftime('%Y-%m-%d %H:%M:%S')}")
        if release['url']:
            print(f"   URL: {release['url']}")

        # リリースノートを表示
        if release.get('notes'):
            print(f"\n   リリースノート:")
            # リリースノートを整形して表示（最初の5行または200文字まで）
            notes = release['notes'].strip()
            if notes:
                lines = notes.split('\n')
                preview_lines = lines[:5]
                preview = '\n'.join(preview_lines)
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                elif len(lines) > 5:
                    preview += "\n   ..."

                # インデントを追加
                for line in preview.split('\n'):
                    print(f"     {line}")
        elif release.get('notes') is not None:
            # notesキーが存在するが空の場合
            print(f"   リリースノート: なし")

        print()


def export_to_markdown(releases: List[Dict], output_file: str):
    """
    リリース情報をMarkdown形式で出力

    Args:
        releases: リリース情報のリスト
        output_file: 出力ファイルパス
    """
    from collections import defaultdict

    # 日付ごとにグループ化
    releases_by_date = defaultdict(list)
    for release in releases:
        date_str = release['release_date'].strftime('%Y.%-m.%-d')  # 2025.3.29形式
        releases_by_date[date_str].append(release)

    # Markdown生成
    lines = []

    # 日付順にソート（新しい順）
    sorted_dates = sorted(releases_by_date.keys(), reverse=True)

    for date_str in sorted_dates:
        lines.append(f"- {date_str}")
        lines.append("  - リポジトリの更新リリース情報")

        for release in releases_by_date[date_str]:
            repo = release['repository']
            version = release['version']
            url = release['url']
            release_date = release['release_date'].strftime('%Y.%-m.%-d')

            # リリースタイトル行
            if url:
                lines.append(f"    - [{repo} {version}]({url}) ({release_date})")
            else:
                lines.append(f"    - {repo} {version} ({release_date})")

            # リリースノート
            if release.get('notes'):
                notes = release['notes'].strip()
                if notes:
                    # リリースノートを行ごとに処理
                    note_lines = notes.split('\n')
                    for note_line in note_lines:
                        note_line = note_line.strip()
                        if note_line:
                            # マークダウンのリスト記号を処理
                            if note_line.startswith('#'):
                                # 見出しは無視または変換
                                continue
                            elif note_line.startswith('-') or note_line.startswith('*'):
                                # 既にリスト形式の場合
                                lines.append(f"      {note_line}")
                            else:
                                # 通常のテキストはリスト形式に
                                lines.append(f"      - {note_line}")

    # ファイルに書き込み
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
        f.write('\n')

    print(f"\nMarkdownファイルを出力しました: {output_file}")


def main():
    # 環境変数からSlackトークンを取得
    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    if not slack_token:
        print("エラー: SLACK_BOT_TOKEN環境変数が設定されていません")
        print("使い方: export SLACK_BOT_TOKEN='xoxb-your-token-here'")
        return

    # チャンネル名（必要に応じて変更）
    channel_name = os.environ.get("SLACK_CHANNEL", "notification-development")

    # スキャン期間（日数）
    days = int(os.environ.get("SCAN_DAYS", "7"))

    # デバッグモード
    debug_mode = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")

    # リリースノート取得オプション
    fetch_notes = os.environ.get("FETCH_NOTES", "").lower() in ("true", "1", "yes")

    try:
        scanner = SlackGitHubReleaseScanner(slack_token, channel_name)

        # デバッグモード: メッセージの内容を表示
        if debug_mode:
            print("\n" + "="*80)
            print("デバッグモード: メッセージ内容を表示")
            print("="*80 + "\n")
            messages = scanner.fetch_messages(days)
            for i, msg in enumerate(messages, 1):
                # タイムスタンプを日時に変換
                ts = float(msg.get("ts", 0))
                msg_datetime = datetime.fromtimestamp(ts)

                print(f"--- メッセージ {i} ---")
                print(f"Date: {msg_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Subtype: {msg.get('subtype', 'normal')}")
                print(f"Text: '{msg.get('text', '')}'")

                # Attachments の詳細表示
                if msg.get('attachments'):
                    print(f"\nAttachments: {len(msg.get('attachments'))} 件")
                    for j, att in enumerate(msg.get('attachments', []), 1):
                        print(f"  Attachment {j}:")
                        print(f"    Service Name: {att.get('service_name', '')}")
                        print(f"    Title: {att.get('title', '')}")
                        print(f"    Title Link: {att.get('title_link', '')}")
                        print(f"    Text: {att.get('text', '')}")
                        print(f"    Fallback: {att.get('fallback', '')}")
                        print(f"    Footer: {att.get('footer', '')}")

                # Blocks の詳細表示
                if msg.get('blocks'):
                    print(f"\nBlocks: {len(msg.get('blocks'))} 件")
                    for j, block in enumerate(msg.get('blocks', []), 1):
                        print(f"  Block {j}:")
                        print(f"    Type: {block.get('type', '')}")
                        if block.get('text'):
                            print(f"    Text: {block['text']}")
                        if block.get('elements'):
                            print(f"    Elements: {block['elements']}")

                print("\n" + "-"*80 + "\n")
            return 0

        releases = scanner.scan_releases(days, fetch_notes=fetch_notes)
        print_releases(releases)

        # CSV出力オプション
        if os.environ.get("OUTPUT_CSV"):
            import csv
            output_file = os.environ.get("OUTPUT_CSV")
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                # リリースノートがある場合はフィールドに追加
                fieldnames = ['repository', 'version', 'release_date', 'url']
                if fetch_notes:
                    fieldnames.append('notes')

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for release in releases:
                    row = {
                        'repository': release['repository'],
                        'version': release['version'],
                        'release_date': release['release_date'].strftime('%Y-%m-%d %H:%M:%S'),
                        'url': release['url'] or ''
                    }
                    if fetch_notes:
                        row['notes'] = release.get('notes', '') or ''
                    writer.writerow(row)
            print(f"\nCSVファイルを出力しました: {output_file}")

        # Markdown出力オプション
        if os.environ.get("OUTPUT_MD"):
            output_file = os.environ.get("OUTPUT_MD")
            export_to_markdown(releases, output_file)

    except Exception as e:
        print(f"エラー: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
