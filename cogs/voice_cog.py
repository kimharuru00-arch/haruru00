import discord
from discord.ext import commands
import sqlite3
import random

def get_db_connection():
    conn = sqlite3.connect('discord_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # config.json에서 GENERATOR_CHANNELS_CONFIG 객체를 불러옵니다.
        config_data = self.bot.config.get('GENERATOR_CHANNELS_CONFIG', {})
        self.generator_channels_config = {int(k): v for k, v in config_data.items()}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        
        # 채널 ID가 설정에 있는지 확인
        if after.channel and after.channel.id in self.generator_channels_config:
            category = after.channel.category
            if category:
                try:
                    # 설정에서 이름 형식(들) 가져오기
                    channel_name_formats = self.generator_channels_config[after.channel.id]
                    
                    # 리스트면 랜덤 선택, 문자열이면 그대로 사용
                    if isinstance(channel_name_formats, list) and channel_name_formats:
                        channel_name_format = random.choice(channel_name_formats)
                    elif isinstance(channel_name_formats, str):
                        channel_name_format = channel_name_formats
                    else:
                        channel_name_format = "{member_name}의 채널"

                    new_channel_name = channel_name_format.format(member_name=member.display_name)

                    # --- [수정된 부분 시작] 인원수 제한 로직 추가 ---
                    target_limit = 0  # 기본값: 0 (무제한)
                    
                    # 잠수중 생성 채널(1424852917374029936)인 경우 인원수를 1명으로 설정
                    if after.channel.id == 1424852917374029936:
                        target_limit = 1
                    # --- [수정된 부분 끝] ---

                    # 권한 설정
                    overwrites = {
                        # 1. 모든 유저(@everyone)에 대한 기본 권한 설정
                        category.guild.default_role: discord.PermissionOverwrite(
                            view_channel=True,          # 채널 보이기
                            connect=True,               # 입장 가능
                            speak=True,                 # 마이크 사용 가능
                            use_voice_activation=True,  # 음성 감지 사용 가능
                            send_messages=True          # 채팅 메시지 보내기 가능
                        ),
                        
                        # 2. 방 생성자(member)에게 관리 권한 부여
                        member: discord.PermissionOverwrite(
                            manage_channels=True,       # 채널 설정(이름, 인원수) 변경 가능
                            move_members=True,          # 멤버 이동/강퇴 가능
                            view_channel=True,
                            connect=True,
                            speak=True,
                            use_voice_activation=True,
                            send_messages=True
                        )
                    }

                    # 채널 생성 (user_limit 옵션 추가됨)
                    new_channel = await category.create_voice_channel(
                        name=new_channel_name,
                        overwrites=overwrites,
                        user_limit=target_limit  # 여기에 계산된 인원수 제한을 적용해요!
                    )
                    
                    await member.move_to(new_channel)
                    
                    conn = get_db_connection()
                    conn.execute("INSERT INTO temp_channels (channel_id, owner_id) VALUES (?, ?)", 
                                 (new_channel.id, member.id))
                    conn.commit()
                    conn.close()
                    
                    limit_msg = " (인원수: 1명)" if target_limit == 1 else ""
                    print(f"'{member.display_name}' 님이 '{new_channel_name}' 채널을 생성했습니다.{limit_msg}")
                    
                except Exception as e:
                    print(f"채널 생성 중 오류 발생: {e}")

        # 채널 삭제 로직 (기존과 동일)
        if before.channel is not None:
            conn = get_db_connection()
            c = conn.cursor()
            temp_channel_data = c.execute("SELECT * FROM temp_channels WHERE channel_id = ?", (before.channel.id,)).fetchone()
            
            if temp_channel_data and len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="임시 채널 자동 삭제")
                    c.execute("DELETE FROM temp_channels WHERE channel_id = ?", (before.channel.id,))
                    conn.commit()
                    print(f"임시 채널 '{before.channel.name}'이(가) 자동으로 삭제되었습니다.")
                except Exception as e:
                    c.execute("DELETE FROM temp_channels WHERE channel_id = ?", (before.channel.id,))
                    conn.commit()
                    print(f"채널 삭제 중 오류 발생 (DB만 정리): {e}")
            conn.close()

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))