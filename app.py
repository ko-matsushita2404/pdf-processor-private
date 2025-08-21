import streamlit as st
import os
import tempfile
import zipfile
import io
import traceback
import gc
from datetime import datetime
import re
import csv
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import logging

# ログ設定（セキュリティ向上のため最小限のログ出力）
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# パスワード設定（Streamlit Secretsまたは環境変数から取得）
try:
    # Streamlit Secretsから取得を試行
    PDF_PASSWORD = st.secrets.get("PDF_PASSWORD", "")
    APP_PASSWORD = st.secrets.get("APP_PASSWORD", "")
except:
    # 環境変数から取得
    PDF_PASSWORD = os.environ.get("PDF_PASSWORD", "")
    APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# 認証機能
def check_password():
    def password_entered():
        if st.session_state["password"] == APP_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    # パスワードが設定されていない場合の処理
    if not APP_PASSWORD:
        st.error("アプリケーションパスワードが設定されていません。管理者に連絡してください。")
        st.stop()

    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", 
                     on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", 
                     on_change=password_entered, key="password")
        st.error("パスワードが正しくありません")
        return False
    else:
        return True

# CSVヘッダー定義
CSV_HEADERS = [
    '製番', '図番', '部番', '符号', '品名', 'ﾒｰｶ名', '材質名', '形式寸法', '重量（kg）', '員数', '単位',
    '発注数量', '単位', '手配ｺｰﾄﾞ', '納期', '仕入先ｺｰﾄﾞ', '発注単価', '金額', '納入場所', '備考', 
    'TECHS単価区分', 'TECHS完了CK', 'TECHS発注情報取込CK'
]

# 画像最適化関数
def optimize_image_for_ocr(image):
    """OCR用に画像を最適化"""
    # 画像サイズを制限（メモリ使用量削減）
    if image.size[0] > 2000:
        ratio = 2000 / image.size[0]
        new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
        image = image.resize(new_size, Image.LANCZOS)
    return image

# OCR処理関数
@st.cache_data(ttl=3600)  # 1時間キャッシュ
def perform_ocr_web(pdf_bytes, file_hash):
    """PDF bytesからOCRでテキストを抽出（キャッシュ対応）"""
    try:
        # PDFパスワード処理
        if PDF_PASSWORD:
            images = convert_from_bytes(pdf_bytes, userpw=PDF_PASSWORD)
        else:
            st.warning("PDFパスワードが設定されていません。パスワード保護されたPDFの処理ができない可能性があります。")
            images = convert_from_bytes(pdf_bytes)
        
        full_text = ""
        for i, image in enumerate(images):
            # 画像を最適化
            optimized_image = optimize_image_for_ocr(image)
            
            # 日本語OCR実行
            text = pytesseract.image_to_string(optimized_image, lang='jpn')
            full_text += f"--- Page {i+1} ---\n"
            full_text += text
            full_text += "\n"
            
            # メモリクリア
            del optimized_image
            
        return full_text
        
    except Exception as e:
        logger.error(f"OCR processing error: {str(e)}")
        st.error(f"OCR処理でエラーが発生しました: {str(e)}")
        return None
    finally:
        # メモリクリア
        gc.collect()

# 請求書データ抽出関数
def extract_hyoki_kaiun_data(ocr_text):
    """請求書からデータを抽出"""
    extracted_rows_asterisk = []
    extracted_rows_no_asterisk = []
    main_seiban = ''
    invoice_no = ''
    delivery_date = ''

    # 製番抽出
    match_seiban_header = re.search(r'製番:\s*(\S+)', ocr_text)
    if match_seiban_header:
        main_seiban = match_seiban_header.group(1)

    # 請求書番号抽出
    match_invoice_no = re.search(r'請求N[O\)]\s*:\s*:\s*([A-Z0-9-]+)', ocr_text)
    if match_invoice_no:
        invoice_no = match_invoice_no.group(1)

    # 納期抽出
    match_delivery_date = re.search(r'請求日\s*:\s*(\d{4}/\d{2}/\d{2})', ocr_text)
    if match_delivery_date:
        delivery_date = match_delivery_date.group(1)

    remarks_text = f"貴社請求書NO.{invoice_no}に依ります。" if invoice_no else ''

    lines = ocr_text.splitlines()

    # 「* 印は課税対象取引です」の行のインデックスを見つける
    effective_end_index = len(lines)
    for idx, line in enumerate(lines):
        if "* 印は課税対象取引です" in line:
            effective_end_index = idx
            break

    # 行項目の正規表現パターン
    line_item_regex = re.compile(
        r'^\*?\s*(.+?)\s+(\d+(?:[.,]\d+)?)\s+(\S+)\s+JPY([\d,\s.]+)\s*(JPY[\d,\s.]*)?$'
    )

    # 形式寸法のパターン
    dimension_patterns = [
        re.compile(r'^\d+FT(?: OPEN TOP)?$'),
        re.compile(r'^\d+/\d+\s*\((?:トレーラー|コンテナ|混載便)\)$'),
        re.compile(r'^\S+\s*\(\s*\d+TON\s*\)$'),
        re.compile(r'^\d+品目=\d+申告$'),
        re.compile(r'^\d+TON$'),
    ]

    i = 0
    while i < effective_end_index:
        line = lines[i]

        match = line_item_regex.search(line)
        if match:
            hinmei = match.group(1).strip()
            inzu = match.group(2)
            tani = match.group(3)
            hacchu_tanka = match.group(4).replace(',', '').replace(' ', '')
            kingaku_str = match.group(5) if match.group(5) else ''
            kingaku = kingaku_str.replace('JPY', '').replace(',', '').replace(' ', '').strip()
            keishiki_sunpou = ''

            # 1. まず固定ルールで補正
            replacement_rules = {
                'ネコッテナ運搬料': 'ｺﾝﾃﾅｰ運搬料',
                'トう97賃': 'ﾄﾗｯｸ賃',
                'トう9賃': 'ﾄﾗｯｸ賃',
                'ルーッ代': 'ｸﾚｰﾝ代',
                'a社費用(立替)': '船社費用(立替)',
            }
            hinmei = replacement_rules.get(hinmei, hinmei)

            # 2. 次に fuzzywuzzy 補正でより近い候補があれば置換
            from fuzzywuzzy import process

            correct_items = ['ｺﾝﾃﾅｰ運搬料', 'ﾄﾗｯｸ賃', 'ｸﾚｰﾝ代', '船社費用(立替)']
            match, score = process.extractOne(hinmei, correct_items)
            if score > 70:  # 類似度70%以上なら補正
                hinmei = match

            # 次の行が形式寸法かチェック
            if i + 1 < len(lines):
                next_line = lines[i+1].strip()
                for pattern in dimension_patterns:
                    if pattern.search(next_line):
                        keishiki_sunpou = next_line
                        i += 1
                        break

            row_data = {
                '製番': main_seiban,
                '品名': hinmei,
                '員数': inzu,
                '単位': tani,
                '発注数量': inzu,
                '発注単価': hacchu_tanka,
                '金額': kingaku,
                '形式寸法': keishiki_sunpou,
                '備考': remarks_text,
                '手配ｺｰﾄﾞ': '3411',
                '納期': delivery_date,
                '仕入先ｺｰﾄﾞ': '80129',
                '納入場所': '本社工場',
                'TECHS単価区分': 'S0',
                'TECHS完了CK': 'S1',
                'TECHS発注情報取込CK': 'S1',
            }

            if line.strip().startswith('*'):
                extracted_rows_asterisk.append(row_data)
            else:
                row_data['品名'] = f"{row_data['品名']}（免税）"
                extracted_rows_no_asterisk.append(row_data)

        i += 1

    return extracted_rows_asterisk, extracted_rows_no_asterisk

# CSV生成関数（UTF-8エンコーディング対応）
def generate_csv_data(extracted_rows):
    """抽出したデータをCSV形式で生成（UTF-8エンコーディング）"""
    if not extracted_rows:
        return None
    
    output = io.StringIO()
    final_data = []
    
    for row_raw in extracted_rows:
        new_row = {header: '' for header in CSV_HEADERS}
        new_row.update(row_raw)
        final_data.append(new_row)
    
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    writer.writerows(final_data)
    
    # UTF-8エンコーディングでバイト形式に変換
    csv_content = output.getvalue()
    return csv_content.encode('utf-8-sig')  # BOM付きUTF-8

# メイン処理関数
def process_pdf_file(pdf_file):
    """単一PDFファイルの処理"""
    try:
        # ファイルハッシュ生成（セキュリティ向上のため）
        pdf_bytes = pdf_file.read()
        file_hash = str(hash(pdf_bytes))
        
        # OCR処理
        ocr_text = perform_ocr_web(pdf_bytes, file_hash)
        
        if not ocr_text:
            return None, None, None
        
        # データ抽出
        extracted_rows_asterisk, extracted_rows_no_asterisk = extract_hyoki_kaiun_data(ocr_text)
        
        # CSV生成（UTF-8エンコーディング）
        csv_asterisk = generate_csv_data(extracted_rows_asterisk) if extracted_rows_asterisk else None
        csv_no_asterisk = generate_csv_data(extracted_rows_no_asterisk) if extracted_rows_no_asterisk else None
        
        return ocr_text, csv_asterisk, csv_no_asterisk
        
    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        st.error(f"処理エラー: {str(e)}")
        return None, None, None
    finally:
        # メモリクリア
        gc.collect()

# メインアプリケーション
def main():
    st.set_page_config(
        page_title="PDF処理システム",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    if not check_password():
        return
    
    st.title("📄 PDF処理システム")
    st.markdown("請求書PDFからデータを抽出してCSVファイルを生成します。")
    
    # 使用制限の説明
    st.info("💡 一度に処理できるファイルは最大5個、各ファイルサイズは10MB以下でお願いします。")
    
    # ファイルアップロード
    uploaded_files = st.file_uploader(
        "PDFファイルを選択してください（複数選択可能）",
        type=['pdf'],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        # ファイル数制限
        if len(uploaded_files) > 5:
            st.error("一度に処理できるファイルは5個までです。")
            return
        
        # ファイルサイズ制限（10MB）
        for file in uploaded_files:
            if file.size > 10 * 1024 * 1024:  # 10MB
                st.error(f"ファイルサイズが大きすぎます（10MB以下にしてください）")
                return
        
        st.success(f"{len(uploaded_files)}個のファイルが選択されました。")
        
        if st.button("処理開始", type="primary"):
            with st.spinner("処理中..."):
                progress_bar = st.progress(0)
                results = []
                
                for i, uploaded_file in enumerate(uploaded_files):
                    st.write(f"処理中: ファイル {i+1}/{len(uploaded_files)}")
                    
                    # PDFファイル処理
                    ocr_text, csv_asterisk, csv_no_asterisk = process_pdf_file(uploaded_file)
                    
                    if ocr_text:
                        results.append({
                            'index': i + 1,
                            'ocr_text': ocr_text,
                            'csv_asterisk': csv_asterisk,
                            'csv_no_asterisk': csv_no_asterisk
                        })
                        st.success(f"✅ ファイル {i+1} 処理完了")
                    else:
                        st.error(f"❌ ファイル {i+1} 処理失敗")
                    
                    progress_bar.progress((i + 1) / len(uploaded_files))
                
                # 結果表示
                st.markdown("## 処理結果")
                
                if results:
                    # ZIP形式でダウンロード
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for result in results:
                            file_index = result['index']
                            
                            # OCRテキスト
                            zip_file.writestr(f"file_{file_index:02d}_ocr_text.txt", result['ocr_text'])
                            
                            # CSV（課税対象）
                            if result['csv_asterisk']:
                                zip_file.writestr(f"file_{file_index:02d}_asterisk.csv", result['csv_asterisk'])
                            
                            # CSV（免税）
                            if result['csv_no_asterisk']:
                                zip_file.writestr(f"file_{file_index:02d}_no_asterisk.csv", result['csv_no_asterisk'])
                    
                    zip_buffer.seek(0)
                    
                    st.download_button(
                        label="📥 結果をダウンロード（ZIP形式）",
                        data=zip_buffer.getvalue(),
                        file_name=f"pdf_processing_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip"
                    )
                    
                    # 個別ファイル表示
                    for result in results:
                        with st.expander(f"📄 ファイル {result['index']} の詳細"):
                            
                            # OCRテキスト表示
                            st.subheader("OCRテキスト")
                            st.text_area(
                                "抽出されたテキスト",
                                result['ocr_text'],
                                height=200,
                                key=f"ocr_file_{result['index']}"
                            )
                            
                            # CSV表示
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                if result['csv_asterisk']:
                                    st.subheader("課税対象データ")
                                    st.download_button(
                                        label="CSVダウンロード",
                                        data=result['csv_asterisk'],
                                        file_name=f"file_{result['index']:02d}_asterisk.csv",
                                        mime="text/csv"
                                    )
                            
                            with col2:
                                if result['csv_no_asterisk']:
                                    st.subheader("免税データ")
                                    st.download_button(
                                        label="CSVダウンロード",
                                        data=result['csv_no_asterisk'],
                                        file_name=f"file_{result['index']:02d}_no_asterisk.csv",
                                        mime="text/csv"
                                    )
                else:
                    st.warning("処理に成功したファイルがありません。")
    
    # フッター
    st.markdown("---")
    st.markdown("*システムに関するお問い合わせは管理者までご連絡ください。*")

if __name__ == "__main__":
    main()
