import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
import google.generativeai as genai
from flask import Flask, request, abort
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, 
    PushMessageRequest, BroadcastRequest, TextMessage
)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境変数から設定を読み込み
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
GOOGLE_SHEETS_API_KEY = os.environ.get('GOOGLE_SHEETS_API_KEY')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')

# LINE Bot設定（配信専用）
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

# Gemini API設定
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

# 仏教テーマのAI設定
AI_PROMPT = """
あなたは仏教の教えを優しく伝える智慧のあるガイドです。
日本の方々に仏教の智慧を分かりやすく、心に響くように伝えてください。

話し方：
- 温かく、穏やかな語調
- 難しい言葉は避け、日常に寄り添う表現
- 押し付けがましくなく、自然に心に届く内容
- 短すぎず長すぎない、ちょうど良い長さ

内容：
- 仏教の基本的な教え（四諦、八正道、因果など）
- 日常生活に活かせる智慧
- 心の平安や苦しみの解決につながる話
- 季節や時期に応じた内容

注意：
- 特定の宗派に偏らない一般的な仏教の教え
- 押し付けがましい説教ではなく、気づきを促す内容
- 読む人の心が軽くなる、希望を感じられる内容
"""

# Google Sheets からメッセージを取得する関数
def get_message_from_sheets():
    """スプレッドシートから今週のメッセージを取得"""
    try:
        if not GOOGLE_SHEETS_API_KEY or not SPREADSHEET_ID:
            logger.error("Google Sheets configuration missing")
            return None
            
        # スプレッドシートのデータを取得
        range_name = 'A:B'  # A列（日付）とB列（メッセージ）
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{range_name}?key={GOOGLE_SHEETS_API_KEY}'
        
        response = requests.get(url)
        if response.status_code != 200:
            logger.error(f"Sheets API error: {response.status_code}")
            return None
            
        data = response.json()
        values = data.get('values', [])
        
        if not values:
            logger.info("No data found in spreadsheet")
            return None
            
        # 日本時間を取得
        jst = timezone(timedelta(hours=9))
        today = datetime.now(jst)
        today_str = today.strftime("%Y年%m月%d日")
        month_day = today.strftime("%m月%d日")
        weekday = today.strftime("%a")  # Mon, Tue, Wed...
        
        # 今日に適したメッセージを探す
        for row in values[1:]:  # ヘッダーをスキップ
            if len(row) >= 2:
                date_cell = row[0] if len(row) > 0 else ""
                message_cell = row[1] if len(row) > 1 else ""
                
                # 日付、曜日、キーワードでマッチング
                if (today_str in date_cell or 
                    month_day in date_cell or 
                    weekday in date_cell or
                    "毎週" in date_cell):
                    if message_cell.strip():
                        logger.info(f"Found message from spreadsheet: {date_cell}")
                        return message_cell
        
        logger.info("No matching message found in spreadsheet")
        return None
        
    except Exception as e:
        logger.error(f"Error accessing spreadsheet: {e}")
        return None

@app.route("/", methods=['GET'])
def health_check():
    """ヘルスチェック用エンドポイント"""
    return "Buddhist Wisdom Bot is running! [SIMPLIFIED VERSION]", 200

@app.route("/test-simple-wisdom", methods=['GET'])
def test_simple_wisdom():
    """簡易版メッセージ生成テスト"""
    try:
        jst = timezone(timedelta(hours=9))
        today = datetime.now(jst)
        today_str = today.strftime("%Y年%m月%d日")
        
        simple_prompt = f"""
{today_str}の心を軽くする3行のメッセージを作成してください。

要件：
- 簡潔で実用的
- 宗教的表現なし
- 自然な日本語

形式：
おはようございます。
[実用的なアドバイス1行]
今日も心穏やかに過ごしましょう。
        """
        
        if GEMINI_API_KEY:
            wisdom_response = model.generate_content(simple_prompt)
            return f"[AI生成テスト]\n{wisdom_response.text}", 200
        else:
            return "おはようございます。\n深呼吸をして、今この瞬間を大切にしましょう。\n今日も心穏やかに過ごしましょう。", 200
            
    except Exception as e:
        return f"エラー: {str(e)}", 500

@app.route("/broadcast", methods=['POST'])
def broadcast():
    """定期配信用エンドポイント"""
    try:
        # リクエストボディから設定を取得
        data = request.get_json() or {}
        
        # カスタムメッセージがない場合はスプレッドシートまたは仏教の教え
        if not data.get('message'):
            # まずスプレッドシートからメッセージを取得
            sheet_message = get_message_from_sheets()
            
            if sheet_message:
                message_text = sheet_message
                logger.info("Using message from spreadsheet")
            else:
                # 日付から教えを選択（重複回避）
                jst = timezone(timedelta(hours=9))
                today = datetime.now(jst)
                
                # 仏教の教えリスト（15個でローテーション）
                teachings = [
                    # 1. 中道
                    """おはようございます。

仏教の「中道」という教えがあります。極端に偏らない生き方です。
頑張りすぎず、怠けすぎず、ちょうど良いバランスを心がけましょう。

今日も心穏やかに過ごしましょう。""",
                    
                    # 2. 一期一会
                    """おはようございます。

「一期一会」- 今日の出会いは一生に一度きりかもしれません。
目の前の人との時間を大切に、心を込めて接しましょう。

今日も心穏やかに過ごしましょう。""",
                    
                    # 3. 無常
                    """おはようございます。

仏教では「諸行無常」といい、すべては変化していきます。
辛いことも永遠には続きません。今を受け入れて前を向きましょう。

今日も心穏やかに過ごしましょう。""",
                    
                    # 4. 因果
                    """おはようございます。

「因果応報」- 良い行いは良い結果を生みます。
小さな親切が、巡り巡って自分に返ってきます。

今日も心穏やかに過ごしましょう。""",
                    
                    # 5. 慈悲
                    """おはようございます。

仏教の「慈悲」とは、思いやりの心です。
まず自分に優しく、そして周りの人にも優しくしましょう。

今日も心穏やかに過ごしましょう。""",
                    
                    # 6. 知足
                    """おはようございます。

「知足」- 今あるものに満足し感謝する心です。
足りないものより、今あるものに目を向けてみましょう。

今日も心穏やかに過ごしましょう。""",
                    
                    # 7. 今ここ
                    """おはようございます。

仏教では「今ここ」を大切にします。
過去や未来ではなく、今この瞬間を生きることが幸せへの道です。

今日も心穏やかに過ごしましょう。""",
                    
                    # 8. 無我
                    """おはようございます。

「無我」- 執着を手放すと心が軽くなります。
こだわりすぎず、流れに身を任せることも大切です。

今日も心穏やかに過ごしましょう。""",
                    
                    # 9. 忍辱
                    """おはようございます。

「忍辱」- 困難に耐える心の強さです。
今の苦労は、必ず成長の糧になります。

今日も心穏やかに過ごしましょう。""",
                    
                    # 10. 布施
                    """おはようございます。

「布施」とは、見返りを求めない与える心です。
笑顔や優しい言葉も、立派な布施になります。

今日も心穏やかに過ごしましょう。""",
                    
                    # 11. 正見
                    """おはようございます。

「正見」- 物事を正しく見る目を持ちましょう。
先入観を捨てて、ありのままを受け入れることが大切です。

今日も心穏やかに過ごしましょう。""",
                    
                    # 12. 苦諦
                    """おはようございます。

仏教では「苦」の原因は執着だと教えます。
手放すことで、心は自由になり軽くなります。

今日も心穏やかに過ごしましょう。""",
                    
                    # 13. 縁起
                    """おはようございます。

「縁起」- すべては繋がり合って存在しています。
あなたの笑顔が、誰かの幸せに繋がっているかもしれません。

今日も心穏やかに過ごしましょう。""",
                    
                    # 14. 空
                    """おはようございます。

「色即是空」- 固定的なものは何もありません。
柔軟な心で、変化を受け入れていきましょう。

今日も心穏やかに過ごしましょう。""",
                    
                    # 15. 精進
                    """おはようございます。

「精進」- 一歩ずつでも前に進むことが大切です。
小さな努力の積み重ねが、大きな成果につながります。

今日も心穏やかに過ごしましょう。"""
                ]
                
                # 年間通算日数を使って教えを選択
                day_of_year = today.timetuple().tm_yday
                teaching_index = (day_of_year - 1) % len(teachings)
                
                message_text = teachings[teaching_index].strip()
                logger.info(f"Using Buddhist teaching #{teaching_index + 1} for day {day_of_year}")
        else:
            message_text = data.get('message')
        
        # 全ユーザーに配信
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.broadcast(
                BroadcastRequest(
                    messages=[TextMessage(text=message_text)]
                )
            )
        
        logger.info(f"Buddhist wisdom broadcast sent: {message_text}")
        return {
            "status": "success", 
            "message": "Buddhist wisdom broadcast sent",
            "content": message_text
        }, 200
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return {"status": "error", "message": str(e)}, 500

@app.route("/test-wisdom", methods=['GET'])
def test_wisdom():
    """仏教メッセージ生成テスト用エンドポイント"""
    # デバッグ: 環境変数確認
    debug_info = f"GEMINI_API_KEY exists: {bool(GEMINI_API_KEY)}\n"
    debug_info += f"GEMINI_API_KEY length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0}\n"
    debug_info += f"GEMINI_API_KEY starts with: {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'None'}...\n\n"
    
    # まずスプレッドシートからメッセージを取得
    sheet_message = get_message_from_sheets()
    
    if sheet_message:
        return f"[DEBUG]\n{debug_info}[スプレッドシートから取得]\n{sheet_message}", 200
    
    # スプレッドシートにない場合はAI生成をテスト
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst)
    today_str = today.strftime("%Y年%m月%d日")
    
    wisdom_prompt = f"""
今日は{today_str}です。仏教の智慧を込めた心温まるメッセージを作成してください。

内容の指針：
- その日に適した仏教の教えや智慧
- 日常生活に活かせる気づき
- 心の平安につながる内容
- 季節感や時期に応じた内容

以下の形式で書いてください：
🕯️ 合掌

[仏教の教えに基づく智慧のメッセージ]

心静かに、今日という一日を大切に過ごしましょう。

南無阿弥陀仏 🙏
    """
    
    try:
        if GEMINI_API_KEY:
            wisdom_response = model.generate_content(wisdom_prompt)
            return f"[AI生成]\n{wisdom_response.text}", 200
        else:
            return """[デフォルトメッセージ]
🕯️ 合掌

今日という日は、二度と戻らない尊い一日です。
心静かに、感謝の気持ちで過ごしましょう。

南無阿弥陀仏 🙏
            """, 200
            
    except Exception as e:
        logger.error(f"Test wisdom error: {e}")
        return f"エラー: {str(e)}", 500

@app.route("/debug-env", methods=['GET'])
def debug_env():
    """環境変数デバッグ用エンドポイント"""
    debug_info = f"""環境変数デバッグ情報:
GEMINI_API_KEY exists: {bool(GEMINI_API_KEY)}
GEMINI_API_KEY length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0}
GEMINI_API_KEY value: {GEMINI_API_KEY if GEMINI_API_KEY else 'None'}

LINE_CHANNEL_ACCESS_TOKEN exists: {bool(LINE_CHANNEL_ACCESS_TOKEN)}
LINE_CHANNEL_ACCESS_TOKEN length: {len(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else 0}

GOOGLE_SHEETS_API_KEY exists: {bool(GOOGLE_SHEETS_API_KEY)}
GOOGLE_SHEETS_API_KEY length: {len(GOOGLE_SHEETS_API_KEY) if GOOGLE_SHEETS_API_KEY else 0}

SPREADSHEET_ID exists: {bool(SPREADSHEET_ID)}
SPREADSHEET_ID: {SPREADSHEET_ID if SPREADSHEET_ID else 'None'}
"""
    return debug_info, 200

@app.route("/test-sheets", methods=['GET'])
def test_sheets():
    """スプレッドシートのデータをテスト用に表示"""
    try:
        if not GOOGLE_SHEETS_API_KEY or not SPREADSHEET_ID:
            return "Google Sheets設定が不足しています", 500
            
        range_name = 'A:B'
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{range_name}?key={GOOGLE_SHEETS_API_KEY}'
        
        response = requests.get(url)
        if response.status_code != 200:
            return f"API Error: {response.status_code}\n{response.text}", 500
            
        data = response.json()
        values = data.get('values', [])
        
        if not values:
            return "スプレッドシートにデータがありません", 200
            
        result = "スプレッドシートの内容:\n"
        for i, row in enumerate(values):
            result += f"行{i+1}: {row}\n"
        
        return result, 200
        
    except Exception as e:
        return f"エラー: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))