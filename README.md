# PDF処理システム

請求書PDFからデータを抽出してCSVファイルを生成するStreamlitアプリケーション。

## 機能

- 複数PDFファイルの一括処理
- OCRによるテキスト抽出
- 課税対象・免税データの自動分類
- CSV形式での出力

## セットアップ

### 1. 必要なパッケージのインストール

```bash
pip install streamlit pytesseract pdf2image pillow
```

### 2. 環境変数の設定

`.env.example`を`.env`にコピーして、実際の値を設定してください：

```bash
cp .env.example .env
```

`.env`ファイルを編集：

```
APP_PASSWORD=your_actual_app_password
PDF_PASSWORD=your_actual_pdf_password
```

### 3. 環境変数の読み込み

#### 方法1: python-dotenvを使用（推奨）

```bash
pip install python-dotenv
```

アプリケーションの先頭に以下を追加：

```python
from dotenv import load_dotenv
load_dotenv()
```

#### 方法2: 直接設定

```bash
# Linux/Mac
export APP_PASSWORD=your_actual_app_password
export PDF_PASSWORD=your_actual_pdf_password

# Windows
set APP_PASSWORD=your_actual_app_password
set PDF_PASSWORD=your_actual_pdf_password
```

### 4. アプリケーションの起動

```bash
streamlit run app.py
```

## デプロイ時の環境変数設定

### Streamlit Cloud

1. リポジトリの設定で「Secrets」を選択
2. 以下の形式で追加：

```toml
APP_PASSWORD = "your_actual_app_password"
PDF_PASSWORD = "your_actual_pdf_password"
```

### Heroku

```bash
heroku config:set APP_PASSWORD=your_actual_app_password
heroku config:set PDF_PASSWORD=your_actual_pdf_password
```

### Docker

```bash
docker run -e APP_PASSWORD=your_actual_app_password -e PDF_PASSWORD=your_actual_pdf_password your-app
```

## セキュリティ注意事項

- `.env`ファイルは絶対にGitにコミットしないでください
- パスワードは定期的に変更してください
- 本番環境では強力なパスワードを使用してください
- 環境変数が設定されていない場合、アプリケーションは適切にエラーメッセージを表示します

## トラブルシューティング

### パスワードエラー

- 環境変数が正しく設定されているか確認
- `.env`ファイルのパスと内容を確認
- アプリケーションを再起動

### OCRエラー

- Tesseractがインストールされているか確認
- 日本語言語パックがインストールされているか確認

## ライセンス

このプロジェクトは社内利用のためのものです。
