import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
import sqlite3
import datetime
import random
import asyncio

# --- 설정값 ---
VOICE_INTERVAL_MINUTES = 10
VOICE_REWARD = 100
CHAT_INTERVAL_MESSAGES = 10
CHAT_REWARD = 50
DAILY_REWARD = 50000
DAILY_COOLDOWN_HOURS = 24
MIN_BET = 100
# -------------

def get_db_connection():
    conn = sqlite3.connect('discord_bot.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

# --- 가위바위보 UI ---
class RPSView(ui.View):
    def __init__(self, interaction: discord.Interaction, amount: int, cog):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.amount = amount
        self.cog = cog
        self.user_choice = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("다른 사람의 게임에 참여할 수 없습니다!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for item in self.children: item.disabled = True
            try:
                await self.interaction.channel.fetch_message(self.message.id)
                embed = discord.Embed(title="⏰ 시간이 초과되었습니다.", description="가위바위보 게임이 취소되었습니다.", color=discord.Color.orange())
                await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                pass

    async def handle_game(self, interaction: discord.Interaction, user_choice: str):
        for item in self.children: item.disabled = True
        await interaction.response.defer()

        user_id = interaction.user.id
        balance = await self.cog.get_balance(user_id)

        if balance < self.amount:
            embed = discord.Embed(title="❌ 게임 진행 불가", description=f"잔액이 부족합니다. (현재 잔액: {balance:,}원)", color=discord.Color.red())
            await interaction.followup.edit_message(message_id=self.message.id, embed=embed, view=self)
            return

        choices = ["가위", "바위", "보"]
        bot_choice = random.choice(choices)
        result, amount_change, color = "", 0, discord.Color.default()

        if user_choice == bot_choice:
            result, amount_change, color = "무승부!", 0, discord.Color.greyple()
        elif (user_choice == "가위" and bot_choice == "보") or \
             (user_choice == "바위" and bot_choice == "가위") or \
             (user_choice == "보" and bot_choice == "바위"):
            result, amount_change, color = "승리!", self.amount, discord.Color.green()
        else:
            result, amount_change, color = "패배...", -self.amount, discord.Color.red()

        if await self.cog.update_balance(user_id, amount_change):
            new_balance = balance + amount_change
            embed = discord.Embed(title=f"가위바위보 결과: {result}", color=color)
            embed.add_field(name="나의 선택", value=user_choice, inline=True)
            embed.add_field(name="봇의 선택", value=bot_choice, inline=True)
            if amount_change > 0: embed.description = f"**{amount_change:,}원**을 땄습니다!"
            elif amount_change < 0: embed.description = f"**{abs(amount_change):,}원**을 잃었습니다."
            else: embed.description = "본전입니다."
            embed.set_footer(text=f"현재 잔액: {new_balance:,}원")
        else:
            embed = discord.Embed(title="❌ 오류", description="잔액 업데이트 중 오류가 발생했습니다.", color=discord.Color.orange())

        await interaction.followup.edit_message(message_id=self.message.id, embed=embed, view=self)

    @ui.button(label="가위 ✂️", style=discord.ButtonStyle.primary, custom_id="rps_rock_btn")
    async def rock(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_game(interaction, "가위")

    @ui.button(label="바위 👊", style=discord.ButtonStyle.primary, custom_id="rps_paper_btn")
    async def paper(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_game(interaction, "바위")

    @ui.button(label="보 🖐️", style=discord.ButtonStyle.primary, custom_id="rps_scissors_btn")
    async def scissors(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_game(interaction, "보")

# --- Economy Cog ---
class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_join_times = {}
        self.message_counts = {}
        self.voice_currency_loop.start()

    def cog_unload(self):
        self.voice_currency_loop.cancel()

    async def get_balance(self, user_id: int) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result['balance'] if result else 0

    async def update_balance(self, user_id: int, amount: int) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if amount < 0:
                cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                if not result or result['balance'] < abs(amount):
                    conn.close(); return False
            cursor.execute("INSERT OR IGNORE INTO economy (user_id, balance) VALUES (?, 0)", (user_id,))
            cursor.execute("UPDATE economy SET balance = MAX(0, balance + ?) WHERE user_id = ?", (amount, user_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error as e:
            print(f"DB Error update_balance for {user_id}: {e}")
            conn.rollback(); conn.close(); return False

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        user_id = message.author.id
        self.message_counts[user_id] = self.message_counts.get(user_id, 0) + 1
        if self.message_counts[user_id] >= CHAT_INTERVAL_MESSAGES:
            if await self.update_balance(user_id, CHAT_REWARD):
                print(f"[Chat Reward] {message.author.display_name} +{CHAT_REWARD}원")
                self.message_counts[user_id] = 0

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        user_id = member.id
        now = datetime.datetime.now()
        if after.channel and not before.channel and not member.bot and not after.afk:
            self.voice_join_times[user_id] = now
            print(f"[Voice Join] {member.display_name} in {after.channel.name}")
        elif user_id in self.voice_join_times and ((not after.channel and before.channel) or (after.afk and not before.afk)):
            if user_id in self.voice_join_times: del self.voice_join_times[user_id]
            print(f"[Voice Leave/AFK] {member.display_name} from {before.channel.name if before.channel else 'Unknown'}")

    @tasks.loop(minutes=VOICE_INTERVAL_MINUTES)
    async def voice_currency_loop(self):
        await self.bot.wait_until_ready()
        now = datetime.datetime.now()
        for user_id, join_time in list(self.voice_join_times.items()):
            member = None
            for guild in self.bot.guilds: member = guild.get_member(user_id);
            if member: break
            if not member or not member.voice or not member.voice.channel or member.voice.afk:
                 if user_id in self.voice_join_times: del self.voice_join_times[user_id]
                 continue
            if await self.update_balance(user_id, VOICE_REWARD):
                print(f"[Voice Reward] {member.display_name} +{VOICE_REWARD}원")
                self.voice_join_times[user_id] = now

    # --- Slash Commands ---
    @app_commands.command(name="잔액", description="자신 또는 다른 유저의 재화를 확인합니다.")
    @app_commands.describe(유저="잔액을 확인할 유저 (선택)")
    async def balance(self, interaction: discord.Interaction, 유저: discord.Member = None):
        target_user = 유저 or interaction.user
        bal = await self.get_balance(target_user.id)
        embed = discord.Embed(title=f"💰 {target_user.display_name}님의 잔액", description=f"현재 **{bal:,}원**을 보유하고 있습니다.", color=discord.Color.gold())
        if target_user.display_avatar: embed.set_thumbnail(url=target_user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=(유저 is None))

    @app_commands.command(name="돈줘", description=f"{DAILY_COOLDOWN_HOURS}시간마다 {DAILY_REWARD:,}원을 받습니다.")
    async def daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        now = datetime.datetime.now()
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT last_daily, balance FROM economy WHERE user_id = ?", (user_id,))
        result = cursor.fetchone(); current_balance = result['balance'] if result else 0
        can_claim, remaining_str = False, ""
        if not result or not result['last_daily']: can_claim = True
        else:
            try:
                last_daily_time = datetime.datetime.fromisoformat(result['last_daily'])
                time_diff = now - last_daily_time
                if time_diff >= datetime.timedelta(hours=DAILY_COOLDOWN_HOURS): can_claim = True
                else:
                    r_time = (last_daily_time + datetime.timedelta(hours=DAILY_COOLDOWN_HOURS)) - now
                    h, rem = divmod(r_time.total_seconds(), 3600); m, _ = divmod(rem, 60)
                    remaining_str = f"{int(h)}시간 {int(m)}분" if h>=1 else f"{int(m)}분"
            except ValueError: can_claim = True
        if can_claim:
            cursor.execute("INSERT OR REPLACE INTO economy (user_id, balance, last_daily) VALUES (?, ?, ?)", (user_id, current_balance, now.isoformat())); conn.commit()
            if await self.update_balance(user_id, DAILY_REWARD):
                embed = discord.Embed(title="✅ 돈 받기 성공!", description=f"{DAILY_REWARD:,}원 획득!\n현재 잔액: **{(current_balance + DAILY_REWARD):,}원**", color=discord.Color.green())
                await interaction.response.send_message(embed=embed)
            else: embed = discord.Embed(title="❌ 오류", description="잔액 업데이트 실패.", color=discord.Color.red()); await interaction.response.send_message(embed=embed, ephemeral=True)
        else: embed = discord.Embed(title="⏰ 쿨타임!", description=f"다음 수령까지 **{remaining_str}** 남음.", color=discord.Color.orange()); await interaction.response.send_message(embed=embed, ephemeral=True)
        conn.close()

    @app_commands.command(name="송금", description="다른 유저에게 재화를 보냅니다.")
    @app_commands.describe(받는사람="재화를 받을 유저", 금액="보낼 금액")
    async def send_money(self, interaction: discord.Interaction, 받는사람: discord.Member, 금액: int):
        sender = interaction.user; receiver = 받는사람
        if sender.id == receiver.id: return await interaction.response.send_message("자신에게 송금 불가.", ephemeral=True)
        if 금액 <= 0: return await interaction.response.send_message("금액은 0보다 커야 함.", ephemeral=True)
        if receiver.bot: return await interaction.response.send_message("봇에게 송금 불가.", ephemeral=True)
        if await self.update_balance(sender.id, -금액):
            if await self.update_balance(receiver.id, 금액):
                s_bal = await self.get_balance(sender.id); r_bal = await self.get_balance(receiver.id)
                embed = discord.Embed(title="💸 송금 완료!", color=discord.Color.blue())
                embed.add_field(name="보낸 사람", value=sender.mention, inline=True); embed.add_field(name="받는 사람", value=receiver.mention, inline=True)
                embed.add_field(name="금액", value=f"{금액:,}원", inline=False); embed.set_footer(text=f"송금 후 잔액: {s_bal:,}원")
                await interaction.response.send_message(embed=embed)
                try: dm_embed = discord.Embed(title="💰 입금 알림", description=f"{sender.mention}에게 **{금액:,}원** 받음!\n현재 잔액: **{r_bal:,}원**", color=discord.Color.green()); await receiver.send(embed=dm_embed)
                except discord.Forbidden: pass
            else: await self.update_balance(sender.id, 금액); embed = discord.Embed(title="❌ 송금 오류", description="받는 사람 잔액 업데이트 실패.", color=discord.Color.red()); await interaction.response.send_message(embed=embed, ephemeral=True)
        else: s_bal = await self.get_balance(sender.id); embed = discord.Embed(title="❌ 송금 실패", description=f"잔액 부족 (현재: {s_bal:,}원)", color=discord.Color.red()); await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="도박", description="가지고 있는 돈의 일부를 걸고 도박을 합니다.")
    @app_commands.describe(금액="걸 금액 (최소 100원)")
    async def gamble(self, interaction: discord.Interaction, 금액: int):
        uid = interaction.user.id
        if 금액 < MIN_BET: return await interaction.response.send_message(f"최소 {MIN_BET:,}원.", ephemeral=True)
        bal = await self.get_balance(uid);
        if bal < 금액: return await interaction.response.send_message(f"잔액 부족 (현재: {bal:,}원)", ephemeral=True)
        win = random.choice([True, False]); change = 금액 if win else -금액
        if await self.update_balance(uid, change):
            n_bal = bal + change
            if win: embed = discord.Embed(title="🎉 도박 성공!", description=f"**{금액:,}원** 획득!\n현재 잔액: **{n_bal:,}원**", color=discord.Color.green())
            else: embed = discord.Embed(title="💥 도박 실패...", description=f"**{금액:,}원** 잃음.\n현재 잔액: **{n_bal:,}원**", color=discord.Color.red())
        else: embed = discord.Embed(title="❌ 도박 오류", description="잔액 업데이트 실패.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="가위바위보", description="봇과 가위바위보 게임을 합니다.")
    @app_commands.describe(금액="걸 금액 (최소 100원)")
    async def rps_ui(self, interaction: discord.Interaction, 금액: int):
        uid = interaction.user.id
        if 금액 < MIN_BET: return await interaction.response.send_message(f"최소 {MIN_BET:,}원.", ephemeral=True)
        bal = await self.get_balance(uid)
        if bal < 금액: return await interaction.response.send_message(f"잔액 부족 (현재: {bal:,}원)", ephemeral=True)
        view = RPSView(interaction, 금액, self); embed = discord.Embed(title="가위바위보!", description=f"{금액:,}원을 걸었습니다. 선택하세요!", color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=view); view.message = await interaction.original_response()

    # --- [수정] 지급 명령어: 특정 유저 ID만 사용 가능 + 본인만 보이게 제한 ---
    @app_commands.command(name="지급", description="특정 유저에게 재화를 지급합니다.")
    @app_commands.describe(대상="재화를 지급할 유저", 금액="지급할 금액")
    async def give_money(self, interaction: discord.Interaction, 대상: discord.Member, 금액: int):
        if interaction.user.id != 1451215822092505099:
            return await interaction.response.send_message("❌ 이 명령어를 사용할 권한이 없습니다.", ephemeral=True)

        if 대상.bot: return await interaction.response.send_message("봇에게 지급 불가.", ephemeral=True)
        if 금액 <= 0: return await interaction.response.send_message("금액은 0보다 커야 함.", ephemeral=True)
        
        if await self.update_balance(대상.id, 금액):
            bal = await self.get_balance(대상.id)
            embed = discord.Embed(title="✅ 재화 지급", description=f"{대상.mention}에게 **{금액:,}원** 지급 완료.\n현재 잔액: **{bal:,}원**", color=discord.Color.green())
            # [수정됨] ephemeral=True 를 추가하여 본인에게만 메시지가 보입니다.
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else: 
            embed = discord.Embed(title="❌ 지급 오류", description="잔액 업데이트 실패.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="차감", description="관리자가 특정 유저의 재화를 차감합니다.")
    @app_commands.describe(대상="재화를 차감할 유저", 금액="차감할 금액")
    @app_commands.checks.has_permissions(administrator=True)
    async def take_money(self, interaction: discord.Interaction, 대상: discord.Member, 금액: int):
        if 대상.bot: return await interaction.response.send_message("봇에게서 차감 불가.", ephemeral=True)
        if 금액 <= 0: return await interaction.response.send_message("금액은 0보다 커야 함.", ephemeral=True)
        cur_bal = await self.get_balance(대상.id)
        if cur_bal < 금액: return await interaction.response.send_message(f"차감 불가 (잔액: {cur_bal:,}원).", ephemeral=True)
        if await self.update_balance(대상.id, -금액):
            n_bal = await self.get_balance(대상.id)
            embed = discord.Embed(title="✅ 재화 차감", description=f"{대상.mention}에게서 **{금액:,}원** 차감 완료.\n현재 잔액: **{n_bal:,}원**", color=discord.Color.orange())
            await interaction.response.send_message(embed=embed)
        else: embed = discord.Embed(title="❌ 차감 오류", description="잔액 업데이트 실패.", color=discord.Color.red()); await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="랭킹", description="서버 내 재화 보유 순위 TOP 10을 확인합니다.")
    async def ranking(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT user_id, balance FROM economy WHERE balance > 0 ORDER BY balance DESC LIMIT 10")
        top_users = cursor.fetchall(); conn.close()
        embed = discord.Embed(title="🏆 재화 보유 랭킹 TOP 10", color=discord.Color.gold())
        if not top_users: embed.description = "랭킹 데이터 없음."
        else:
            rank_text = ""
            for rank, data in enumerate(top_users, 1):
                member = interaction.guild.get_member(data['user_id'])
                name = member.mention if member else f"탈퇴 유저({data['user_id']})"
                rank_text += f"{rank}. {name} - **{data['balance']:,}원**\n"
            embed.description = rank_text
        await interaction.followup.send(embed=embed)

    # Error handler
    @take_money.error
    async def admin_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions): await interaction.response.send_message("권한 부족.", ephemeral=True)
        else: print(f"Admin Econ Error: {error}"); await interaction.response.send_message("명령어 오류.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))