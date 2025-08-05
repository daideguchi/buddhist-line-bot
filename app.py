import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
import google.generativeai as genai
from flask import Flask, request, abort, render_template
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
                
                # 仏教の教えとブログURLのマッピング
                teaching_keys = [
                    'chudo', 'ichigo_ichie', 'mujo', 'inga', 'jihi',
                    'chisoku', 'imakoko', 'muga', 'niniku', 'fuse',
                    'shoken', 'kutai', 'engi', 'ku', 'shojin'
                ]
                
                # 仏教の教えリスト（15個でローテーション）
                teachings_with_url = [
                    # 1. 中道
                    """おはようございます。

仏教の「中道」という教えがあります。極端に偏らない生き方です。
頑張りすぎず、怠けすぎず、ちょうど良いバランスを心がけましょう。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/chudo""",
                    
                    # 2. 一期一会
                    """おはようございます。

「一期一会」- 今日の出会いは一生に一度きりかもしれません。
目の前の人との時間を大切に、心を込めて接しましょう。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/ichigo_ichie""",
                    
                    # 3. 無常
                    """おはようございます。

仏教では「諸行無常」といい、すべては変化していきます。
辛いことも永遠には続きません。今を受け入れて前を向きましょう。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/mujo""",
                    
                    # 4. 因果
                    """おはようございます。

「因果応報」- 良い行いは良い結果を生みます。
小さな親切が、巡り巡って自分に返ってきます。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/inga""",
                    
                    # 5. 慈悲
                    """おはようございます。

仏教の「慈悲」とは、思いやりの心です。
まず自分に優しく、そして周りの人にも優しくしましょう。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/jihi""",
                    
                    # 6. 知足
                    """おはようございます。

「知足」- 今あるものに満足し感謝する心です。
足りないものより、今あるものに目を向けてみましょう。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/chisoku""",
                    
                    # 7. 今ここ
                    """おはようございます。

仏教では「今ここ」を大切にします。
過去や未来ではなく、今この瞬間を生きることが幸せへの道です。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/imakoko""",
                    
                    # 8. 無我
                    """おはようございます。

「無我」- 執着を手放すと心が軽くなります。
こだわりすぎず、流れに身を任せることも大切です。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/muga""",
                    
                    # 9. 忍辱
                    """おはようございます。

「忍辱」- 困難に耐える心の強さです。
今の苦労は、必ず成長の糧になります。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/niniku""",
                    
                    # 10. 布施
                    """おはようございます。

「布施」とは、見返りを求めない与える心です。
笑顔や優しい言葉も、立派な布施になります。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/fuse""",
                    
                    # 11. 正見
                    """おはようございます。

「正見」- 物事を正しく見る目を持ちましょう。
先入観を捨てて、ありのままを受け入れることが大切です。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/shoken""",
                    
                    # 12. 苦諦
                    """おはようございます。

仏教では「苦」の原因は執着だと教えます。
手放すことで、心は自由になり軽くなります。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/kutai""",
                    
                    # 13. 縁起
                    """おはようございます。

「縁起」- すべては繋がり合って存在しています。
あなたの笑顔が、誰かの幸せに繋がっているかもしれません。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/engi""",
                    
                    # 14. 空
                    """おはようございます。

「色即是空」- 固定的なものは何もありません。
柔軟な心で、変化を受け入れていきましょう。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/ku""",
                    
                    # 15. 精進
                    """おはようございます。

「精進」- 一歩ずつでも前に進むことが大切です。
小さな努力の積み重ねが、大きな成果につながります。

今日も心穏やかに過ごしましょう。

📖 詳しく読む：https://buddhist-line-bot-production.up.railway.app/blog/shojin"""
                ]
                
                # 年間通算日数を使って教えを選択
                day_of_year = today.timetuple().tm_yday
                teaching_index = (day_of_year - 1) % len(teachings_with_url)
                
                message_text = teachings_with_url[teaching_index].strip()
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

# 仏教の教えの詳細データ
DETAILED_TEACHINGS = {
    'chudo': {
        'name': '中道',
        'pronunciation': 'ちゅうどう',
        'meaning': '中道とは、極端に偏らない生き方を説く仏教の根本的な教えです。お釈迦様が修行時代に体験した、厳しすぎる苦行でも快楽にふけることでもない、バランスのとれた道を意味します。現代の私たちにとっても、頑張りすぎて燃え尽きることなく、かといって怠けすぎることもない、適度な生き方の指針となります。',
        'quote': '苦しすぎず、楽すぎず、ちょうど良い道を歩もう',
        'application': 'ストレス社会で生きる現代人にとって、中道の教えは心のバランスを保つための羅針盤です。仕事に追われて疲れ切ってしまう時、「もう少し力を抜いても大丈夫」と自分に優しくしてあげましょう。逆に、やる気が出ない時は「少しだけでも前進しよう」と自分を励ましてあげる。このバランス感覚が、長く続けられる幸せな人生を作ります。',
        'practices': [
            '完璧を求めすぎず、80%でも良しとする心構えを持つ',
            '疲れた時は無理せず休憩を取る',
            '怠けがちな時は小さな一歩を踏み出す',
            '他人と比較せず、自分のペースを大切にする'
        ],
        'reflection': '人生は長い道のりです。短距離走のように全力疾走し続けることはできません。かといって、立ち止まったままでも前に進めません。中道の教えは、自分にとって持続可能な生き方を見つけることの大切さを教えてくれます。',
        'story': 'お釈迦様は王子として何不自由ない生活を送った後、厳しい苦行を6年間続けました。しかし、どちらも悟りには至らず、適度な食事を取り、無理のない修行を続けることで初めて悟りを開いたと言われています。',
        'daily_practice': '今日一日、何かに取り組む時は「100%完璧でなくても大丈夫」と自分に言い聞かせてみましょう。そして疲れを感じたら、5分でも10分でも、自分を労わる時間を作ってあげてください。'
    },
    'ichigo_ichie': {
        'name': '一期一会',
        'pronunciation': 'いちごいちえ',
        'meaning': '一期一会とは、「一生に一度の出会い」という意味で、今この瞬間の出会いや体験を大切にする心構えを表す言葉です。茶道から生まれた言葉ですが、仏教的な無常観と深く結びついています。同じ瞬間は二度と訪れない、同じ人との同じ関係も二度とないということを心に刻み、今を精一杯生きることの大切さを教えてくれます。',
        'quote': '今この瞬間は、二度と戻らない かけがえのない時間',
        'application': '普段何気なくやり過ごしている日常の瞬間にも、実は深い意味があります。家族との食事、友人との会話、同僚との仕事。これらすべてが一期一会の出会いです。スマートフォンを見ながらの会話ではなく、相手の目を見て心を込めて接する。そうすることで、人間関係がより豊かになり、お互いにとって意味のある時間を過ごすことができます。',
        'practices': [
            '人と話す時はスマートフォンを置き、相手に集中する',
            '日常の小さな瞬間にも感謝の気持ちを持つ',
            '別れ際には「ありがとう」の言葉を忘れずに',
            '今日会う人すべてを大切な縁だと思って接する'
        ],
        'reflection': '人生は出会いと別れの連続です。毎日が一期一会の連続であり、今日という日も二度と戻ってきません。この教えを心に留めることで、何気ない日常が特別な意味を持つようになります。',
        'story': '茶道の千利休は、茶会での一期一会を大切にしました。同じメンバーで同じ茶室に集まっても、季節、天気、その日の心境により、まったく同じ茶会は二度とありません。だからこそ、その時を大切にするのです。',
        'daily_practice': '今日出会うすべての人に、心からの関心を向けてみましょう。コンビニの店員さん、電車で隣になった人、家族や同僚。すべてが貴重な一期一会の出会いです。'
    },
    'mujo': {
        'name': '諸行無常',
        'pronunciation': 'しょぎょうむじょう',
        'meaning': '諸行無常は仏教の根本的な教えの一つで、「すべてのものは変化し続け、永遠に同じ状態を保つものは何もない」という真理を表します。この世のすべて（諸行）は常に変化し（無常）、固定化されたものは存在しないということです。これは決して悲観的な教えではなく、変化があるからこそ成長や改善の可能性があり、苦しい状況も必ず変化するという希望の教えでもあります。',
        'quote': '変化こそが この世の唯一の不変の真理',
        'application': '仕事で失敗した時、人間関係でつまずいた時、健康を損なった時。そんな辛い状況にある時こそ、無常の教えが心の支えになります。「この状況も永遠に続くわけではない」「必ず変化の時が来る」と思うことで、絶望に打ちひしがれることなく、前向きに生きる力が湧いてきます。また、順調な時にも慢心せず、謙虚な気持ちを保つことができます。',
        'practices': [
            '辛い時は「これも変化する」と自分に言い聞かせる',
            '良い時も「この状況に感謝しつつ、永続しないことを忘れずに」と心に留める',
            '季節の移ろいを意識的に観察し、変化の美しさを感じる',
            '過去の辛い経験が今は良い思い出になっていることを思い出す'
        ],
        'reflection': '変化を恐れるのではなく、変化の中にこそ人生の豊かさがあることを理解しましょう。春夏秋冬があるからこそ自然は美しく、喜怒哀楽があるからこそ人生は深みを持ちます。',
        'story': 'お釈迦様は、ある母親が亡くなった子どもを抱いて泣いている姿を見て、「この世で死なない人がいる家から、芥子の種をもらってきなさい」と言いました。しかし、そのような家は存在しません。すべての家庭に死があり、無常があることを、母親は理解したのです。',
        'daily_practice': '今日感じる感情や起こる出来事に対して、「これも変化するもの」という視点を持ってみましょう。怒りや悲しみも、喜びや楽しさも、すべて流れゆくものです。'
    },
    'inga': {
        'name': '因果応報',
        'pronunciation': 'いんがおうほう',
        'meaning': '因果応報とは、良い行いには良い結果が、悪い行いには悪い結果が必ず返ってくるという仏教の根本的な教えです。「因」は原因、「果」は結果を意味し、すべての行為には必ず結果が伴うということです。これは決して恐怖を与える教えではなく、日々の小さな善行を積み重ねることで、自分や周りの人々の人生をより良いものにできるという希望の教えでもあります。',
        'quote': '善き種を蒔けば、善き実を収穫できる',
        'application': '日常生活の中で、人に親切にする、感謝の言葉を伝える、丁寧に仕事をするといった小さな良い行いを心がけましょう。それは必ず自分に返ってきます。また、怒りや愚痴、悪口などのネガティブな行為は控えめにし、できるだけ建設的で前向きな言動を選択することが大切です。',
        'practices': [
            '毎日一つは人に親切なことをする',
            '感謝の気持ちを言葉や行動で表現する',
            'ネガティブな発言を控え、建設的な言葉を選ぶ',
            '自分の行動が他人に与える影響を意識する'
        ],
        'reflection': '因果応報は即座に現れるものばかりではありません。時には長い時間をかけて結果が現れることもあります。大切なのは、結果を期待するのではなく、純粋な気持ちで良い行いを続けることです。',
        'story': '仏教の説話に、貧しい老女が仏様に一握りの砂を供養したところ、その純粋な気持ちが評価され、来世で王として生まれ変わったという話があります。行為の大小ではなく、心の在り方が重要だという教えです。',
        'daily_practice': '今日は意識的に、周りの人に対して親切な言葉をかけてみましょう。笑顔で挨拶する、「ありがとう」を多く言う、誰かの話を丁寧に聞くなど、小さなことから始めてください。'
    },
    'jihi': {
        'name': '慈悲',
        'pronunciation': 'じひ',
        'meaning': '慈悲とは、「慈」は楽を与えること、「悲」は苦を取り除くことを意味し、すべての生き物に対する深い思いやりの心を表します。仏教における最も重要な徳目の一つで、相手の幸せを願い、苦しみを共に感じ、それを和らげようとする温かい心のことです。慈悲は決して上から目線の同情ではなく、平等で無条件の愛情を意味します。',
        'quote': '慈悲の心は、すべての苦しみを癒す薬',
        'application': '慈悲の実践は、まず自分自身に優しくすることから始まります。自分を責めたり、完璧を求めすぎたりせず、失敗や弱さも含めて自分を受け入れましょう。そして、その温かさを家族、友人、知人、さらには見知らぬ人にまで広げていきます。相手の立場に立って考え、判断するよりも理解することを優先します。',
        'practices': [
            '自分の失敗や弱さを責めず、優しく受け入れる',
            '相手の気持ちや状況を想像してから話す',
            '困っている人を見かけたら、できる範囲で手を差し伸べる',
            '怒りを感じた時は、相手の事情を考えてみる'
        ],
        'reflection': '慈悲は特別な人だけが持つものではありません。誰もが生まれながらに持っている心の宝物です。日々の小さな実践を通じて、この宝物を磨き、光らせることができます。',
        'story': '観音菩薩は慈悲の象徴として親しまれています。千の手を持つ千手観音は、すべての人を救うために多くの手が必要だという慈悲の深さを表現していると言われています。',
        'daily_practice': '今日は自分と他人に対して、特に優しい気持ちで接してみましょう。イライラした時は深呼吸をして、「この人も幸せになりたいと願っている」ということを思い出してください。'
    }
}

@app.route('/blog/<teaching_key>')
def blog_article(teaching_key):
    """仏教の教えのブログ記事を表示"""
    teaching = DETAILED_TEACHINGS.get(teaching_key)
    if not teaching:
        abort(404)
    
    return render_template('teaching.html', teaching=teaching)

@app.route('/blog')
def blog_index():
    """ブログ記事一覧を表示"""
    teachings_list = []
    for key, teaching in DETAILED_TEACHINGS.items():
        teachings_list.append({
            'key': key,
            'name': teaching['name'],
            'pronunciation': teaching['pronunciation'],
            'url': f'/blog/{key}'
        })
    
    return render_template('blog_index.html', teachings=teachings_list)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))