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
    },
    'chisoku': {
        'name': '知足',
        'pronunciation': 'ちそく',
        'meaning': '知足とは、「足るを知る」という意味で、今あるものに満足し感謝する心を表します。現代社会は「もっと欲しい」「もっと持ちたい」という欲望に駆り立てられがちですが、知足の教えは、既に自分が持っているものの価値に気づき、それに感謝することの大切さを説いています。これは決して向上心を捨てることではなく、今の状況を受け入れながらも、心穏やかに成長していく智慧です。',
        'quote': '足りないものを数えるより、あるものに感謝しよう',
        'application': '毎日の生活の中で、当たり前だと思っていることに目を向けてみましょう。健康な体、安全な住まい、美味しい食事、家族や友人との時間。これらは決して当たり前ではなく、多くの恵みが重なって成り立っています。SNSで他人と比較して落ち込むよりも、自分の人生にある小さな幸せを数えてみることで、心が軽やかになります。',
        'practices': [
            '毎朝起きた時に、今日あることに3つ感謝する',
            '他人と比較しそうになったら、自分の良いところを思い出す',
            '物を買う前に「本当に必要か」を一度考える',
            '家族や友人の存在に改めて感謝の言葉を伝える'
        ],
        'reflection': '知足の心は、幸せを外に求めるのではなく、内側に見つける智慧です。欲望には際限がありませんが、感謝の心には無限の豊かさがあります。',
        'story': '中国の老子は「足るを知る者は富む」と言いました。また、仏教の経典には「少欲知足」という言葉があり、欲を少なくして足ることを知る者こそが真の豊かさを得ると教えています。',
        'daily_practice': '今日は意識的に、当たり前だと思っていることに感謝してみましょう。朝のコーヒー、家族の笑顔、安全に歩ける道。小さなことから感謝の気持ちを育てていってください。'
    },
    'imakoko': {
        'name': '今ここ',
        'pronunciation': 'いまここ',
        'meaning': '「今ここ」とは、過去の後悔や未来の不安にとらわれることなく、現在のこの瞬間に意識を向けて生きることの大切さを説く教えです。マインドフルネスの根本的な考え方でもあり、仏教では「正念」と呼ばれます。私たちの心は常に過去と未来を行き来していますが、実際に生きているのは「今」だけです。この瞬間に集中することで、心の平安と深い気づきを得ることができます。',
        'quote': '過去は記憶、未来は想像、現実は今この瞬間だけ',
        'application': '日常生活の中で、今していることに完全に注意を向ける練習をしてみましょう。食事をする時は味わうことに集中し、歩く時は足の感覚に意識を向け、人と話す時は相手の言葉に耳を傾ける。スマートフォンを見ながらの「ながら行動」をやめて、一つ一つの行動を丁寧に行うことで、人生の質が格段に向上します。',
        'practices': [
            '食事の時は最初の一口を味わって食べる',
            '歩く時は足の裏の感覚を意識する',
            '呼吸に意識を向けて深呼吸を3回する',
            '不安になったら「今、ここで何が起きているか」を観察する'
        ],
        'reflection': '今この瞬間こそが、私たちが本当に生きている時間です。過去を変えることはできませんし、未来はまだ来ていません。今に集中することで、人生がより豊かで意味深いものになります。',
        'story': 'お釈迦様は弟子たちに「今この瞬間の呼吸に意識を向けなさい」と教えました。これが仏教瞑想の基本であり、2500年前から続く「今ここ」を生きる実践法です。',
        'daily_practice': '今日は何をする時も、最初の5分間は完全にその行動に集中してみましょう。スマートフォンを置いて、今この瞬間を存分に味わってください。'
    },
    'muga': {
        'name': '無我',
        'pronunciation': 'むが',
        'meaning': '無我とは、固定的で不変の「自我」は存在しないという仏教の根本的な教えです。私たちは「これが自分だ」という強いアイデンティティを持ちがちですが、実際の自分は常に変化し続けており、様々な要因によって形作られています。無我の教えは、自我への執着を手放すことで、より自由で柔軟な生き方ができることを示しています。これは自分を否定することではなく、より大きな視点から自分を見つめることです。',
        'quote': '執着を手放せば、心は軽やかに空を舞う',
        'application': '自分のイメージや他人からの評価に固執しすぎず、もっと自然体で生きることを心がけましょう。「こうでなければならない」という思い込みを手放し、状況に応じて柔軟に対応する。失敗しても「それも自分の一部」と受け入れ、成功しても慢心せず謙虚でいる。このような姿勢が、ストレスの少ない生き方につながります。',
        'practices': [
            '自分の意見に固執せず、他の考え方も受け入れる',
            '失敗した時は「完璧でなくても大丈夫」と自分を慰める',
            '他人からの評価を気にしすぎず、自分らしさを大切にする',
            '変化を恐れず、新しい経験を歓迎する'
        ],
        'reflection': '無我の教えは、真の自由への道を示しています。自我の檻から解放されることで、もっと広い世界を見ることができ、他者との深いつながりを感じることができます。',
        'story': 'ある修行僧が「自分とは何か」と悩んでいた時、師匠は川を指して言いました。「あの川は常に流れているが、同じ水は二度と流れない。それでも私たちは『川』と呼ぶ。あなたもまた、常に変化する川のようなものだ」と。',
        'daily_practice': '今日は自分の固定観念を一つ手放してみましょう。「いつもこうしている」ことを少し変えてみたり、新しい視点で物事を見てみたりして、柔軟性を育ててください。'
    },
    'niniku': {
        'name': '忍辱',
        'pronunciation': 'にんにく',
        'meaning': '忍辱とは、困難や苦しみに遭遇した時に、怒りや恨みに支配されることなく、心の平静を保つ強さを意味します。「忍」は耐える、「辱」は屈辱や困難を表し、単に我慢することではなく、智慧をもって状況を受け入れ、そこから学びを得る積極的な姿勢を指します。現代のストレス社会において、この教えは心の resilience（回復力）を育てる重要な智慧となります。',
        'quote': '困難は成長への扉、忍耐は その鍵',
        'application': '人生で困難に直面した時、まず深呼吸をして感情を落ち着かせましょう。「この経験から何を学べるか」「どのように成長できるか」という視点を持つことで、被害者意識から抜け出すことができます。また、他人からの理不尽な扱いを受けた時も、相手の事情を想像し、怒りに支配されずに冷静に対処することで、より良い解決策を見つけることができます。',
        'practices': [
            'イライラした時は10秒数えてから反応する',
            '困難な状況を「成長のチャンス」と捉え直す',
            '他人の言動に振り回されず、自分の価値観を大切にする',
            '辛い経験をした後は、そこから得た学びを書き出してみる'
        ],
        'reflection': '忍辱は弱さではなく、内なる強さの表れです。一時的な感情に流されず、長期的な視点を持つことで、真の解決と成長を得ることができます。',
        'story': 'お釈迦様は前世で忍辱仙人として修行していた時、悪王に体を切り刻まれても恨みを抱かず、慈悲の心を保ち続けたという話があります。この究極の忍辱によって、悟りへの道が開かれたとされています。',
        'daily_practice': '今日何かイライラすることがあったら、まず深呼吸をして「この状況から何を学べるか」を考えてみましょう。怒りではなく、智慧で対応することを心がけてください。'
    },
    'fuse': {
        'name': '布施',
        'pronunciation': 'ふせ',
        'meaning': '布施とは、見返りを求めることなく、他者に施しを与える行為です。仏教では、物質的な施し（財施）、恐怖を取り除く施し（無畏施）、智慧や教えを与える施し（法施）の三つがありますが、最も大切なのは純粋な心からの行為です。布施は相手のためだけでなく、自分の心も豊かにし、執着心を手放す修行でもあります。小さな親切や笑顔も立派な布施になります。',
        'quote': '与えることで受け取り、手放すことで豊かになる',
        'application': '日常生活の中で、できる範囲で他者に喜びや安らぎを与えることを心がけましょう。お金や物だけでなく、笑顔、優しい言葉、時間を割いて話を聞くこと、道を譲ることなど、小さな行為も大きな意味を持ちます。大切なのは、見返りを期待せず、純粋な気持ちで行うことです。そうすることで、自分の心も軽やかになり、周りとの関係も温かくなります。',
        'practices': [
            '毎日一つは人に親切なことをする',
            '電車で席を譲る、道を教えるなど小さな親切を心がける',
            '家族や友人の話を時間をかけて丁寧に聞く',
            '寄付やボランティアなど、できる範囲で社会貢献をする'
        ],
        'reflection': '真の豊かさは、どれだけ持っているかではなく、どれだけ与えられるかにあります。布施の心を持つことで、自分も周りも幸せになる循環が生まれます。',
        'story': '貧しい老婆が仏様に一銭の施しをした時、富豪が大金を寄進した時よりも大きな功徳があったという話があります。大切なのは金額ではなく、その人なりの精一杯の心だということを教えています。',
        'daily_practice': '今日は意識的に、誰かのために何かをしてみましょう。コンビニの店員さんに笑顔で挨拶する、家族のお手伝いをする、友人に励ましのメッセージを送るなど、小さなことから始めてください。'
    },
    'shoken': {
        'name': '正見',
        'pronunciation': 'しょうけん',
        'meaning': '正見とは、物事をありのままに、正しく見る智慧のことです。八正道の最初に位置する重要な教えで、私たちの認識の歪みや偏見、先入観を取り除き、真実を見抜く目を養うことを意味します。日常生活では、感情や思い込みに左右されず、客観的で冷静な判断力を身につけることです。正見を持つことで、適切な行動と正しい人生の歩み方が可能になります。',
        'quote': '曇りなき心の目で、真実を見つめよう',
        'application': '何かの判断をする時、まず一歩引いて状況を客観視する習慣をつけましょう。感情的になっている時ほど、「事実は何か」「自分の思い込みはないか」を確認することが大切です。また、メディアの情報や他人の意見も鵜呑みにせず、複数の角度から検証する姿勢を持ちます。人間関係でも、相手の行動の背景や事情を考慮することで、より適切な対応ができます。',
        'practices': [
            '怒りを感じた時は一度立ち止まり、状況を客観視する',
            'ニュースや情報は複数の源から確認する習慣をつける',
            '人を判断する前に、その人の立場や事情を考える',
            '自分の偏見や先入観に気づいたら、素直に見直す'
        ],
        'reflection': '正見は一朝一夕に身につくものではありません。日々の小さな気づきの積み重ねによって、徐々に曇りのない心の目が育まれていきます。',
        'story': 'ある弟子が師匠に「真実とは何ですか」と尋ねました。師匠は透明な水の入ったコップを見せて言いました。「これが真実だ。色も味もつけていない、ありのままの状態。私たちの心もこのように透明でなければならない」と。',
        'daily_practice': '今日は何かを判断する前に、「これは事実か、それとも私の解釈か」を一度確認してみましょう。先入観を手放して、新鮮な目で物事を見る練習をしてください。'
    },
    'kutai': {
        'name': '苦諦',
        'pronunciation': 'くたい',
        'meaning': '苦諦とは、仏教の四諦の第一で、人生には苦しみが存在するという真理を認識することです。これは人生を悲観的に見ることではなく、苦しみの存在を受け入れることで、それに適切に対処できるという智慧です。苦しみの多くは、現実と理想のギャップ、執着、無知から生まれます。苦諦を理解することは、苦しみから解放される第一歩となります。',
        'quote': '苦しみを受け入れることが、解放への第一歩',
        'application': '人生で困難や悲しみに遭遇した時、「なぜ私だけが」と嘆くのではなく、「これも人生の一部」として受け入れることから始めましょう。苦しみを否定したり逃避したりするのではなく、その存在を認めることで、冷静に対処法を考えることができます。また、他人の苦しみにも理解を示し、共感することで、より深い人間関係を築くことができます。',
        'practices': [
            '困難に直面した時は「これも人生の学び」と受け入れる',
            '完璧を求めず、不完全さも人生の一部と理解する',
            '他人の苦しみに対して批判せず、共感を示す',
            '苦しい時こそ、自分を大切にする時間を作る'
        ],
        'reflection': '苦しみは人生から完全に取り除くことはできませんが、それとの付き合い方を変えることはできます。苦諦の理解は、より成熟した人生観を育てます。',
        'story': 'お釈迦様が初めて老人、病人、死者を見た時、人生の苦しみの現実に目覚めました。この体験が、苦しみからの解放を求める修行の出発点となったのです。',
        'daily_practice': '今日感じる小さな不満や苦しみに対して、「これも人生の一部」という視点を持ってみましょう。抵抗するのではなく、受け入れることで心が楽になることを体験してください。'
    },
    'engi': {
        'name': '縁起',
        'pronunciation': 'えんぎ',
        'meaning': '縁起とは、すべての存在や現象は他との関係性の中で成り立っており、独立して存在するものは何もないという仏教の根本的な教えです。私たち一人一人も、無数の縁（関係性）によって今の自分が形作られています。家族、友人、自然、社会、さらには見知らぬ人々まで、すべてが複雑に絡み合って現在の状況を作り出しています。この理解は、感謝の心と責任感を育みます。',
        'quote': 'すべては繋がっている、あなたの笑顔も誰かの幸せの一部',
        'application': '日常生活の中で、自分を支えてくれている見えない縁に気づくことを心がけましょう。食事一つとっても、農家の方、運送業の方、店員さんなど多くの人の働きがあって成り立っています。また、自分の行動も他者に影響を与えていることを意識し、良い縁を作り出すような言動を心がけることで、より豊かな人間関係を築くことができます。',
        'practices': [
            '食事の前に、食材に関わった人々に感謝する',
            '自分の行動が他人に与える影響を考えてから行動する',
            '困っている人を見かけたら、良い縁を作るつもりで手助けする',
            '家族や友人との関係を大切にし、感謝を表現する'
        ],
        'reflection': '縁起の理解は、個人主義を超えた大きな視点を与えてくれます。私たちは孤立した存在ではなく、大きな生命の網の中の一部なのです。',
        'story': 'インドラの網という比喩があります。宇宙は巨大な網のようで、交差点ごとに宝石があり、それぞれが他のすべての宝石を映し出している。一つの宝石の輝きが全体に影響を与えるように、私たちの行動も全体に響いていくのです。',
        'daily_practice': '今日は自分を支えてくれている見えない縁に意識を向けてみましょう。そして、自分も誰かにとって良い縁になれるよう、温かい心で人と接してください。'
    },
    'ku': {
        'name': '空',
        'pronunciation': 'くう',
        'meaning': '空とは、すべての存在に固定的な実体がないという仏教の深遠な教えです。「色即是空、空即是色」という般若心経の有名な言葉が示すように、私たちが「これ」だと思っているものも、実は常に変化し、他との関係性の中でのみ存在しています。空の理解は、執着を手放し、柔軟で自由な心を育てることにつながります。これは虚無主義ではなく、真の自由への扉です。',
        'quote': '固定観念を手放せば、無限の可能性が広がる',
        'application': '日常生活では、「こうでなければならない」という固定的な考えを柔軟にすることから始めましょう。仕事のやり方、人間関係、自分の性格について、「これが絶対」と思わず、状況に応じて変化することを恐れない。失敗も成功も、永続的なものではないと理解することで、一喜一憂することなく、平常心を保つことができます。',
        'practices': [
            '「絶対にこうだ」という思い込みを疑ってみる',
            '変化を恐れず、新しい可能性に心を開く',
            '失敗しても「これも変化するもの」と受け入れる',
            '他人の意見や価値観の違いを柔軟に受け入れる'
        ],
        'reflection': '空の教えは、最も深い仏教の智慧の一つです。理解するのに時間がかかりますが、少しずつでも実践することで、心の自由度が格段に高まります。',
        'story': '龍樹菩薩は空の思想を体系化した偉大な哲学者です。彼は「すべては空であるが故に、すべてが可能である」と説きました。固定的でないからこそ、変化と成長が可能なのです。',
        'daily_practice': '今日は一つの固定観念を手放してみましょう。「いつもこうしている」ことを少し変えてみたり、新しい角度から物事を見てみたりして、心の柔軟性を育ててください。'
    },
    'shojin': {
        'name': '精進',
        'pronunciation': 'しょうじん',
        'meaning': '精進とは、正しい目標に向かって継続的に努力することを意味します。単なる頑張りではなく、智慧に基づいた適切な方向性を持った努力です。仏教では六波羅蜜の一つとして重視され、怠惰に流されることなく、また無理をしすぎることもなく、中道の精神で持続可能な努力を続けることが大切とされています。小さな歩みでも続けることで、大きな成果につながります。',
        'quote': '千里の道も一歩から、継続は力なり',
        'application': '大きな目標を達成するために、まず小さな習慣から始めましょう。一日10分の読書、毎朝の散歩、感謝の気持ちを書き留めるなど、無理のない範囲で続けられることを選ぶことが重要です。また、完璧を求めず、途中で休んでも自分を責めずに、再び始めることができる柔軟性も精進の一部です。継続することで、自信と inner strength が育まれます。',
        'practices': [
            '毎日続けられる小さな良い習慣を一つ決める',
            '三日坊主になっても自分を責めず、また始める',
            '大きな目標を小さなステップに分解する',
            '努力の過程を楽しみ、結果だけにこだわらない'
        ],
        'reflection': '精進は marathon であり、sprint ではありません。急がず、止まらず、自分のペースで歩み続けることが、最終的に大きな成果と内面の成長をもたらします。',
        'story': 'ある修行僧が「どうすれば悟りを得られますか」と師匠に尋ねました。師匠は庭で石に水を垂らし続ける装置を見せて言いました。「この小さな水滴が、やがて硬い石に穴を開ける。精進とはこういうことだ」と。',
        'daily_practice': '今日から続けたい小さな良い習慣を一つ決めて、実際に始めてみましょう。完璧を求めず、「今日一日だけ」という気持ちで取り組むことから始めてください。'
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