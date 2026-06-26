import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
import sqlite3
import datetime
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    try:
        conn = sqlite3.connect('discord_bot.db')
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn
    except sqlite3.Error as e:
        logger.error(f"DB 연결 오류: {e}")
        return None

# --- UI 컴포넌트 ---
class TempRoleModal(ui.Modal, title='기간 설정'):
    def __init__(self, role: discord.Role, original_view):
        super().__init__(timeout=None)
        self.role = role
        self.original_view = original_view
    duration = ui.TextInput(label='역할 유지 기간 (일)', placeholder='예: 30', style=discord.TextStyle.short, required=True, min_length=1)

    async def on_submit(self, interaction: discord.Interaction):
        try: days = int(str(self.duration.value))
        except ValueError: return await interaction.response.send_message("숫자만 입력.", ephemeral=True)
        if days <= 0: return await interaction.response.send_message("기간은 1일 이상.", ephemeral=True)
        
        conn = get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            conn.execute("INSERT OR REPLACE INTO role_config (guild_id, role_id, duration_days) VALUES (?, ?, ?)",
                         (interaction.guild.id, self.role.id, days))
            conn.commit()
            await interaction.response.send_message(f"✅ 설정 완료! '{self.role.name}' 역할은 **{days}일**간 유지.", ephemeral=True)
            
            new_embed = discord.Embed(title="⏰ 기간제 역할 관리", color=discord.Color.blue())
            new_embed.description = f"현재 **{self.role.mention}** 역할이 **{days}일** 기간제로 설정됨."
            if interaction.message: # Check if original message exists
                 await interaction.message.edit(embed=new_embed, view=self.original_view)
        except sqlite3.Error as e:
            logger.error(f"TempRoleModal DB 오류: {e}")
            await interaction.response.send_message("DB 오류 발생.", ephemeral=True)
        except discord.HTTPException as e:
            logger.warning(f"TempRoleModal UI 수정 오류: {e}")
            await interaction.followup.send(f"✅ 설정 완료! '{self.role.name}' 역할은 **{days}일**간 유지. (UI 업데이트 실패)", ephemeral=True)
        except Exception as e:
            logger.error(f"TempRoleModal 알 수 없는 오류: {e}", exc_info=True)
            await interaction.response.send_message(f"오류 발생: {e}", ephemeral=True)
        finally:
            if conn: conn.close()

# 뽑기 비용 설정 Modal
class GachaCostModal(ui.Modal, title="뽑기 비용 설정"):
    cost_input = ui.TextInput(label="1회 뽑기 비용", placeholder="예: 1000", style=discord.TextStyle.short, required=True, min_length=1)

    async def on_submit(self, interaction: discord.Interaction):
        try: cost = int(self.cost_input.value)
        except ValueError: return await interaction.response.send_message("올바른 숫자를 입력해주세요.", ephemeral=True)
        if cost < 0: return await interaction.response.send_message("0 이상의 금액을 입력해주세요.", ephemeral=True)

        conn = get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            conn.execute("INSERT OR REPLACE INTO gacha_settings (guild_id, cost) VALUES (?, ?)", (interaction.guild.id, cost))
            conn.commit()
            await interaction.response.send_message(f"✅ 뽑기 비용이 **{cost:,}원**으로 설정되었습니다.", ephemeral=True)
        except sqlite3.Error as e:
            logger.error(f"GachaCostModal DB 오류: {e}")
            await interaction.response.send_message("DB 오류 발생.", ephemeral=True)
        finally:
            if conn: conn.close()

# --- 관리자 제어판 View ---
class MainControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 명령어로 매번 생성

    @ui.button(label="기간제 역할 관리", style=discord.ButtonStyle.primary, custom_id="temp_role_manage_btn")
    async def temp_role_manage(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        conn=get_db_connection(); config=None
        if conn: config = conn.execute("SELECT * FROM role_config WHERE guild_id = ?", (interaction.guild.id,)).fetchone(); conn.close()
        embed = discord.Embed(title="⏰ 기간제 역할 관리", color=discord.Color.blue())
        if config and (role := interaction.guild.get_role(config['role_id'])):
             embed.description = f"현재 **{role.mention}** 역할이 **{config['duration_days']}일** 기간제로 설정됨."
        else: embed.description = "기간제 역할 미설정."
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=TempRoleSettingsView(self))

    @ui.button(label="역할 토글 허용", style=discord.ButtonStyle.secondary, custom_id="toggle_role_permit_btn")
    async def toggle_role_permit(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="🔧 역할 토글 권한 관리 (수동)", description="권한 부여/제거할 유저와 역할 선택.", color=discord.Color.green())
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=ToggleRolePermsView(self))

    @ui.button(label="셀프 역할 설정", style=discord.ButtonStyle.success, custom_id="self_role_config_btn")
    async def self_role_config(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="✨ 셀프 역할 설정 (자동)", description="등록된 역할은 직접 부여 시 자동 토글 권한 부여.", color=discord.Color.teal())
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=SelfRoleConfigView(self))

    @ui.button(label="⚙️ 뽑기 설정", style=discord.ButtonStyle.grey, custom_id="gacha_config_btn")
    async def gacha_config(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        conn = get_db_connection(); current_cost = 1000 # 기본값
        if conn:
            setting = conn.execute("SELECT cost FROM gacha_settings WHERE guild_id = ?", (interaction.guild_id,)).fetchone()
            if setting: current_cost = setting['cost']
            conn.close()
        embed = discord.Embed(title="⚙️ 뽑기 설정", description=f"현재 1회 뽑기 비용: **{current_cost:,}원**", color=discord.Color.blurple())
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=GachaConfigView(self))

class TempRoleSettingsView(ui.View):
    def __init__(self, main_view: ui.View):
        super().__init__(timeout=None)
        self.main_view = main_view
        self.selected_role_id = None
        role_select = ui.RoleSelect(placeholder="설정할 역할 선택...", custom_id="temp_role_select")
        role_select.callback = self.on_role_select
        self.add_item(role_select)
    async def on_role_select(self, interaction: discord.Interaction):
        self.selected_role_id = int(interaction.data['values'][0])
        role = interaction.guild.get_role(self.selected_role_id)
        role_name = role.name if role else "알 수 없는 역할"
        await interaction.response.send_message(f"'{role_name}' 선택됨. '기간 설정' 클릭.", ephemeral=True)
    @ui.button(label="기간 설정", style=discord.ButtonStyle.success, custom_id="set_duration_btn")
    async def set_duration(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_role_id: return await interaction.response.send_message("역할 먼저 선택.", ephemeral=True)
        role = interaction.guild.get_role(self.selected_role_id)
        if not role: return await interaction.response.send_message("역할을 찾을 수 없음.", ephemeral=True)
        await interaction.response.send_modal(TempRoleModal(role, self))
    @ui.button(label="대상자 목록 보기", style=discord.ButtonStyle.secondary, custom_id="view_list_btn")
    async def view_list(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        conn=get_db_connection(); user_list = [];
        if conn: user_list = conn.execute("SELECT * FROM temp_role_users WHERE guild_id = ? ORDER BY expiry_date ASC", (interaction.guild.id,)).fetchall(); conn.close()
        if not user_list: return await interaction.followup.send("기간제 역할 유저 없음.", ephemeral=True)
        embed = discord.Embed(title="기간제 역할 유저 목록", color=discord.Color.green())
        lines = []
        for d in user_list:
             m=interaction.guild.get_member(d['user_id']); u=m.mention if m else f"탈퇴 (ID:{d['user_id']})"
             try: t=f"<t:{int(datetime.datetime.fromisoformat(d['expiry_date']).timestamp())}:R>"
             except Exception: t="날짜 오류"
             lines.append(f"{u} - 만료: {t}")
        embed.description="\n".join(lines) if lines else "목록 로드 실패."
        await interaction.followup.send(embed=embed, ephemeral=True)
    @ui.button(label="뒤로 가기", style=discord.ButtonStyle.danger, custom_id="go_back_temp_btn")
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="👑 서버 관리 제어판", description="작업 선택.", color=discord.Color.purple())
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=MainControlView())

class ToggleRolePermsView(ui.View):
    def __init__(self, main_view: ui.View):
        super().__init__(timeout=None)
        self.main_view = main_view
        self.selected_user_id = None; self.selected_role_id = None
        user_select = ui.UserSelect(placeholder="대상 유저 선택...", custom_id="toggle_perm_user_select")
        user_select.callback = self.on_user_select; self.add_item(user_select)
        role_select = ui.RoleSelect(placeholder="대상 역할 선택...", custom_id="toggle_perm_role_select")
        role_select.callback = self.on_role_select; self.add_item(role_select)
    async def on_user_select(self, interaction: discord.Interaction):
        self.selected_user_id = int(interaction.data['values'][0]) # Store ID
        await interaction.response.send_message("유저 선택됨.", ephemeral=True)
    async def on_role_select(self, interaction: discord.Interaction):
        self.selected_role_id = int(interaction.data['values'][0]) # Store ID
        await interaction.response.send_message("역할 선택됨.", ephemeral=True)
    @ui.button(label="권한 부여", style=discord.ButtonStyle.success, custom_id="grant_perm_btn")
    async def grant_perm(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_user_id or not self.selected_role_id: return await interaction.response.send_message("유저와 역할 모두 선택.", ephemeral=True)
        conn=get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            conn.execute("INSERT INTO user_role_permissions (guild_id, user_id, role_id) VALUES (?, ?, ?)", (interaction.guild.id, self.selected_user_id, self.selected_role_id)); conn.commit()
            u=interaction.guild.get_member(self.selected_user_id); r=interaction.guild.get_role(self.selected_role_id)
            await interaction.response.send_message(f"✅ {u.mention if u else '유저'}에게 '{r.name if r else '역할'}' 토글 권한 부여.", ephemeral=True)
        except sqlite3.IntegrityError: await interaction.response.send_message("이미 부여된 권한.", ephemeral=True)
        except sqlite3.Error as e: logger.error(f"권한 부여 DB 오류: {e}"); await interaction.response.send_message("DB 오류.", ephemeral=True)
        finally: conn.close()
    @ui.button(label="권한 제거", style=discord.ButtonStyle.danger, custom_id="revoke_perm_btn")
    async def revoke_perm(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_user_id or not self.selected_role_id: return await interaction.response.send_message("유저와 역할 모두 선택.", ephemeral=True)
        conn=get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            cursor=conn.cursor()
            cursor.execute("DELETE FROM user_role_permissions WHERE guild_id = ? AND user_id = ? AND role_id = ?", (interaction.guild.id, self.selected_user_id, self.selected_role_id)); conn.commit()
            if cursor.rowcount > 0:
                u=interaction.guild.get_member(self.selected_user_id); r=interaction.guild.get_role(self.selected_role_id)
                await interaction.response.send_message(f"➖ {u.mention if u else '유저'}의 '{r.name if r else '역할'}' 토글 권한 제거.", ephemeral=True)
            else: await interaction.response.send_message("부여된 권한 아님.", ephemeral=True)
        except sqlite3.Error as e: logger.error(f"권한 제거 DB 오류: {e}"); await interaction.response.send_message("DB 오류.", ephemeral=True)
        finally: conn.close()
    @ui.button(label="뒤로 가기", style=discord.ButtonStyle.secondary, row=2, custom_id="go_back_toggle_perm_btn")
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="👑 서버 관리 제어판", description="작업 선택.", color=discord.Color.purple())
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=MainControlView())

# --- 뽑기 설정 UI ---
class GachaConfigView(ui.View):
    def __init__(self, main_view: ui.View):
        super().__init__(timeout=None)
        self.main_view = main_view
        self.selected_role_id = None

        role_select = ui.RoleSelect(placeholder="상품 목록에 추가/제거할 역할 선택...", custom_id="gacha_role_select")
        role_select.callback = self.on_role_select
        self.add_item(role_select)

    async def on_role_select(self, interaction: discord.Interaction):
        self.selected_role_id = int(interaction.data['values'][0])
        role = interaction.guild.get_role(self.selected_role_id)
        await interaction.response.send_message(f"'{role.name if role else '알 수 없는 역할'}' 선택됨. 아래 버튼 클릭.", ephemeral=True)

    @ui.button(label="비용 변경", style=discord.ButtonStyle.success)
    async def change_cost(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(GachaCostModal())

    @ui.button(label="상품 역할 추가", style=discord.ButtonStyle.primary)
    async def add_role(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_role_id: return await interaction.response.send_message("역할 먼저 선택.", ephemeral=True)
        conn = get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            conn.execute("INSERT INTO gacha_roles (guild_id, role_id) VALUES (?, ?)", (interaction.guild.id, self.selected_role_id)); conn.commit()
            r = interaction.guild.get_role(self.selected_role_id)
            await interaction.response.send_message(f"✅ '{r.name if r else '역할'}' 뽑기 상품 목록에 추가.", ephemeral=True)
        except sqlite3.IntegrityError: await interaction.response.send_message("이미 상품 목록에 있음.", ephemeral=True)
        except sqlite3.Error as e: logger.error(f"뽑기 역할 추가 DB 오류: {e}"); await interaction.response.send_message("DB 오류.", ephemeral=True)
        finally: conn.close()

    @ui.button(label="상품 역할 제거", style=discord.ButtonStyle.danger)
    async def remove_role(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_role_id: return await interaction.response.send_message("역할 먼저 선택.", ephemeral=True)
        conn=get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            cursor=conn.cursor()
            cursor.execute("DELETE FROM gacha_roles WHERE guild_id = ? AND role_id = ?", (interaction.guild.id, self.selected_role_id)); conn.commit()
            if cursor.rowcount > 0:
                r = interaction.guild.get_role(self.selected_role_id)
                await interaction.response.send_message(f"➖ '{r.name if r else '역할'}' 뽑기 상품 목록에서 제거.", ephemeral=True)
            else: await interaction.response.send_message("목록에 없는 역할.", ephemeral=True)
        except sqlite3.Error as e: logger.error(f"뽑기 역할 제거 DB 오류: {e}"); await interaction.response.send_message("DB 오류.", ephemeral=True)
        finally: conn.close()

    @ui.button(label="상품 목록 보기", style=discord.ButtonStyle.secondary)
    async def view_roles(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        conn=get_db_connection(); roles_data = []
        if conn:
            try: roles_data = conn.execute("SELECT role_id FROM gacha_roles WHERE guild_id = ?", (interaction.guild.id,)).fetchall()
            except sqlite3.Error as e: logger.error(f"뽑기 역할 목록 DB 오류: {e}")
            finally: conn.close()
        if not roles_data: return await interaction.followup.send("뽑기 상품 역할 없음.", ephemeral=True)
        mentions = [r.mention for r_id in roles_data if (r := interaction.guild.get_role(r_id['role_id']))]
        embed = discord.Embed(title="🎁 현재 뽑기 상품 역할 목록", description="\n".join(mentions) if mentions else "설정된 역할 없음/찾을수없음.", color=discord.Color.blurple())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="뒤로 가기", style=discord.ButtonStyle.grey)
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="👑 서버 관리 제어판", description="작업 선택.", color=discord.Color.purple())
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=MainControlView())


class SelfRoleConfigView(ui.View):
    def __init__(self, main_view: ui.View):
        super().__init__(timeout=None)
        self.main_view = main_view
        self.selected_role_id = None
        role_select = ui.RoleSelect(placeholder="추가/제거할 역할 선택...", custom_id="self_cfg_role_select")
        role_select.callback = self.on_role_select; self.add_item(role_select)
    async def on_role_select(self, interaction: discord.Interaction):
        self.selected_role_id = int(interaction.data['values'][0])
        role = interaction.guild.get_role(self.selected_role_id)
        await interaction.response.send_message(f"'{role.name if role else '알 수 없는 역할'}' 선택됨.", ephemeral=True)
    @ui.button(label="목록에 추가", style=discord.ButtonStyle.success, custom_id="self_cfg_add_btn")
    async def add_to_list(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_role_id: return await interaction.response.send_message("역할 먼저 선택.", ephemeral=True)
        conn = get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            conn.execute("INSERT INTO toggleable_roles (guild_id, role_id) VALUES (?, ?)", (interaction.guild.id, self.selected_role_id)); conn.commit()
            r = interaction.guild.get_role(self.selected_role_id)
            await interaction.response.send_message(f"✅ '{r.name if r else '역할'}' 셀프 역할 목록에 추가.", ephemeral=True)
        except sqlite3.IntegrityError: await interaction.response.send_message("이미 목록에 있음.", ephemeral=True)
        except sqlite3.Error as e: logger.error(f"셀프 역할 추가 DB 오류: {e}"); await interaction.response.send_message("DB 오류.", ephemeral=True)
        finally: conn.close()
    @ui.button(label="목록에서 제거", style=discord.ButtonStyle.danger, custom_id="self_cfg_remove_btn")
    async def remove_from_list(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_role_id: return await interaction.response.send_message("역할 먼저 선택.", ephemeral=True)
        conn=get_db_connection()
        if not conn: return await interaction.response.send_message("DB 연결 오류.", ephemeral=True)
        try:
            cursor=conn.cursor()
            cursor.execute("DELETE FROM toggleable_roles WHERE guild_id = ? AND role_id = ?", (interaction.guild.id, self.selected_role_id)); conn.commit()
            if cursor.rowcount > 0:
                r = interaction.guild.get_role(self.selected_role_id)
                await interaction.response.send_message(f"➖ '{r.name if r else '역할'}' 셀프 역할 목록에서 제거.", ephemeral=True)
            else: await interaction.response.send_message("목록에 없는 역할.", ephemeral=True)
        except sqlite3.Error as e: logger.error(f"셀프 역할 제거 DB 오류: {e}"); await interaction.response.send_message("DB 오류.", ephemeral=True)
        finally: conn.close()
    @ui.button(label="목록 보기", style=discord.ButtonStyle.secondary, custom_id="self_cfg_view_btn")
    async def view_list(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        conn=get_db_connection(); roles_data = []
        if conn:
            try: roles_data = conn.execute("SELECT role_id FROM toggleable_roles WHERE guild_id = ?", (interaction.guild.id,)).fetchall()
            except sqlite3.Error as e: logger.error(f"셀프 역할 목록 DB 오류: {e}")
            finally: conn.close()
        if not roles_data: return await interaction.followup.send("셀프 역할 설정 없음.", ephemeral=True)
        mentions = [r.mention for r_id in roles_data if (r := interaction.guild.get_role(r_id['role_id']))]
        embed = discord.Embed(title="✨ 현재 설정된 셀프 역할 목록", description="\n".join(mentions) if mentions else "설정된 역할 없음/찾을수없음.", color=discord.Color.teal())
        await interaction.followup.send(embed=embed, ephemeral=True)
    @ui.button(label="뒤로 가기", style=discord.ButtonStyle.grey, custom_id="self_cfg_back_btn")
    async def go_back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="👑 서버 관리 제어판", description="작업 선택.", color=discord.Color.purple())
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=MainControlView())


# --- [새로운] 유저 셀프 역할 다중 선택 (체크박스) UI ---
class UserSelfRoleSelect(ui.Select):
    def __init__(self, guild: discord.Guild, user_roles: list[discord.Role], allowed_roles: list[discord.Role]):
        self.guild = guild
        self.user_roles_set = set(user_roles)
        self.allowed_roles_map = {role.id: role for role in allowed_roles}

        options = []
        for role in allowed_roles:
            options.append(
                discord.SelectOption(
                    label=role.name,
                    value=str(role.id),
                    default=(role in self.user_roles_set) # 유저가 이미 가진 역할이면 default=True (체크됨)
                )
            )

        super().__init__(
            placeholder="역할을 선택해주세요 (다중 선택 가능)",
            min_values=0, # 0개 선택 = 모든 역할 해제
            max_values=len(options), # 모든 역할 선택 가능
            options=options,
            custom_id="user_self_role_multi_select"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # 유저가 최종적으로 선택한(체크한) 역할 ID 목록
        selected_role_ids = set(int(val) for val in self.values)
        
        roles_to_add = []
        roles_to_remove = []

        # 허용된 역할 전체를 기준으로 판단
        for role_id, role in self.allowed_roles_map.items():
            # 1. 유저가 선택했고(체크) & 현재 가지고 있지 않은 역할 -> 추가 대상
            if role_id in selected_role_ids and role not in self.user_roles_set:
                roles_to_add.append(role)
            # 2. 유저가 선택하지 않았고(해제) & 현재 가지고 있는 역할 -> 제거 대상
            elif role_id not in selected_role_ids and role in self.user_roles_set:
                roles_to_remove.append(role)

        try:
            if roles_to_add:
                await interaction.user.add_roles(*roles_to_add, reason="유저 셀프 역할 추가")
            if roles_to_remove:
                await interaction.user.remove_roles(*roles_to_remove, reason="유저 셀프 역할 제거")
            
            # View 비활성화
            self.disabled = True
            view = ui.View(timeout=None)
            view.add_item(self)
            await interaction.edit_original_response(content="✅ 역할이 성공적으로 변경되었습니다.", view=view)

        except discord.Forbidden:
            await interaction.followup.send("❌ 봇 권한 부족. (역할 관리 권한 확인)", ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send("❌ 역할 변경 중 오류 발생.", ephemeral=True)
        except Exception as e:
            logger.error(f"셀프 역할 변경 오류: {e}", exc_info=True)
            await interaction.followup.send("❌ 알 수 없는 오류 발생.", ephemeral=True)


class RoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_expired_roles.start()

    def cog_unload(self):
        self.check_expired_roles.cancel()

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles == after.roles: return
        
        conn = get_db_connection()
        if not conn: return # DB 연결 실패 시 아무것도 안 함
        
        try:
            added_roles = set(after.roles) - set(before.roles)
            
            if added_roles:
                for new_role in added_roles:
                    # --- 기간제 역할 로직 (유지) ---
                    config = conn.execute("SELECT * FROM role_config WHERE guild_id = ? AND role_id = ?", (after.guild.id, new_role.id)).fetchone()
                    if config:
                        dur = config['duration_days']; exp = datetime.datetime.now() + datetime.timedelta(days=dur)
                        conn.execute("INSERT INTO temp_role_users (guild_id, user_id, role_id, expiry_date) VALUES (?, ?, ?, ?)", (after.guild.id, after.id, new_role.id, exp.strftime('%Y-%m-%d %H:%M:%S')))
                        logger.info(f"[Record] {after.display_name} got temp role '{new_role.name}'.")
                    
                    # --- 셀프 역할 권한 자동 부여 로직 (유지) ---
                    is_toggleable = conn.execute("SELECT 1 FROM toggleable_roles WHERE guild_id = ? AND role_id = ?", (after.guild.id, new_role.id)).fetchone()
                    if is_toggleable:
                        try:
                            conn.execute("INSERT INTO user_role_permissions (guild_id, user_id, role_id) VALUES (?, ?, ?)", (after.guild.id, after.id, new_role.id))
                            logger.info(f"[Auto Grant] {after.display_name} granted toggle for '{new_role.name}'.")
                        except sqlite3.IntegrityError: pass # Already has permission
                        
            # --- [수정됨] 역할 제거 시 권한 회수 로직 삭제 ---
            # 유저가 스스로 역할을 제거해도 (ex: /역할 사용) 
            # user_role_permissions에 저장된 권한은 삭제되지 않고 유지됩니다.
            
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"on_member_update DB 오류: {e}")
            conn.rollback() # 오류 발생 시 롤백
        except Exception as e:
            logger.error(f"on_member_update 알 수 없는 오류: {e}", exc_info=True)
        finally:
            conn.close()

    @tasks.loop(minutes=5)
    async def check_expired_roles(self):
        await self.bot.wait_until_ready()
        conn = get_db_connection()
        if not conn: return
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            expired = conn.execute("SELECT * FROM temp_role_users WHERE expiry_date <= ?", (now_str,)).fetchall()
            if not expired: return # Processed in finally
            
            guild_cache = {}; processed_ids = []
            for row in expired:
                g_id, u_id, r_id = row['guild_id'], row['user_id'], row['role_id']
                guild = guild_cache.get(g_id) or self.bot.get_guild(g_id)
                if not guild: continue
                guild_cache[g_id] = guild
                
                member = guild.get_member(u_id)
                role = guild.get_role(r_id)
                
                if member and role:
                    try:
                        await member.remove_roles(role, reason="기간 만료")
                        logger.info(f"[회수] {member.display_name}님 '{role.name}' 역할 기간 만료.")
                    except discord.Forbidden: logger.error(f"[회수 실패] {member.display_name}님 '{role.name}' 역할 - 권한 부족.")
                    except discord.HTTPException as e: logger.error(f"[회수 실패] {member.display_name}님 '{role.name}' - API 오류: {e}")
                
                processed_ids.append((row['id'],))
                
            if processed_ids:
                conn.executemany("DELETE FROM temp_role_users WHERE id = ?", processed_ids); conn.commit()
        except sqlite3.Error as e:
             logger.error(f"check_expired_roles DB 오류: {e}")
        except Exception as e:
             logger.error(f"check_expired_roles 루프 오류: {e}", exc_info=True)
        finally:
             if conn: conn.close()

    # --- Slash Commands ---
    @app_commands.command(name="관리", description="관리자용 제어판을 엽니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def manage(self, interaction: discord.Interaction):
        embed = discord.Embed(title="👑 서버 관리 제어판", description="작업 선택.", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, view=MainControlView(), ephemeral=True)

    @app_commands.command(name="권한-보기", description="특정 유저의 셀프 역할 권한 목록을 봅니다.")
    @app_commands.describe(유저="권한 확인할 유저")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def view_permissions(self, interaction: discord.Interaction, 유저: discord.Member):
        await interaction.response.defer(ephemeral=True)
        conn=get_db_connection(); perms = []
        if conn:
            try: perms = conn.execute("SELECT role_id FROM user_role_permissions WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, 유저.id)).fetchall()
            except sqlite3.Error as e: logger.error(f"권한 보기 DB 오류: {e}")
            finally: conn.close()
        
        embed = discord.Embed(title=f"📜 {유저.display_name}님의 권한 목록", color=discord.Color.gold())
        if not perms: embed.description = "허용된 역할 없음."
        else:
             mentions = [r.mention for p in perms if (r := interaction.guild.get_role(p['role_id']))]
             embed.description = "\n".join(mentions) if mentions else "역할을 찾을 수 없음."
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- [수정된] /역할 명령어 ---
    @app_commands.command(name="역할", description="나에게 허용된 역할을 끄거나 켭니다. (다중 선택)")
    async def toggle_role_ui(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        conn = get_db_connection()
        perms = []
        if conn:
            try:
                perms = conn.execute("SELECT role_id FROM user_role_permissions WHERE user_id = ? AND guild_id = ?", (interaction.user.id, interaction.guild.id)).fetchall()
            except sqlite3.Error as e:
                logger.error(f"셀프 역할 DB 오류: {e}")
                await interaction.followup.send("DB 오류 발생.", ephemeral=True)
                return
            finally:
                conn.close()

        if not perms:
            return await interaction.followup.send("❌ 변경 가능한 역할이 없습니다.", ephemeral=True)

        user_current_roles = interaction.user.roles
        allowed_roles = []
        for perm in perms:
            role = interaction.guild.get_role(perm['role_id'])
            if role: # 역할이 서버에서 삭제되지 않았는지 확인
                allowed_roles.append(role)
        
        if not allowed_roles:
            return await interaction.followup.send("❌ 설정된 역할을 서버에서 찾을 수 없습니다.", ephemeral=True)

        # View 및 Select 생성
        view = ui.View(timeout=180) # 3분 타임아웃
        select_menu = UserSelfRoleSelect(
            guild=interaction.guild,
            user_roles=user_current_roles,
            allowed_roles=allowed_roles
        )
        view.add_item(select_menu)
            
        embed = discord.Embed(title="✨ 역할 변경하기 (다중 선택)", 
                            description="원하는 역할을 모두 선택/해제한 후 메뉴를 닫아주세요.\n(현재 가진 역할은 미리 선택되어 있습니다)", 
                            color=discord.Color.gold())
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RoleCog(bot))