import discord
from discord import app_commands
from discord.ext import commands
import json
import os

class ChatControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 경로 설정 (main.py의 data 폴더 구조 유지)
        self.data_folder = 'data'
        self.config_path = os.path.join(self.data_folder, 'config.json')
        self.backup_path = os.path.join(self.data_folder, 'chat_backups.json')

        # 폴더가 없으면 생성
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)

    # --- 헬퍼 함수들 (기존과 동일) ---
    def load_config(self):
        if not os.path.exists(self.config_path):
            return {"allowed_roles": []}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"설정 로드 오류: {e}")
            return {}

    def save_backup(self, channel_id, data):
        backups = {}
        if os.path.exists(self.backup_path):
            with open(self.backup_path, 'r', encoding='utf-8') as f:
                try:
                    backups = json.load(f)
                except json.JSONDecodeError:
                    backups = {}
        
        backups[str(channel_id)] = data
        with open(self.backup_path, 'w', encoding='utf-8') as f:
            json.dump(backups, f, indent=4, ensure_ascii=False)

    def load_backup(self, channel_id):
        if not os.path.exists(self.backup_path):
            return None
        with open(self.backup_path, 'r', encoding='utf-8') as f:
            try:
                backups = json.load(f)
                return backups.get(str(channel_id))
            except json.JSONDecodeError:
                return None

    def delete_backup(self, channel_id):
        if not os.path.exists(self.backup_path):
            return
        with open(self.backup_path, 'r', encoding='utf-8') as f:
            try:
                backups = json.load(f)
            except json.JSONDecodeError:
                return
        
        if str(channel_id) in backups:
            del backups[str(channel_id)]
            
        with open(self.backup_path, 'w', encoding='utf-8') as f:
            json.dump(backups, f, indent=4, ensure_ascii=False)

    # --- 슬래시 명령어 기능 ---

    @app_commands.command(name="얼리기", description="현재 채널의 채팅을 얼리고 상태를 백업합니다.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def freeze(self, interaction: discord.Interaction):
        """슬래시 명령어: /얼리기"""
        channel = interaction.channel
        config = self.load_config()
        allowed_role_ids = config.get("allowed_roles", [])
        
        # 이미 백업 데이터가 있는지 확인
        if self.load_backup(channel.id):
            embed = discord.Embed(title="⚠️ 알림", description="이미 얼려져 있는 채널 같습니다. (백업 데이터 존재)", color=discord.Color.orange())
            # ephemeral=True를 넣으면 명령어를 친 사람에게만 보입니다 (선택사항)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 1. 응답 대기 (작업이 길어질 수 있으므로)
        await interaction.response.defer()

        # 2. 현재 상태 백업 로직
        backup_data = {}
        
        # @everyone 권한 백업
        everyone_overwrite = channel.overwrites_for(interaction.guild.default_role)
        backup_data[str(interaction.guild.default_role.id)] = everyone_overwrite.send_messages

        # 허용 목록 역할 권한 백업 & 타겟 수집
        target_roles = []
        for role_id in allowed_role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                target_roles.append(role)
                role_overwrite = channel.overwrites_for(role)
                backup_data[str(role.id)] = role_overwrite.send_messages

        self.save_backup(channel.id, backup_data)

        # 3. 권한 변경 (얼리기)
        # @everyone 채팅 금지
        await channel.set_permissions(interaction.guild.default_role, send_messages=False)
        
        # 허용된 역할 채팅 가능
        for role in target_roles:
            await channel.set_permissions(role, send_messages=True)

        embed = discord.Embed(title="관리자가 해당 채널의 채팅을 얼렸습니다.", description="지정된 관리자 외에는 채팅을 칠 수 없습니다.", color=discord.Color.from_rgb(173, 216, 230))
        embed.set_footer(text=f"관리자: {interaction.user.display_name}")
        
        # defer()를 했으므로 followup.send로 보냅니다.
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="녹이기", description="채널을 녹이고 얼리기 전의 권한 상태로 복구합니다.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unfreeze(self, interaction: discord.Interaction):
        """슬래시 명령어: /녹이기"""
        channel = interaction.channel
        
        await interaction.response.defer() # 응답 대기

        backup_data = self.load_backup(channel.id)

        if not backup_data:
            await interaction.followup.send("⚠️ 복구할 백업 데이터가 없습니다. 기본 설정으로 @everyone 권한만 초기화합니다.", ephemeral=True)
            await channel.set_permissions(interaction.guild.default_role, send_messages=None)
            return

        # 4. 백업된 상태로 복구
        for role_id_str, perm_value in backup_data.items():
            role = interaction.guild.get_role(int(role_id_str))
            if role:
                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = perm_value
                
                if overwrite.is_empty():
                    await channel.set_permissions(role, overwrite=None)
                else:
                    await channel.set_permissions(role, overwrite=overwrite)

        self.delete_backup(channel.id)

        embed = discord.Embed(title="관리자가 해당 채널의 채팅을 녹였습니다.", description="채팅창이 이전 상태로 복구되었습니다.", color=discord.Color.from_rgb(255, 182, 193))
        embed.set_footer(text=f"관리자: {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    # 권한 오류 처리 (관리자가 아닌 사람이 쳤을 때)
    @freeze.error
    @unfreeze.error
    async def chat_control_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("⛔ 이 명령어를 사용할 권한이 없습니다. (채널 관리 권한 필요)", ephemeral=True)
        else:
            await interaction.response.send_message(f"오류가 발생했습니다: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ChatControl(bot))