import discord
from discord import ui, app_commands
from discord.ext import commands
import sqlite3
import re

def get_db_connection():
    conn = sqlite3.connect('discord_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

class PollView(ui.View):
    def __init__(self, options):
        super().__init__(timeout=None)
        for i, option_text in enumerate(options):
            button = ui.Button(label=f"{option_text} (0표)", style=discord.ButtonStyle.secondary, custom_id=f"poll_option_{i}")
            button.callback = self.button_callback
            self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        conn = get_db_connection()
        try:
            voted = conn.execute("SELECT 1 FROM anonymous_votes WHERE poll_message_id = ? AND user_id = ?",
                                 (interaction.message.id, interaction.user.id)).fetchone()
            if voted:
                await interaction.followup.send("이미 이 투표에 참여하셨습니다.", ephemeral=True)
                return
            conn.execute("INSERT INTO anonymous_votes (poll_message_id, user_id) VALUES (?, ?)",
                         (interaction.message.id, interaction.user.id))
            conn.commit()
        finally:
            conn.close()
        
        button = discord.utils.get(self.children, custom_id=interaction.data["custom_id"])
        current_votes = int(re.search(r"\((\d+)표\)", button.label).group(1))
        new_votes = current_votes + 1
        option_text = re.sub(r" \(\d+표\)", "", button.label)
        button.label = f"{option_text} ({new_votes}표)"
        await interaction.message.edit(view=self)
        await interaction.followup.send("🗳️ 투표가 성공적으로 기록되었습니다.", ephemeral=True)

class PollCreateModal(ui.Modal, title="익명 투표 만들기"):
    poll_title = ui.TextInput(label="투표 제목", placeholder="오늘 저녁 메뉴는?", style=discord.TextStyle.short, required=True)
    options = ui.TextInput(label="선택지 (줄바꿈으로 구분)", placeholder="치킨\n피자\n족발", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        option_list = self.options.value.strip().split('\n')
        if len(option_list) < 2 or len(option_list) > 5:
            await interaction.response.send_message("선택지는 2개 이상 5개 이하로 만들어주세요.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📊 {self.poll_title.value}", description="아래 버튼을 눌러 투표에 참여해주세요!", color=discord.Color.dark_gold())
        embed.set_footer(text=f"{interaction.user.display_name}님이 시작한 투표")
        view = PollView(options=option_list)
        await interaction.response.send_message(embed=embed, view=view)


class PollCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 봇이 재시작되어도 기존 투표 View가 계속 작동하도록 등록합니다.
        self.bot.add_view(PollView(options=[]))

    @app_commands.command(name="익명투표", description="익명으로 진행되는 투표를 생성합니다.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def create_poll(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PollCreateModal())

async def setup(bot):
    await bot.add_cog(PollCog(bot))