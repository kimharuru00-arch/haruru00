import discord
from discord.ext import commands
import os
import json
import sqlite3
import logging # 로깅 추가

# --- 로깅 설정 ---
# 파일 핸들러 설정 (파일에 로그 저장)
file_handler = logging.FileHandler(filename='discord_bot.log', encoding='utf-8', mode='w')
file_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))

# 스트림 핸들러 설정 (콘솔에 로그 출력)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))

# 로거 설정
logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger('discord') # discord 라이브러리 로거 가져오기
logger.setLevel(logging.INFO) # 필요시 DEBUG로 변경하여 더 자세한 로그 확인 가능
discord_py_logger = logging.getLogger('discord') # discord.py 로거
discord_py_logger.setLevel(logging.INFO) # INFO 레벨 이상만 출력 (DEBUG는 너무 많음)


# --- 설정 불러오기 ---
def load_config():
    if not os.path.exists('data'): os.makedirs('data')
    config_path = 'data/config.json'
    
    # [수정] 기본 설정 파일에 GENERATOR_CHANNELS_CONFIG (객체)를 사용
    default_config = {"BOT_TOKEN": "YOUR_BOT_TOKEN_HERE", "GENERATOR_CHANNELS_CONFIG": {}}
    
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f: json.dump(default_config, f, indent=2)
        logger.warning(f"{config_path} 생성됨. 봇 토큰/채널 ID 입력 필요.")
        return default_config
    try:
        with open(config_path, 'r', encoding='utf-8') as f: config = json.load(f)
        
        # [수정] GENERATOR_CHANNELS_CONFIG 키를 검사
        if "BOT_TOKEN" not in config or "GENERATOR_CHANNELS_CONFIG" not in config:
             # [수정] 오류 메시지도 변경
             raise ValueError("필수 키(BOT_TOKEN, GENERATOR_CHANNELS_CONFIG) 누락.")
             
        if config["BOT_TOKEN"] == "YOUR_BOT_TOKEN_HERE": logger.warning("봇 토큰 미설정.")
        return config
    except Exception as e: logger.error(f"{config_path} 로드 오류: {e}"); raise e

config = load_config()
BOT_TOKEN = config.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# --- 데이터베이스 초기화 ---
def initialize_database():
    try:
        conn = sqlite3.connect('discord_bot.db')
        c = conn.cursor()
        # [수정] voice_cog.py에서 owner_id를 사용하므로 temp_channels 테이블에 owner_id 컬럼 추가
        c.execute('''
            CREATE TABLE IF NOT EXISTS temp_channels (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER
            )
        ''')
        
        # 기존 테이블에 owner_id 컬럼이 없는 경우를 대비하여 추가 (ALTER TABLE)
        try:
            c.execute("ALTER TABLE temp_channels ADD COLUMN owner_id INTEGER")
            logger.info("temp_channels 테이블에 'owner_id' 컬럼을 추가했습니다.")
        except sqlite3.OperationalError:
            pass # 컬럼이 이미 존재하면 오류가 발생하므로 무시
            
        c.execute('CREATE TABLE IF NOT EXISTS role_config (guild_id INTEGER PRIMARY KEY, role_id INTEGER NOT NULL, duration_days INTEGER NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS temp_role_users (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role_id INTEGER NOT NULL, expiry_date TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS user_role_permissions (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role_id INTEGER NOT NULL, UNIQUE(guild_id, user_id, role_id))')
        c.execute('CREATE TABLE IF NOT EXISTS anonymous_votes (poll_message_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (poll_message_id, user_id))')
        c.execute('CREATE TABLE IF NOT EXISTS toggleable_roles (guild_id INTEGER NOT NULL, role_id INTEGER NOT NULL, PRIMARY KEY (guild_id, role_id))')
        c.execute('CREATE TABLE IF NOT EXISTS economy (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, last_daily TEXT DEFAULT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS gacha_settings (guild_id INTEGER PRIMARY KEY, cost INTEGER DEFAULT 1000)')
        c.execute('CREATE TABLE IF NOT EXISTS gacha_roles (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, role_id INTEGER NOT NULL, UNIQUE(guild_id, role_id))')
        conn.commit()
        conn.close()
        logger.info("✅ 데이터베이스 테이블 초기화 완료.")
    except sqlite3.Error as e:
        logger.error(f"데이터베이스 초기화 오류: {e}")
        raise e # 초기화 실패 시 봇 중지

# --- 봇 클라이언트 설정 ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True; intents.voice_states = True; intents.message_content = True; intents.reactions = True
        super().__init__(command_prefix="!", intents=intents)
        self.config = config; self.active_games = {}; self.persistent_views_loaded = False

    async def setup_hook(self):
        initialize_database() # DB 먼저 초기화
        if not os.path.exists('cogs'): os.makedirs('cogs'); logger.info("정보: 'cogs' 폴더 생성됨.")
        loaded_cogs_count = 0
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                ext = f'cogs.{filename[:-3]}'
                try: await self.load_extension(ext); logger.info(f"✅ Cog '{filename[:-3]}' 로드 성공."); loaded_cogs_count += 1
                except commands.ExtensionAlreadyLoaded: logger.info(f"ℹ️ Cog '{filename[:-3]}' 는 이미 로드됨.")
                except Exception as e: logger.error(f"❌ Cog '{filename[:-3]}' 로드 실패: {e}", exc_info=True) # 상세 오류 로깅
        if loaded_cogs_count == 0: logger.warning("경고: 'cogs' 폴더에 로드할 .py 파일 없음.")

        # --- [수정] ---
        # Persistent Views 등록 블록이 삭제되었습니다.
        # 각 Cog의 setup 함수 (예: game_cog.py의 setup)가
        # bot.add_view()를 직접 호출하여 자신의 뷰를 등록합니다.
        # ----------------

        # 명령어 동기화
        try: synced = await self.tree.sync(); logger.info(f"✅ {len(synced)}개 슬래시 명령어 동기화 완료.")
        except Exception as e: logger.error(f"❌ 슬래시 명령어 동기화 실패: {e}", exc_info=True)

    async def on_ready(self):
        logger.info(f'✅ 로그인: {self.user} (ID: {self.user.id})')
        logger.info(f"   > 활동 서버: {[g.name for g in self.guilds]}")
        if self.user.id: logger.info(f"   > 초대 링크: https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=8&scope=bot%20applications.commands")
        logger.info("-----------------------------------------")

    async def on_command_error(self, ctx, error): # Prefix command error (if any)
        logger.error(f"명령어 오류 발생 (prefix): {error}", exc_info=True)
        # await ctx.send(f"오류 발생: {error}") # 사용자에게 알림 (선택 사항)

    async def on_error(self, event_method, *args, **kwargs): # General event error
         logger.error(f"이벤트 오류 발생 ({event_method}): {args}", exc_info=True)


# --- 봇 실행 ---
if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        logger.critical("="*40 + "\n오류: 봇 토큰 미설정!\ndata/config.json 확인 필요.\n" + "="*40)
    else:
        try:
            bot = MyBot()
            bot.run(BOT_TOKEN, log_handler=None) # 기본 핸들러 비활성화, 위에서 설정한 로거 사용
        except discord.errors.LoginFailure:
            logger.critical("="*40 + "\n오류: 잘못된 봇 토큰.\ndata/config.json 확인 필요.\n" + "="*40)
        except discord.errors.PrivilegedIntentsRequired:
             logger.critical("="*40 + "\n오류: Intents 미활성화.\nDiscord 개발자 포털 확인 필요.\n" + "="*40)
        except Exception as e:
            logger.critical(f"봇 실행 중 치명적 오류: {e}", exc_info=True)