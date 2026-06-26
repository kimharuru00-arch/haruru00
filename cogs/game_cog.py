import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
import sqlite3
import random
import asyncio
import logging
import math

# --- 로깅 설정 ---
logger = logging.getLogger(__name__)

# --- (신규) 카드 게임 핵심 로직 ---
class Card:
    """단일 카드 객체. 슈트(suit), 랭크(rank), 바카라/블랙잭 값을 가집니다."""
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
        self.baccarat_value = self._get_baccarat_value()
        self.blackjack_value = self._get_blackjack_value()

    def _get_baccarat_value(self):
        if self.rank in ['K', 'Q', 'J', '10']:
            return 0
        elif self.rank == 'A':
            return 1
        else:
            return int(self.rank)

    def _get_blackjack_value(self):
        if self.rank in ['K', 'Q', 'J']:
            return 10
        elif self.rank == 'A':
            return 11
        else:
            return int(self.rank)

    def __str__(self):
        suit_emoji = {
            'Spades': '♠️', 'Hearts': '♥️', 'Diamonds': '♦️', 'Clubs': '♣️'
        }
        return f"[{suit_emoji[self.suit]} {self.rank}]"

class Deck:
    """게임 덱 객체. 덱 생성, 셔플, 카드 분배를 담당합니다."""
    def __init__(self, num_decks=6):
        self.cards = []
        self.suits = ['Spades', 'Hearts', 'Diamonds', 'Clubs']
        self.ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'K', 'Q', 'J']
        for _ in range(num_decks):
            for suit in self.suits:
                for rank in self.ranks:
                    self.cards.append(Card(suit, rank))
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self):
        if not self.cards:
            logger.warning("덱이 비어 카드를 다시 셔플합니다.")
            self.__init__()
        return self.cards.pop()

# --- 바카라 (싱글) 베팅 모달 ---
class BaccaratBetModal(ui.Modal, title="🎴 바카라 (싱글) 베팅"):
    bet_amount = ui.TextInput(label="베팅 금액", placeholder="최소 100원", style=discord.TextStyle.short)
    
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.eco = get_economy_cog(self.bot)

    async def on_submit(self, i: discord.Interaction):
        try:
            amount = int(self.bet_amount.value)
        except ValueError:
            return await i.response.send_message("베팅 금액은 숫자만 입력해야 합니다.", ephemeral=True)

        if amount < 100:
            return await i.response.send_message("최소 베팅 금액은 100원입니다.", ephemeral=True)
        
        if not self.eco:
            return await i.response.send_message("경제 시스템 오류가 발생했습니다.", ephemeral=True)

        user_id = i.user.id
        balance = await self.eco.get_balance(user_id)
        if balance < amount:
            return await i.response.send_message(f"잔액이 부족합니다. (현재 잔액: {balance:,}원)", ephemeral=True)

        await i.response.defer(ephemeral=True)
        view = BaccaratBetView(bot=self.bot, eco=self.eco, amount=amount, user=i.user)
        await i.followup.send("베팅할 위치를 선택하세요.", view=view, ephemeral=True)

# --- 바카라 (싱글) 베팅 위치 선택 뷰 ---
class BaccaratBetView(ui.View):
    def __init__(self, bot: commands.Bot, eco: commands.Cog, amount: int, user: discord.Member):
        super().__init__(timeout=60)
        self.bot = bot
        self.eco = eco
        self.amount = amount
        self.user = user

    async def start_game_deal(self, i: discord.Interaction, bet_choice: str):
        if not await self.eco.update_balance(self.user.id, -self.amount):
            logger.error(f"Baccarat(S) Bet Error: User {self.user.id} -{self.amount}")
            return await i.response.send_message("베팅 금액 차감 중 오류가 발생했습니다.", ephemeral=True)

        await i.response.defer()

        deck = Deck(num_decks=1) 
        player_hand = []
        banker_hand = []
        
        e = discord.Embed(title="🎴 바카라 (싱글)", description="**딜링을 시작합니다...**", color=0xAAAAAA)
        e.add_field(name="플레이어", value="[❔]", inline=True)
        e.add_field(name="뱅커", value="[❔]", inline=True)
        e.set_footer(text=f"{self.user.display_name}님이 {bet_choice}에 {self.amount:,}원 베팅")
        
        msg = await i.followup.send(embed=e, ephemeral=False, wait=True)

        try:
            await asyncio.sleep(2)

            player_hand.append(deck.deal())
            e.description = "플레이어 첫 번째 카드..."
            e.set_field_at(0, name="플레이어", value=f"{str(player_hand[0])}", inline=True)
            await msg.edit(embed=e)
            await asyncio.sleep(2)

            banker_hand.append(deck.deal())
            e.description = "뱅커 첫 번째 카드..."
            e.set_field_at(1, name="뱅커", value=f"{str(banker_hand[0])}", inline=True)
            await msg.edit(embed=e)
            await asyncio.sleep(2)

            player_hand.append(deck.deal())
            player_score = sum(c.baccarat_value for c in player_hand) % 10
            e.description = "플레이어 두 번째 카드..."
            e.set_field_at(0, name=f"플레이어 (합: {player_score})", value=f"{str(player_hand[0])} {str(player_hand[1])}", inline=True)
            await msg.edit(embed=e)
            await asyncio.sleep(2)

            banker_hand.append(deck.deal())
            banker_score = sum(c.baccarat_value for c in banker_hand) % 10
            e.description = "뱅커 두 번째 카드..."
            e.set_field_at(1, name=f"뱅커 (합: {banker_score})", value=f"{str(banker_hand[0])} {str(banker_hand[1])}", inline=True)
            await msg.edit(embed=e)
            await asyncio.sleep(2)
            
            player_third_card = None
            banker_third_card = None
            
            if player_score >= 8 or banker_score >= 8:
                e.description = "--- 🃏 내추럴 8/9! 게임 종료 🃏 ---"
                await msg.edit(embed=e)
                await asyncio.sleep(2)
            else:
                if player_score <= 5:
                    player_third_card = deck.deal()
                    player_hand.append(player_third_card)
                    player_score = sum(c.baccarat_value for c in player_hand) % 10
                    e.description = "플레이어 3번째 카드..."
                    e.set_field_at(0, name=f"플레이어 (합: {player_score})", value=" ".join(str(c) for c in player_hand), inline=True)
                    await msg.edit(embed=e)
                    await asyncio.sleep(2)
                else:
                    e.description = "플레이어 6/7. 스탠드."
                    await msg.edit(embed=e)
                    await asyncio.sleep(2)

                player_third_val = player_third_card.baccarat_value if player_third_card else -1

                banker_draws = False
                if banker_score <= 2: banker_draws = True
                elif banker_score == 3: banker_draws = (player_third_val != 8)
                elif banker_score == 4: banker_draws = (player_third_val in [2,3,4,5,6,7])
                elif banker_score == 5: banker_draws = (player_third_val in [4,5,6,7])
                elif banker_score == 6: banker_draws = (player_third_val in [6,7])

                if (player_score == 6 or player_score == 7) and len(player_hand) == 2:
                    if banker_score <=5:
                        banker_draws = True

                if not banker_draws and player_third_card:
                    e.description = "뱅커 스탠드."
                    await msg.edit(embed=e)
                    await asyncio.sleep(2)
                    
                if banker_draws:
                    banker_third_card = deck.deal()
                    banker_hand.append(banker_third_card)
                    banker_score = sum(c.baccarat_value for c in banker_hand) % 10
                    e.description = "뱅커 3번째 카드..."
                    e.set_field_at(1, name=f"뱅커 (합: {banker_score})", value=" ".join(str(c) for c in banker_hand), inline=True)
                    await msg.edit(embed=e)
                    await asyncio.sleep(2)
                elif not player_third_card:
                    e.description = "뱅커 스탠드."
                    await msg.edit(embed=e)
                    await asyncio.sleep(2)

            winner = ""
            payout = 0
            payout_mult = 0
            color = 0xAAAAAA

            if player_score > banker_score:
                winner = "player"
                payout_mult = 2.0 
                color = 0x0000FF 
            elif banker_score > player_score:
                winner = "banker"
                payout_mult = 1.95 
                color = 0xFF0000 
            else:
                winner = "tie"
                payout_mult = 9.0 
                color = 0x00FF00 

            e.title = "🎴 바카라 (싱글) 결과"
            e.color = color

            if bet_choice == winner:
                payout = int(self.amount * payout_mult)
                await self.eco.update_balance(self.user.id, payout)
                e.description = f"**🎉 {self.user.mention}님 승리!**\n{bet_choice.upper()}에 베팅하여 **{payout:,}원**을 획득했습니다!"
            else:
                payout = 0
                e.description = f"**😥 {self.user.mention}님 패배...**\n{bet_choice.upper()}에 베팅. 결과: **{winner.upper()}**.\n**{self.amount:,}원**을 잃었습니다."
            
            e.set_footer(text=f"베팅: {self.amount:,}원 ({bet_choice}) | 획득: {payout:,}원")
            await msg.edit(embed=e)

            await asyncio.sleep(10)
            await msg.delete()

        except Exception as e:
            logger.error(f"싱글 바카라 게임 중 오류: {e}", exc_info=True)
            try:
                await msg.edit(content=f"게임 중 오류가 발생했습니다: {e}", embed=None, view=None)
                await self.eco.update_balance(self.user.id, self.amount)
                await msg.delete(delay=10)
            except:
                pass

    @ui.button(label="플레이어", style=discord.ButtonStyle.primary, emoji="🇵")
    async def bet_player(self, i: discord.Interaction, button: ui.Button):
        await self.start_game_deal(i, "player")

    @ui.button(label="뱅커", style=discord.ButtonStyle.danger, emoji="🇧")
    async def bet_banker(self, i: discord.Interaction, button: ui.Button):
        await self.start_game_deal(i, "banker")

    @ui.button(label="타이", style=discord.ButtonStyle.success, emoji="🇹")
    async def bet_tie(self, i: discord.Interaction, button: ui.Button):
        await self.start_game_deal(i, "tie")


# --- 블랙잭 (싱글) 베팅 모달 ---
class BlackjackBetModal(ui.Modal, title="♠️ 블랙잭 베팅"):
    bet_amount = ui.TextInput(label="베팅 금액", placeholder="최소 100원", style=discord.TextStyle.short)

    def __init__(self, bot: commands.Bot, cog: commands.Cog):
        super().__init__()
        self.bot = bot
        self.eco = get_economy_cog(self.bot)
        self.cog = cog 

    async def on_submit(self, i: discord.Interaction):
        try:
            amount = int(self.bet_amount.value)
        except ValueError:
            return await i.response.send_message("숫자만 입력.", ephemeral=True)
        if amount < 100:
            return await i.response.send_message("최소 100원.", ephemeral=True)
        
        if not self.eco:
            return await i.response.send_message("경제 시스템 오류.", ephemeral=True)
        if not self.cog:
            return await i.response.send_message("게임 시스템 오류.", ephemeral=True)

        user_id = i.user.id
        balance = await self.eco.get_balance(user_id)
        if balance < amount:
            return await i.response.send_message(f"잔액이 부족합니다. (현재 잔액: {balance:,}원)", ephemeral=True)
        
        if not await self.eco.update_balance(user_id, -amount):
            logger.error(f"Blackjack Bet Error: User {user_id} -{amount}")
            return await i.response.send_message("베팅 금액 차감 중 오류가 발생했습니다.", ephemeral=True)

        # 개인에게만 메시지(ephemeral=True)로 보이도록 수정, 동시 게임 가능
        await i.response.defer(ephemeral=True) 
        game_view = BlackjackGameView(i.user, amount, self.bot, self.cog)
        await game_view.start_game(i)

# --- 블랙잭 (싱글) 게임 뷰 ---
class BlackjackGameView(ui.View):
    def __init__(self, user: discord.Member, bet: int, bot: commands.Bot, cog):
        super().__init__(timeout=180.0) 
        self.user = user
        self.bet = bet
        self.bot = bot
        self.cog = cog
        self.eco = get_economy_cog(bot)
        
        self.deck = Deck()
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
        self.msg: discord.Message = None

    async def start_game(self, i: discord.Interaction):
        e = self._create_embed("♠️ 블랙잭", "딜링을 시작합니다...", 0x0000FF)
        
        # 개인 메시지로 진행
        msg = await i.followup.send(embed=e, view=self, wait=True, ephemeral=True)
        self.msg = msg

        try:
            await asyncio.sleep(1.5)
            self.player_hand.append(self.deck.deal())
            e = self._create_embed("♠️ 블랙잭", "플레이어 1번째 카드", 0x0000FF)
            await self.msg.edit(embed=e, view=self)
            
            await asyncio.sleep(1.5)
            self.dealer_hand.append(self.deck.deal())
            e = self._create_embed("♠️ 블랙잭", "딜러 1번째 카드", 0x0000FF)
            await self.msg.edit(embed=e, view=self)

            await asyncio.sleep(1.5)
            self.player_hand.append(self.deck.deal())
            e = self._create_embed("♠️ 블랙잭", "플레이어 2번째 카드", 0x0000FF)
            await self.msg.edit(embed=e, view=self)

            await asyncio.sleep(1.5)
            self.dealer_hand.append(self.deck.deal())
            e = self._create_embed("♠️ 블랙잭", "Hit 또는 Stay를 선택하세요.", 0x0000FF)
            
            player_score = self._calculate_score(self.player_hand)
            dealer_score = self._calculate_score(self.dealer_hand)
            
            for item in self.children:
                if isinstance(item, ui.Button): item.disabled = False
            await self.msg.edit(embed=e, view=self)
            
            if player_score == 21:
                if dealer_score == 21:
                    await self._end_game(i, "push", "무승부 (양측 블랙잭!)", 1.0)
                else:
                    await self._end_game(i, "blackjack", " 블랙잭!", 2.5) 
            elif dealer_score == 21:
                await self._end_game(i, "loss", " 딜러 블랙잭!", 0.0)

        except Exception as e:
            logger.error(f"블랙잭 시작 중 오류: {e}", exc_info=True)
            await self._cleanup_game(f"게임 시작 중 오류 발생: {e}", refund=True)

    def _calculate_score(self, hand: list[Card]) -> int:
        score = sum(c.blackjack_value for c in hand)
        num_aces = sum(1 for c in hand if c.rank == 'A')
        
        while score > 21 and num_aces > 0:
            score -= 10
            num_aces -= 1
        return score

    def _format_hand(self, hand: list[Card], show_all=True) -> str:
        if not hand: 
            return "[❔]"
        if not show_all: 
            return f"{str(hand[0])} [❔]"
        return " ".join(str(c) for c in hand)

    def _create_embed(self, title: str, description: str, color: int) -> discord.Embed:
        e = discord.Embed(title=title, description=description, color=color)
        
        player_score = self._calculate_score(self.player_hand)
        
        show_dealer = self.game_over
        dealer_score_str = "?"
        if len(self.dealer_hand) == 1:
            dealer_score_str = "?"
            show_dealer = True
        elif show_dealer:
            dealer_score_str = str(self._calculate_score(self.dealer_hand))
        
        e.add_field(name=f"딜러의 패 (합: {dealer_score_str})", 
                    value=self._format_hand(self.dealer_hand, show_all=show_dealer), 
                    inline=False)
        e.add_field(name=f"{self.user.display_name}의 패 (합: {player_score})", 
                    value=self._format_hand(self.player_hand, show_all=True), 
                    inline=False)
        e.set_footer(text=f"베팅 금액: {self.bet:,}원")
        return e

    async def _update_message(self, i: discord.Interaction, title: str, description: str, color: int):
        e = self._create_embed(title, description, color)
        await i.response.edit_message(embed=e, view=self)

    async def _cleanup_game(self, description: str, refund: bool = False):
        self.game_over = True
        self.stop()
        
        if refund and self.eco:
            await self.eco.update_balance(self.user.id, self.bet)
            description += f"\n베팅금 {self.bet:,}원이 환 환불되었습니다."

        if self.msg:
            try:
                e = discord.Embed(title="♠️ 블랙잭 종료", description=description, color=0xAAAAAA)
                for item in self.children:
                    if isinstance(item, ui.Button): item.disabled = True
                await self.msg.edit(embed=e, view=self)
                
                await asyncio.sleep(10)
                await self.msg.delete()
            except discord.HTTPException as e:
                logger.warning(f"블랙잭 정리 메시지 수정/삭제 실패: {e}")
            self.msg = None

    async def _end_game(self, i: discord.Interaction, result: str, title: str, payout_mult: float):
        self.game_over = True
        self.stop() 

        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

        payout = 0
        description = ""
        color = 0xAAAAAA

        if result == "win" or result == "blackjack":
            payout = int(self.bet * payout_mult)
            description = f"승리! **{payout:,}원**을 획득했습니다."
            color = 0x00FF00
        elif result == "loss" or result == "bust":
            description = f"패배. 베팅금 **{self.bet:,}원**을 잃었습니다."
            color = 0xFF0000
        elif result == "push":
            payout = self.bet 
            description = "무승부. 베팅금을 돌려받습니다."
            color = 0xAAAAAA
            
        if payout > 0 and self.eco:
            if not await self.eco.update_balance(self.user.id, payout):
                logger.error(f"Blackjack Payout Error: User {self.user.id} +{payout}")
                description += "\n(오류: 상금 지급에 실패했습니다.)"
        
        e = self._create_embed(title, description, color)
        
        try:
            if i.response.is_done():
                await i.followup.edit_message(message_id=self.msg.id, embed=e, view=self)
            else:
                await i.response.edit_message(embed=e, view=self)
        except discord.HTTPException as e:
            logger.error(f"Blackjack end_game edit error: {e}")

        await self._cleanup_game(description, refund=False)

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.user.id:
            await i.response.send_message("게임에 참여한 유저만 버튼을 누를 수 있습니다.", ephemeral=True)
            return False
        if self.game_over:
            await i.response.send_message("이미 종료된 게임입니다.", ephemeral=True)
            return False
        
        is_any_button_enabled = any(not item.disabled for item in self.children if isinstance(item, ui.Button))
        if not is_any_button_enabled:
            await i.response.send_message("딜링 중입니다. 잠시만 기다려주세요.", ephemeral=True)
            return False
            
        return True

    @ui.button(label="Hit", style=discord.ButtonStyle.success, custom_id="bj_hit", disabled=True)
    async def hit_button(self, i: discord.Interaction, button: ui.Button):
        self.player_hand.append(self.deck.deal())
        player_score = self._calculate_score(self.player_hand)

        if player_score > 21:
            await self._end_game(i, "bust", "💥 BUST!", 0.0)
        elif player_score == 21:
            stay_button_obj = discord.utils.get(self.children, custom_id="bj_stay")
            if stay_button_obj:
                await stay_button_obj.callback(i)
            else:
                logger.error("Stay 버튼을 찾을 수 없습니다 (bj_stay).")
        else:
            await self._update_message(i, "♠️ 블랙잭", "Hit 또는 Stay를 선택하세요.", 0x0000FF)

    @ui.button(label="Stay", style=discord.ButtonStyle.danger, custom_id="bj_stay", disabled=True)
    async def stay_button(self, i: discord.Interaction, button: ui.Button):
        player_score = self._calculate_score(self.player_hand)
        dealer_score = self._calculate_score(self.dealer_hand)
        
        self.game_over = True 
        for item in self.children:
            if isinstance(item, ui.Button): item.disabled = True
            
        e = self._create_embed("♠️ 블랙잭", "딜러의 턴입니다...", 0xAAAAAA)
        
        if i.response.is_done():
            await i.edit_original_response(embed=e, view=self)
        else:
            await i.response.edit_message(embed=e, view=self)

        while dealer_score < 17:
            await asyncio.sleep(2)
            self.dealer_hand.append(self.deck.deal())
            dealer_score = self._calculate_score(self.dealer_hand)
            
            e = self._create_embed("♠️ 블랙잭", "딜러가 카드를 뽑습니다...", 0xAAAAAA)
            await i.edit_original_response(embed=e, view=self)

        await asyncio.sleep(1) 

        if dealer_score > 21:
            await self._end_game(i, "win", "🎉 딜러 BUST!", 2.0)
        elif dealer_score > player_score:
            await self._end_game(i, "loss", "😥 딜러 승리", 0.0)
        elif player_score > dealer_score:
            await self._end_game(i, "win", "🎉 플레이어 승리!", 2.0)
        else:
            await self._end_game(i, "push", "무승부 (Push)", 1.0)

    async def on_timeout(self):
        await self._cleanup_game(f"시간이 초과되어 베팅금 ({self.bet:,}원)을 잃었습니다.", refund=False)
        logger.info(f"Blackjack game timeout for {self.user.id}")

# --- 바카라 (멀티) 베팅 모달 ---
class BaccaratMultiBetModal(ui.Modal, title="🎩 멀티 바카라 베팅"):
    bet_amount = ui.TextInput(label="베팅 금액", placeholder="최소 100원", style=discord.TextStyle.short)

    def __init__(self, bet_type: str, bot: commands.Bot, cog: commands.Cog, eco: commands.Cog):
        super().__init__()
        self.bet_type = bet_type
        self.bet_type_kor = {"player": "플레이어", "banker": "뱅커", "tie": "타이"}[bet_type]
        self.bot = bot
        self.cog = cog
        self.eco = eco
        self.title = f"🎩 {self.bet_type_kor}에 베팅"

    async def on_submit(self, i: discord.Interaction):
        if not self.cog.baccarat_game_loop.is_running() or self.cog.multi_baccarat_phase != "betting":
             return await i.response.send_message("지금은 베팅 시간이 아닙니다.", ephemeral=True)

        try:
            amount = int(self.bet_amount.value)
        except ValueError:
            return await i.response.send_message("숫자만 입력.", ephemeral=True)
        if amount < 100:
            return await i.response.send_message("최소 100원.", ephemeral=True)
        
        if not self.eco:
            return await i.response.send_message("경제 시스템 오류.", ephemeral=True)

        user_id = i.user.id
        balance = await self.eco.get_balance(user_id)
        
        current_bet_amount = 0
        if user_id in self.cog.multi_baccarat_bets:
            _, current_bet_amount = self.cog.multi_baccarat_bets[user_id]
        
        if balance < amount + current_bet_amount:
            return await i.response.send_message(f"잔액이 부족합니다.\n(현재 베팅: {current_bet_amount:,}원 / 추가 베팅: {amount:,}원 / 잔액: {balance:,}원)", ephemeral=True)

        if user_id in self.cog.multi_baccarat_bets:
            old_bet_type, old_amount = self.cog.multi_baccarat_bets.pop(user_id)
            if not await self.eco.update_balance(user_id, old_amount): 
                 logger.error(f"Multi Baccarat Refund Error: User {user_id} +{old_amount}")
                 return await i.response.send_message("기존 베팅 환불 중 오류가 발생했습니다.", ephemeral=True)

        if not await self.eco.update_balance(user_id, -amount):
            logger.error(f"Multi Baccarat Bet Error: User {user_id} -{amount}")
            return await i.response.send_message("베팅 금액 차감 중 오류가 발생했습니다.", ephemeral=True)
            
        self.cog.multi_baccarat_bets[user_id] = (self.bet_type, amount)
        await i.response.send_message(f"✅ [{self.bet_type_kor}]에 **{amount:,}원** 베팅 완료!", ephemeral=True)

# --- 바카라 (멀티) 영구 뷰 ---
class BaccaratMultiView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def send_bet_modal(self, i: discord.Interaction, bet_type: str):
        bot = i.client
        cog = bot.get_cog("GameCog")
        eco = bot.get_cog("EconomyCog")

        if not cog or not eco:
            return await i.response.send_message("시스템 오류 (Cogs not found).", ephemeral=True)

        if not cog.baccarat_game_loop.is_running() or cog.multi_baccarat_phase != "betting":
             return await i.response.send_message("지금은 베팅 시간이 아닙니다.", ephemeral=True)
        
        await i.response.send_modal(BaccaratMultiBetModal(bet_type, bot, cog, eco))

    @ui.button(label="플레이어 베팅", style=discord.ButtonStyle.primary, custom_id="multi_bacc_player", emoji="🇵")
    async def bet_player(self, i: discord.Interaction, button: ui.Button):
        await self.send_bet_modal(i, "player")

    @ui.button(label="뱅커 베팅", style=discord.ButtonStyle.danger, custom_id="multi_bacc_banker", emoji="🇧")
    async def bet_banker(self, i: discord.Interaction, button: ui.Button):
        await self.send_bet_modal(i, "banker")

    @ui.button(label="타이 베팅", style=discord.ButtonStyle.success, custom_id="multi_bacc_tie", emoji="🇹")
    async def bet_tie(self, i: discord.Interaction, button: ui.Button):
        await self.send_bet_modal(i, "tie")

# --- 메인 게임 패널 ---
class GameSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    async def start_game_interaction(self, i: discord.Interaction, game_type: str):
        bot = i.client 
        cog = bot.get_cog("GameCog")
        
        if not cog:
            await i.response.send_message("게임 시스템 오류 (Cog not found).", ephemeral=True)
            return False

        # baccarat_single만 채널 중복 진행 여부를 검사
        if game_type in ["baccarat_single"]:
            if i.channel_id in bot.active_games:
                existing_msg_id = bot.active_games.get(i.channel_id)
                if existing_msg_id:
                    try:
                        await i.channel.fetch_message(existing_msg_id)
                        logger.info(f"게임 시작 시도 차단됨 (채널 {i.channel_id}에 이미 게임 진행 중)")
                        await i.response.send_message("이 채널에서 이미 다른 게임이 진행 중입니다.", ephemeral=True)
                        return False 
                    except discord.NotFound:
                        logger.info(f"기존 게임 메시지(ID: {existing_msg_id}) 없음. 채널 {i.channel_id} 정리.")
                        await cog.end_game(i.channel_id, existing_msg_id)
                    except discord.HTTPException as e:
                        logger.warning(f"게임 상태 확인 오류 (fetch): {e}")
                        await i.response.send_message("게임 상태 확인 중 오류가 발생했습니다.", ephemeral=True)
                        return False
        
        modal_map = {
            "blackjack": BlackjackBetModal(bot, cog),
            "baccarat_single": BaccaratBetModal(bot)
        }
        
        if game_type in modal_map:
            await i.response.send_modal(modal_map[game_type])
            return True
        else:
            logger.error(f"알 수 없는 게임 타입 요청: {game_type}")
            await i.response.send_message("알 수 없는 게임입니다.", ephemeral=True)
            return False

    @discord.ui.button(label="♠️ 블랙잭 (싱글)", style=discord.ButtonStyle.primary, custom_id="start_blackjack_persistent")
    async def start_blackjack(self, i: discord.Interaction, btn: discord.ui.Button):
        await self.start_game_interaction(i, "blackjack")
        
    @discord.ui.button(label="🎴 바카라 (싱글)", style=discord.ButtonStyle.secondary, custom_id="start_baccarat_single_persistent")
    async def start_baccarat_single(self, i: discord.Interaction, btn: discord.ui.Button):
        await self.start_game_interaction(i, "baccarat_single")
        
    @discord.ui.button(label="✨ 뽑기", style=discord.ButtonStyle.success, custom_id="gacha_start_persistent")
    async def start_gacha(self, i: discord.Interaction, btn: discord.ui.Button):
        bot = i.client
        eco = get_economy_cog(bot)
        game = bot.get_cog("GameCog")
        
        await i.response.defer(ephemeral=True)

        if not eco or not game:
            logger.error("뽑기 실패: 필수 Cog 없음")
            return await i.followup.send("필수 시스템 오류.", ephemeral=True)
        
        conn=get_db_connection()
        cost = 1000
        if conn:
            try:
                setting=conn.execute("SELECT cost FROM gacha_settings WHERE guild_id=?",(i.guild_id,)).fetchone()
                cost=setting['cost'] if setting else 1000
            except sqlite3.Error as e:
                logger.error(f"뽑기 비용 조회 DB 오류: {e}")
                return await i.followup.send("뽑기 설정 로드 오류.", ephemeral=True)
            finally:
                conn.close()
        else:
            return await i.followup.send("DB 연결 오류.", ephemeral=True)
            
        bal = await eco.get_balance(i.user.id)
        if bal < cost:
            return await i.followup.send(f"잔액 부족 ({cost:,}원 필요, 현재: {bal:,}원).", ephemeral=True)
        
        if not await eco.update_balance(i.user.id, -cost):
            logger.warning(f"뽑기 비용 차감 실패 (User:{i.user.id}, Cost:{cost})")
            return await i.followup.send("비용 차감 오류.", ephemeral=True)
        
        await game.run_gacha(i, cost)

# --- 헬퍼 함수 ---
def get_db_connection():
    try:
        conn = sqlite3.connect('discord_bot.db')
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn
    except sqlite3.Error as e:
        logger.error(f"DB 연결 오류: {e}")
        return None

def get_economy_cog(bot):
    cog = bot.get_cog("EconomyCog")
    if cog is None:
        logger.error("EconomyCog 찾을 수 없음. Cog 로딩 순서 또는 파일 확인 필요.")
    return cog

# --- 메인 GameCog ---
class GameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, 'active_games'):
            bot.active_games = {} 
        
        self.multi_baccarat_channel_id: int = None
        self.multi_baccarat_message_id: int = None
        self.multi_baccarat_view = BaccaratMultiView()
        self.multi_baccarat_bets: dict[int, tuple[str, int]] = {} 
        self.multi_baccarat_phase: str = "waiting" 
        
        # 싱글 게임 패널 상태 변수 추가
        self.single_panel_channel_id: int = None
        self.single_panel_message_id: int = None
        
        self.load_multi_baccarat_config()
        self.load_single_panel_config() 
        
        if self.multi_baccarat_channel_id:
            self.baccarat_game_loop.start()

    def cog_unload(self):
        self.baccarat_game_loop.cancel()

    # --- 싱글 패널 DB 연동 ---
    def load_single_panel_config(self):
        conn = get_db_connection()
        if conn:
            try:
                conn.execute("CREATE TABLE IF NOT EXISTS single_panel_config (guild_id INTEGER PRIMARY KEY, channel_id INTEGER, message_id INTEGER)")
                config = conn.execute("SELECT channel_id, message_id FROM single_panel_config LIMIT 1").fetchone()
                if config:
                    self.single_panel_channel_id = config["channel_id"]
                    self.single_panel_message_id = config["message_id"]
            except sqlite3.Error as e:
                logger.error(f"싱글 패널 로드 오류: {e}")
            finally:
                conn.close()

    def save_single_panel_config(self):
        conn = get_db_connection()
        if conn:
            try:
                conn.execute("DELETE FROM single_panel_config") 
                if self.single_panel_channel_id and self.single_panel_message_id:
                    conn.execute("INSERT INTO single_panel_config (guild_id, channel_id, message_id) VALUES (?, ?, ?)", (0, self.single_panel_channel_id, self.single_panel_message_id))
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"싱글 패널 저장 오류: {e}")
            finally:
                conn.close()

    def load_multi_baccarat_config(self):
        conn = get_db_connection()
        if conn:
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS multi_baccarat_config (
                        guild_id INTEGER PRIMARY KEY,
                        channel_id INTEGER,
                        message_id INTEGER
                    )
                """)
                config = conn.execute("SELECT channel_id, message_id FROM multi_baccarat_config LIMIT 1").fetchone()
                if config:
                    self.multi_baccarat_channel_id = config["channel_id"]
                    self.multi_baccarat_message_id = config["message_id"]
            except sqlite3.Error as e:
                logger.error(f"멀티 바카라 설정 로드 DB 오류: {e}")
            finally:
                conn.close()

    def save_multi_baccarat_config(self):
        conn = get_db_connection()
        if conn:
            try:
                conn.execute("DELETE FROM multi_baccarat_config") 
                if self.multi_baccarat_channel_id and self.multi_baccarat_message_id:
                    conn.execute("INSERT INTO multi_baccarat_config (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
                                 (0, self.multi_baccarat_channel_id, self.multi_baccarat_message_id))
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"멀티 바카라 설정 저장 DB 오류: {e}")
            finally:
                conn.close()
    
    # --- 멀티 바카라 게임 루프 ---
    @tasks.loop(seconds=1.0) 
    async def baccarat_game_loop(self):
        await self.bot.wait_until_ready()

        if not self.multi_baccarat_channel_id or not self.multi_baccarat_message_id:
            self.baccarat_game_loop.cancel()
            return
            
        eco = get_economy_cog(self.bot)
        if not eco:
            await asyncio.sleep(10)
            return

        try:
            channel = await self.bot.fetch_channel(self.multi_baccarat_channel_id)
            msg = await channel.fetch_message(self.multi_baccarat_message_id)
        except Exception as e:
            self.multi_baccarat_channel_id = None
            self.multi_baccarat_message_id = None
            self.save_multi_baccarat_config()
            self.baccarat_game_loop.cancel()
            return

        # 1. 베팅 페이즈
        self.multi_baccarat_phase = "betting"
        self.multi_baccarat_bets.clear()
        
        for item in self.multi_baccarat_view.children:
            if isinstance(item, ui.Button): item.disabled = False
        
        e = discord.Embed(title="🎩 멀티 바카라", description="**베팅이 15초간 진행됩니다!**", color=0x0000FF)
        e.set_footer(text="버튼을 눌러 베팅에 참여하세요.")
        await msg.edit(embed=e, view=self.multi_baccarat_view)
        await asyncio.sleep(15) 

        # 2. 딜링 페이즈
        self.multi_baccarat_phase = "dealing"
        for item in self.multi_baccarat_view.children:
            if isinstance(item, ui.Button): item.disabled = True
            
        e = discord.Embed(title="🎩 멀티 바카라", description="**베팅 마감! 딜링을 시작합니다...**", color=0xAAAAAA)
        e.add_field(name="현재 베팅 참여자", value=f"{len(self.multi_baccarat_bets)}명", inline=False)
        e.add_field(name="플레이어", value="[❔]", inline=True)
        e.add_field(name="뱅커", value="[❔]", inline=True)
        await msg.edit(embed=e, view=self.multi_baccarat_view)
        await asyncio.sleep(2) 

        deck = Deck()
        player_hand = []
        banker_hand = []
        
        player_hand.append(deck.deal())
        e.description = "플레이어 첫 번째 카드..."
        e.set_field_at(1, name="플레이어", value=f"{str(player_hand[0])}", inline=True)
        await msg.edit(embed=e)
        await asyncio.sleep(2)

        banker_hand.append(deck.deal())
        e.description = "뱅커 첫 번째 카드..."
        e.set_field_at(2, name="뱅커", value=f"{str(banker_hand[0])}", inline=True)
        await msg.edit(embed=e)
        await asyncio.sleep(2)

        player_hand.append(deck.deal())
        player_score = sum(c.baccarat_value for c in player_hand) % 10
        e.description = "플레이어 두 번째 카드..."
        e.set_field_at(1, name=f"플레이어 (합: {player_score})", value=f"{str(player_hand[0])} {str(player_hand[1])}", inline=True)
        await msg.edit(embed=e)
        await asyncio.sleep(2)

        banker_hand.append(deck.deal())
        banker_score = sum(c.baccarat_value for c in banker_hand) % 10
        e.description = "뱅커 두 번째 카드..."
        e.set_field_at(2, name=f"뱅커 (합: {banker_score})", value=f"{str(banker_hand[0])} {str(banker_hand[1])}", inline=True)
        await msg.edit(embed=e)
        await asyncio.sleep(2)

        player_third_card = None
        banker_third_card = None

        if player_score >= 8 or banker_score >= 8:
            e.description = "--- 🃏 내추럴 8/9! 게임 종료 🃏 ---"
            await msg.edit(embed=e)
            await asyncio.sleep(2)
        else:
            if player_score <= 5:
                player_third_card = deck.deal()
                player_hand.append(player_third_card)
                player_score = sum(c.baccarat_value for c in player_hand) % 10
                e.description = "플레이어 3번째 카드..."
                e.set_field_at(1, name=f"플레이어 (합: {player_score})", value=" ".join(str(c) for c in player_hand), inline=True)
                await msg.edit(embed=e)
                await asyncio.sleep(2)
            else:
                e.description = "플레이어 6/7. 스탠드."
                await msg.edit(embed=e)
                await asyncio.sleep(2)

            player_third_val = player_third_card.baccarat_value if player_third_card else -1
            banker_draws = False
            if banker_score <= 2: banker_draws = True
            elif banker_score == 3: banker_draws = (player_third_val != 8)
            elif banker_score == 4: banker_draws = (player_third_val in [2,3,4,5,6,7])
            elif banker_score == 5: banker_draws = (player_third_val in [4,5,6,7])
            elif banker_score == 6: banker_draws = (player_third_val in [6,7])
            
            if (player_score == 6 or player_score == 7) and len(player_hand) == 2:
                if banker_score <=5:
                    banker_draws = True
            
            if not banker_draws and player_third_card:
                e.description = "뱅커 스탠드."
                await msg.edit(embed=e)
                await asyncio.sleep(2)
                
            if banker_draws:
                banker_third_card = deck.deal()
                banker_hand.append(banker_third_card)
                banker_score = sum(c.baccarat_value for c in banker_hand) % 10
                e.description = "뱅커 3번째 카드..."
                e.set_field_at(2, name=f"뱅커 (합: {banker_score})", value=" ".join(str(c) for c in banker_hand), inline=True)
                await msg.edit(embed=e)
                await asyncio.sleep(2)
            elif not player_third_card:
                e.description = "뱅커 스탠드."
                await msg.edit(embed=e)
                await asyncio.sleep(2)

        winner = ""
        payout_mults = {"player": 2.0, "banker": 1.95, "tie": 9.0}
        color = 0xAAAAAA

        if player_score > banker_score: winner = "player"; color = 0x0000FF
        elif banker_score > player_score: winner = "banker"; color = 0xFF0000
        else: winner = "tie"; color = 0x00FF00
        
        e.title = "🎩 멀티 바카라 - 결과 발표"
        e.description = f"**{winner.upper()} 승리!**"
        e.color = color
        await msg.edit(embed=e)
        
        # 3. 정산 페이즈
        self.multi_baccarat_phase = "payout"
        winners_list = []
        total_payout = 0
        
        for user_id, (bet_type, amount) in self.multi_baccarat_bets.items():
            payout = 0
            if bet_type == winner:
                payout = int(amount * payout_mults[winner])
                if await eco.update_balance(user_id, payout):
                    user = self.bot.get_user(user_id)
                    display_name = user.display_name if user else f"유저({user_id})"
                    winners_list.append(f"**{display_name}**: +{payout:,}원 (베팅: {amount:,}원)")
                    total_payout += payout

        e.add_field(name=f"🏆 승자 목록 (총 획득: {total_payout:,}원)",
                    value="\n".join(winners_list) if winners_list else "없음",
                    inline=False)
        e.set_footer(text="10초 후 정산, 5초 후 다음 게임을 시작합니다.")
        await msg.edit(embed=e, view=self.multi_baccarat_view)
        await asyncio.sleep(10) 

        # 4. 대기 페이즈
        self.multi_baccarat_phase = "waiting"
        await asyncio.sleep(5) 

    async def end_game(self, cid: int, mid: int):
        if cid in self.bot.active_games and self.bot.active_games.get(cid) == mid:
            try:
                del self.bot.active_games[cid]
            except KeyError:
                pass
            
    async def run_gacha(self, i: discord.Interaction, cost: int):
        u=i.user; g=i.guild
        win=random.randint(1,100)<=5; 
        
        if win:
            conn=get_db_connection(); roles_d=[];
            if conn:
                try: roles_d=conn.execute("SELECT role_id FROM gacha_roles WHERE guild_id=?",(g.id,)).fetchall()
                except sqlite3.Error as e: logger.error(f"Gacha role fetch DB Error: {e}"); return await i.followup.send("DB 오류.", ephemeral=True)
                finally: conn.close()
            else: return await i.followup.send("DB 연결 오류.", ephemeral=True)
            
            if not roles_d:
                await i.followup.send(f"🎉 당첨! 근데 상품 역할 없음! 비용({cost:,}원) 환불.",ephemeral=True)
                eco=get_economy_cog(self.bot);
                if eco: await eco.update_balance(u.id, cost)
                return
                
            u_roles={r.id for r in u.roles}
            avail=[g.get_role(r['role_id']) for r in roles_d if r['role_id'] not in u_roles]
            avail=[r for r in avail if r]; 
            
            if not avail:
                await i.followup.send(f"🎉 당첨! 근데 받을 수 있는 역할 없음! 비용({cost:,}원) 환불.",ephemeral=True)
                eco=get_economy_cog(self.bot)
                if eco: await eco.update_balance(u.id, cost)
                return
                
            chosen=random.choice(avail);
            try:
                await u.add_roles(chosen, reason="뽑기 당첨")
                e=discord.Embed(title="🎊 뽑기 대성공!", description=f"희귀 역할 **{chosen.mention}** 획득!", color=0xffd700)
                e.set_thumbnail(url="https://i.imgur.com/5lQfF0C.gif") 
                await i.followup.send(embed=e, ephemeral=False) 
            except discord.Forbidden:
                await i.followup.send(f"🎉 당첨! 근데 역할 지급 권한 없음.", ephemeral=True)
            except Exception as e:
                await i.followup.send(f"🎉 당첨! 근데 역할 지급 오류.", ephemeral=True)
        else:
            e=discord.Embed(title="꽝!", description="다음 기회에... 💨", color=0x555555)
            await i.followup.send(embed=e, ephemeral=True)

    # --- 싱글 게임설치 ---
    @app_commands.command(name="게임설치", description="싱글플레이 게임/뽑기 시작 버튼 영구 메시지 설치.")
    @app_commands.checks.has_permissions(administrator=True)
    async def install_game_panel(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        
        # 기존 패널이 있다면 삭제 시도
        if self.single_panel_channel_id and self.single_panel_message_id:
            try:
                old_channel = await self.bot.fetch_channel(self.single_panel_channel_id)
                old_msg = await old_channel.fetch_message(self.single_panel_message_id)
                await old_msg.delete()
            except:
                pass

        e = discord.Embed(title="🎲 싱글플레이 게임 센터", description="아래 버튼을 눌러 게임을 시작하세요!", color=0x9b59b6)
        msg = await i.channel.send(embed=e, view=GameSetupView())
        
        # 새 패널 정보 저장
        self.single_panel_channel_id = i.channel.id
        self.single_panel_message_id = msg.id
        self.save_single_panel_config()
        
        await i.followup.send("✅ 게임 패널이 설치되었습니다. 해당 채널에 채팅이 올라오면 메뉴가 자동으로 맨 아래로 이동합니다.", ephemeral=True)

    @install_game_panel.error
    async def install_err(self, i: discord.Interaction, err: app_commands.AppCommandError):
        if isinstance(err, app_commands.MissingPermissions): await i.response.send_message("관리자만 사용 가능.", ephemeral=True)
        else: logger.error(f"Install Panel Error: {err}"); await i.response.send_message(f"패널 설치 오류.", ephemeral=True)

    # --- 채팅 발생 시 게임 패널 및 멀티 바카라 최하단 이동 ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: 
            return 
            
        # 1. 싱글플레이 패널 끌어올림 로직
        if self.single_panel_channel_id and message.channel.id == self.single_panel_channel_id:
            if self.single_panel_message_id:
                try:
                    old_msg = await message.channel.fetch_message(self.single_panel_message_id)
                    await old_msg.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logger.warning(f"싱글 패널 삭제 실패: {e}")
            
            e = discord.Embed(title="🎲 싱글플레이 게임 센터", description="아래 버튼을 눌러 게임을 시작하세요!", color=0x9b59b6)
            new_msg = await message.channel.send(embed=e, view=GameSetupView())
            
            self.single_panel_message_id = new_msg.id
            self.save_single_panel_config()

        # 2. 멀티 바카라 패널 끌어올림 로직 (대기 시간일 때만 작동)
        if self.multi_baccarat_channel_id and message.channel.id == self.multi_baccarat_channel_id:
            # 게임이 진행 중이 아닐 때(waiting)만 끌어올림 허용하여 오류 방지
            if getattr(self, 'multi_baccarat_phase', 'waiting') == "waiting":
                if self.multi_baccarat_message_id:
                    try:
                        old_msg = await message.channel.fetch_message(self.multi_baccarat_message_id)
                        await old_msg.delete()
                    except discord.NotFound:
                        pass
                    except Exception as e:
                        logger.warning(f"멀티 바카라 패널 삭제 실패: {e}")
                
                e = discord.Embed(title="🎩 멀티 바카라 테이블", description="다음 라운드를 준비 중입니다...", color=0xAAAAAA)
                new_msg = await message.channel.send(embed=e, view=self.multi_baccarat_view)
                
                self.multi_baccarat_message_id = new_msg.id
                self.save_multi_baccarat_config()

    # --- [수정됨] 알로항 주사위 명령어 (2개의 주사위를 번갈아가며 공개) ---
    @app_commands.command(name="주사위", description="토사장 공 주사위 게임. 배팅한 금액을 걸고 승부합니다.")
    async def dice_alohang(self, i: discord.Interaction, bet: int):
        eco = get_economy_cog(self.bot)
        if not eco:
            return await i.response.send_message("경제 시스템 오류.", ephemeral=True)
        if bet < 100:
            return await i.response.send_message("최소 배팅 금액은 100원입니다.", ephemeral=True)
            
        balance = await eco.get_balance(i.user.id)
        if balance < bet:
            return await i.response.send_message(f"잔액이 부족합니다. (현재: {balance:,}원)", ephemeral=True)
            
        if not await eco.update_balance(i.user.id, -bet):
            return await i.response.send_message("베팅 금액 차감 중 오류가 발생했습니다.", ephemeral=True)

        # 주사위 4개 (봇 2개, 유저 2개) 미리 굴림
        bot_dice1 = random.randint(1, 6)
        user_dice1 = random.randint(1, 6)
        bot_dice2 = random.randint(1, 6)
        user_dice2 = random.randint(1, 6)

        bot_total = bot_dice1 + bot_dice2
        user_total = user_dice1 + user_dice2

        # 1. 초기 메시지: 봇 1차 주사위만 공개
        embed = discord.Embed(title="🎲 토사장 공 주사위", description="**긴장되는 순간... 주사위를 굴립니다!** 땀뻘뻘;;", color=0xAAAAAA)
        embed.add_field(name="🤖 봇의 주사위", value=f"1차: 🎲 **{bot_dice1}**\n2차: 🎲 **?**\n합계: **?**", inline=True)
        embed.add_field(name=f"👤 {i.user.display_name}의 주사위", value=f"1차: 🎲 **?**\n2차: 🎲 **?**\n합계: **?**", inline=True)
        
        await i.response.send_message(embed=embed)
        
        # 2. 유저 1차 주사위 공개
        await asyncio.sleep(2.0)
        embed.set_field_at(1, name=f"👤 {i.user.display_name}의 주사위", value=f"1차: 🎲 **{user_dice1}**\n2차: 🎲 **?**\n합계: **?**", inline=True)
        await i.edit_original_response(embed=embed)

        # 3. 봇 2차 주사위 공개
        await asyncio.sleep(2.0)
        embed.set_field_at(0, name="🤖 봇의 주사위", value=f"1차: 🎲 **{bot_dice1}**\n2차: 🎲 **{bot_dice2}**\n합계: **{bot_total}**", inline=True)
        await i.edit_original_response(embed=embed)

        # 4. 유저 2차 주사위 공개 및 결과 발표
        await asyncio.sleep(2.0)
        embed.set_field_at(1, name=f"👤 {i.user.display_name}의 주사위", value=f"1차: 🎲 **{user_dice1}**\n2차: 🎲 **{user_dice2}**\n합계: **{user_total}**", inline=True)

        if user_total > bot_total:
            await eco.update_balance(i.user.id, bet * 2)
            embed.description = f"🎉 **승리!** 주사위 합이 더 높습니다!\n**{bet * 2:,}원**을 획득했습니다!"
            embed.color = 0x00FF00
        elif user_total < bot_total:
            embed.description = f"😥 **패배...** 주사위 합이 낮습니다.\n**{bet:,}원**을 잃었습니다."
            embed.color = 0xFF0000
        else:
            await eco.update_balance(i.user.id, bet)
            embed.description = "🤝 **무승부!** 합이 같습니다. 배팅금을 돌려받았습니다."
            embed.color = 0xAAAAAA

        await i.edit_original_response(embed=embed)

    @app_commands.command(name="멀티바카라-설치", description="지정한 채널에 24시간 자동 멀티 바카라 테이블을 설치합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_multi_baccarat(self, i: discord.Interaction, channel: discord.TextChannel):
        await i.response.defer(ephemeral=True)

        if self.baccarat_game_loop.is_running():
            if self.multi_baccarat_channel_id == channel.id:
                return await i.followup.send(f"멀티 바카라가 이미 {channel.mention} 채널에 설치되어 있습니다.", ephemeral=True)
            
            await i.followup.send(f"기존 <#{self.multi_baccarat_channel_id}> 채널에서 게임을 제거하고 {channel.mention}으로 이동합니다...", ephemeral=True)
            self.baccarat_game_loop.cancel() 

            try:
                old_channel = await self.bot.fetch_channel(self.multi_baccarat_channel_id)
                old_msg = await old_channel.fetch_message(self.multi_baccarat_message_id)
                await old_msg.delete()
            except Exception as e:
                logger.warning(f"기존 멀티 바카라 메시지 삭제 실패: {e}")
            
        e = discord.Embed(title="🎩 멀티 바카라 테이블", description="게임 루프가 곧 시작됩니다... (설치 중)", color=0xAAAAAA)
        
        try:
            msg = await channel.send(embed=e, view=self.multi_baccarat_view)
            for item in self.multi_baccarat_view.children:
                if isinstance(item, ui.Button): item.disabled = True
            await msg.edit(view=self.multi_baccarat_view)
            
        except discord.Forbidden:
            return await i.followup.send(f"{channel.mention} 채널에 메시지를 보낼 권한이 없습니다.", ephemeral=True)
        except Exception as e:
            logger.error(f"멀티 바카라 설치 오류: {e}")
            return await i.followup.send("테이블 설치 중 오류가 발생했습니다.", ephemeral=True)

        self.multi_baccarat_channel_id = channel.id
        self.multi_baccarat_message_id = msg.id
        self.save_multi_baccarat_config() 
        
        self.baccarat_game_loop.start()
        await i.followup.send(f"{channel.mention}에 멀티 바카라 테이블을 성공적으로 설치했습니다.", ephemeral=True)

    @app_commands.command(name="멀티바카라-제거", description="설치된 멀티 바카라 테이블을 중지하고 제거합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_multi_baccarat(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        
        if not self.baccarat_game_loop.is_running():
            return await i.followup.send("멀티 바카라가 현재 실행 중이지 않습니다.", ephemeral=True)

        self.baccarat_game_loop.cancel()

        try:
            old_channel = await self.bot.fetch_channel(self.multi_baccarat_channel_id)
            old_msg = await old_channel.fetch_message(self.multi_baccarat_message_id)
            await old_msg.delete()
        except Exception as e:
            logger.warning(f"멀티 바카라 메시지 삭제 실패: {e}")

        self.multi_baccarat_channel_id = None
        self.multi_baccarat_message_id = None
        self.save_multi_baccarat_config() 
        
        await i.followup.send("멀티 바카라 테이블을 성공적으로 제거했습니다.", ephemeral=True)

# --- Cog 로드 ---
async def setup(bot):
    cog_instance = GameCog(bot)
    await bot.add_cog(cog_instance)
    
    bot.add_view(GameSetupView())
    bot.add_view(BaccaratMultiView())