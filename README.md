# Slack GitHub Release Scanner

SlackチャンネルからGitHubのリリース通知を抽出するスクリプトです。

## 機能

- Slackチャンネルから過去1週間（設定可能）のメッセージを取得
- Attachment の Fallback に "New release" を含むGitHubリリース通知を抽出
- リポジトリ名、バージョン、リリース日時、URLを一覧表示
- GitHubリリースノートの自動取得（オプション）
- CSV/Markdown出力オプション付き

## 前提条件

- Python 3.9以上
- [uv](https://github.com/astral-sh/uv) - 高速なPythonパッケージマネージャー

### uvのインストール

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# pipx経由
pipx install uv
```

## セットアップ

### 1. プロジェクトのセットアップ

```bash
# 依存パッケージのインストール（uv.lockが自動生成されます）
uv sync
```

### 2. Slack Bot Tokenの取得

1. [Slack API](https://api.slack.com/apps)にアクセス
2. "Create New App" → "From scratch" を選択
3. アプリ名（例: GitHub Release Scanner）とワークスペースを選択して "Create App"
4. 左メニューの "OAuth & Permissions" をクリック
5. "Scopes" セクションの "Bot Token Scopes" で以下の権限を追加:

   **必須の権限:**
   - `channels:history` - パブリックチャンネルのメッセージ履歴を読む
   - `channels:read` - パブリックチャンネルの情報を読む
   - `groups:history` - プライベートチャンネルのメッセージ履歴を読む
   - `groups:read` - プライベートチャンネルの情報を読む

   注: `notification-development` がプライベートチャンネルの場合は `groups:*` の権限が必要です

6. ページ上部の "Install to Workspace" ボタンをクリック
7. 権限の確認画面で "許可する" をクリック
8. "Bot User OAuth Token" (`xoxb-`で始まるトークン) が表示されるのでコピー
9. Slackの `notification-development` チャンネルで以下を実行してボットを招待:
   ```
   /invite @your-bot-name
   ```
   （ボット名はステップ3で設定したアプリ名）

### 3. 環境変数の設定

```bash
export SLACK_BOT_TOKEN='xoxb-your-token-here'
```

## 使い方

### 基本的な使い方

```bash
# uvで実行
uv run python slack_github_releases.py

# または、インストール済みのコマンドとして実行
uv run slack-scan
```

デフォルトでは:
- チャンネル: `notification-development`
- 期間: 過去7日間

### オプション設定

環境変数でカスタマイズできます:

```bash
# チャンネル名を変更
export SLACK_CHANNEL='your-channel-name'

# スキャン期間を変更（日数）
export SCAN_DAYS=14

# リリースノートを取得（GitHub APIを使用）
export FETCH_NOTES=true

# GitHub Personal Access Token（レート制限回避のため推奨）
export GITHUB_TOKEN='ghp_your-token-here'

# CSV出力
export OUTPUT_CSV='releases.csv'

# Markdown出力(日付別グループ化、リリースノート付き)
export OUTPUT_MD='releases.md'

# 実行
uv run python slack_github_releases.py
```

### ワンライナーでの実行

```bash
# 環境変数を指定して実行
SLACK_BOT_TOKEN='xoxb-your-token' uv run python slack_github_releases.py

# リリースノート付きでCSVに出力
SLACK_BOT_TOKEN='xoxb-your-token' FETCH_NOTES=true OUTPUT_CSV='releases.csv' uv run slack-scan

# Markdown形式でリリースノート付き出力
SLACK_BOT_TOKEN='xoxb-your-token' FETCH_NOTES=true OUTPUT_MD='releases.md' uv run slack-scan

# 半年分のデータをリリースノート付きで取得
SCAN_DAYS=180 FETCH_NOTES=true uv run python slack_github_releases.py
```

### 出力例

```
チャンネル 'notification-development' から過去7日分のメッセージを取得中...
245件のメッセージを取得しました
GitHubリリース通知を解析中...
12件のリリース通知を見つけました

================================================================================
GitHubリリース一覧 (合計: 12件)
================================================================================

1. facebook/react
   バージョン: v18.2.0
   リリース日時: 2025-10-28 14:23:15
   URL: https://github.com/facebook/react/releases/tag/v18.2.0

2. nodejs/node
   バージョン: v20.10.0
   リリース日時: 2025-10-27 09:15:42
   URL: https://github.com/nodejs/node/releases/tag/v20.10.0

...
```

### Markdown出力例

`OUTPUT_MD`オプションを使用すると、日付別にグループ化されたMarkdown形式でリリース情報を出力できます:

```markdown
- 2025.3.29
  - リポジトリの更新リリース情報
    - [hakoniwa-drone-core v3.0.0](https://github.com/toppers/hakoniwa-drone-core/releases/tag/v3.0.0) (2025.3.26)
      - 大阪万博向けのイベントで利用する箱庭ドローンシミュレータの公開
      - 箱庭機能あり/無しの両方で利用できるように利用手順書とサンプルを公開
    - [hakoniwa-ros2pdu 2.2.1](https://github.com/toppers/hakoniwa-ros2pdu/releases/tag/2.2.1) (2025.3.26)
      - What's Changed
      - Add Codespace Dev Container by @tmori in #91
```

**注意**: Markdown出力にはリリースノートが必要なため、`FETCH_NOTES=true`との併用が推奨されます。

## トラブルシューティング

### エラー: "missing_scope"

```
エラー: チャンネルID取得エラー: missing_scope
```

**原因**: Slack Botに必要な権限（scope）が不足しています。

**解決方法**:
1. [Slack API Apps](https://api.slack.com/apps)にアクセス
2. 作成したアプリを選択
3. 左メニューの "OAuth & Permissions" をクリック
4. "Bot Token Scopes" セクションで以下の権限が**すべて**追加されているか確認:
   - `channels:history`
   - `channels:read`
   - `groups:history`
   - `groups:read`
5. 権限を追加した場合、ページ上部の "Reinstall to Workspace" をクリック
6. 新しいトークンをコピーして環境変数を更新

### エラー: "チャンネルが見つかりません"

**原因**: チャンネル名が間違っているか、ボットがチャンネル一覧を取得できません。

**解決方法**:
- チャンネル名が正しいか確認（`#`は不要、`notification-development`のように指定）
- プライベートチャンネルの場合、`groups:read`権限が必要
- ボットがワークスペースにインストールされているか確認

### エラー: "not_in_channel"

**原因**: ボットがチャンネルに参加していません。

**解決方法**:

Slackの該当チャンネルで以下を実行してボットを招待:

```
/invite @your-bot-name
```

または、チャンネル詳細の「インテグレーション」タブから「アプリを追加」でボットを追加

### リリース通知が抽出されない

- メッセージに "New release published" が含まれているか確認
- GitHubアプリの通知形式が変わっている可能性があります
- `raw_text`フィールドを確認して、パターンマッチングを調整してください

## ライセンス

MIT
