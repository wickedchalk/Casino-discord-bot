import sqlite3
import discord
import random
import math
import asyncio
import datetime
from discord import app_commands
from discord.ext import commands

# ================= CONFIGURATION =================
BOT_TOKEN = "ENTER_BOT_TOKEN"
ADMIN_ROLE_ID =  
DB_PATH = 'casino.db'
# =================================================

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
                       (user_id INTEGER PRIMARY KEY, 
                        balance REAL DEFAULT 0.0, 
                        wagered REAL DEFAULT 0.0, 
                        net_pl REAL DEFAULT 0.0)''')
        conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL)')
        conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("payout_cap", 10000.0)')
        conn.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                       (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        user_id INTEGER, 
                        game TEXT, 
                        bet REAL, 
                        profit REAL, 
                        timestamp DATETIME)''')

def get_stats(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute('SELECT balance, wagered, net_pl FROM users WHERE user_id = ?', (user_id,)).fetchone()
        return res if res else (0.0, 0.0, 0.0)

def get_global_payout_status():
    with sqlite3.connect(DB_PATH) as conn:
        total_pl = conn.execute('SELECT SUM(net_pl) FROM users').fetchone()[0] or 0.0
        cap = conn.execute('SELECT value FROM settings WHERE key = "payout_cap"').fetchone()[0]
        return total_pl, cap

def update_balance(user_id, amount):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)', (user_id,))
        conn.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))

def record_game(user_id, game_name, bet, win_amt):
    profit = win_amt - bet
    now = datetime.datetime.now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        conn.execute('UPDATE users SET wagered = wagered + ?, net_pl = net_pl + ? WHERE user_id = ?', (bet, profit, user_id))
        conn.execute('INSERT INTO audit_logs (user_id, game, bet, profit, timestamp) VALUES (?, ?, ?, ?, ?)', 
                     (user_id, game_name, bet, profit, now))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=["!", "/"], intents=intents)

    async def setup_hook(self):
        init_db()
        self.add_view(DealerRequestView()) 
        await self.tree.sync()

bot = MyBot()
bot.remove_command('help')

# ================= HELP SYSTEM =================

class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="General Commands", description="Basic bot commands", emoji="💳"),
            discord.SelectOption(label="Casino Games", description="How to play and win", emoji="🎲"),
            discord.SelectOption(label="Admin Settings", description="Staff only controls", emoji="🛡️")
        ]
        super().__init__(placeholder="Choose a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "General Commands":
            embed = discord.Embed(title="💳 General Commands", color=0x3498db)
            embed.add_field(name="`/balance`", value="View your current wallet balance.", inline=False)
            embed.add_field(name="`/tip <user> <amount>`", value="Send money to another user.", inline=False)
            embed.add_field(name="`/leaderboard`", value="Show top wagerers.", inline=False)
            embed.add_field(name="`/stats [user]`", value="View gambling statistics.", inline=False)
            embed.add_field(name="`!requestdealer`", value="Open a support ticket.", inline=False)
            embed.add_field(name="`/deposit <amount>`", value="Open a deposit ticket.", inline=False)
            embed.add_field(name="`/withdraw <amount>`", value="Open a withdrawal ticket.", inline=False)
        elif self.values[0] == "Casino Games":
            embed = discord.Embed(title="🎲 Casino Games (5% House Edge)", color=0xe74c3c)
            embed.add_field(name="`/blackjack <bet>`", value="Classic 21. Pays 1.95x.", inline=False)
            embed.add_field(name="`/mines <bet> <bombs>`", value="Uncover diamonds. Avoid bombs.", inline=False)
            embed.add_field(name="`/dragontower <bet>`", value="Climb the tower for multipliers.", inline=False)
            embed.add_field(name="`/roulette <bet> <choice>`", value="Numbers, Red, or Black.", inline=False)
            embed.add_field(name="`/slots <bet>`", value="Spin the reels for a jackpot.", inline=False)
            embed.add_field(name="`/baccarat <bet> <side>`", value="Player, Banker, or Tie.", inline=False)
            embed.add_field(name="`/coinflip <bet> <side>`", value="50/50. Pays 1.9x.", inline=False)
        elif self.values[0] == "Admin Settings":
            embed = discord.Embed(title="🛡️ Admin Controls", color=0x2ecc71)
            embed.add_field(name="`/setcap <amount>`", value="Update payout protection.", inline=True)
            embed.add_field(name="`/setbal <user> <amount>`", value="Adjust user balance.", inline=True)
            embed.add_field(name="`/close`", value="Delete a ticket channel.", inline=True)
            embed.add_field(name="`/rename <name>`", value="Rename a ticket channel.", inline=True)
            embed.add_field(name="`!resetall`", value="Wipe all data.", inline=False)
        
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(HelpSelect())

@bot.hybrid_command(name="help", description="Detailed guide to bot commands")
async def help_command(ctx):
    embed = discord.Embed(title="📚 Cheff Casino Guide", description="Select a category to view commands.", color=0x2b2d31)
    await ctx.send(embed=embed, view=HelpView())

# ================= SOCIAL/ECONOMY COMMANDS =================

@bot.hybrid_command(name="tip", description="Send money to another player")
async def tip(ctx, member: discord.Member, amount: float):
    if amount <= 0: return await ctx.send("❌ Amount must be positive.")
    if member.id == ctx.author.id: return await ctx.send("❌ You cannot tip yourself.")
    
    bal, _, _ = get_stats(ctx.author.id)
    if bal < amount: return await ctx.send("❌ Insufficient funds.")
    
    update_balance(ctx.author.id, -amount)
    update_balance(member.id, amount)
    
    embed = discord.Embed(title="💸 Tip Sent", color=0x2ecc71)
    embed.description = f"You tipped **{member.display_name}** `${amount:,.2f}`"
    await ctx.send(embed=embed)

@bot.hybrid_command(name="stats", description="View gambling statistics")
async def stats(ctx, member: discord.Member = None):
    target = member or ctx.author
    bal, wagered, pl = get_stats(target.id)
    
    with sqlite3.connect(DB_PATH) as conn:
        total_games = conn.execute('SELECT COUNT(*) FROM audit_logs WHERE user_id = ?', (target.id,)).fetchone()[0]
        biggest_win = conn.execute('SELECT MAX(profit) FROM audit_logs WHERE user_id = ?', (target.id,)).fetchone()[0] or 0.0

    embed = discord.Embed(title=f"📊 Statistics: {target.display_name}", color=0x3498db)
    embed.add_field(name="Balance", value=f"`${bal:,.2f}`", inline=True)
    embed.add_field(name="Wagered", value=f"`${wagered:,.2f}`", inline=True)
    embed.add_field(name="Net P/L", value=f"`${pl:,.2f}`", inline=True)
    embed.add_field(name="Games Played", value=f"`{total_games}`", inline=True)
    embed.add_field(name="Biggest Win", value=f"`${biggest_win:,.2f}`", inline=True)
    embed.set_thumbnail(url=target.display_avatar.url)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="leaderboard", description="View top 10 wagerers")
async def leaderboard(ctx):
    with sqlite3.connect(DB_PATH) as conn:
        top_users = conn.execute('SELECT user_id, wagered FROM users ORDER BY wagered DESC LIMIT 10').fetchall()
    
    if not top_users: return await ctx.send("The leaderboard is currently empty.")
    
    embed = discord.Embed(title="🏆 Wager Leaderboard", color=0xf1c40f)
    description = ""
    for i, (user_id, wagered) in enumerate(top_users, 1):
        user = bot.get_user(user_id)
        name = user.display_name if user else f"User {user_id}"
        description += f"**{i}. {name}** — `${wagered:,.2f}`\n"
    
    embed.description = description
    await ctx.send(embed=embed)

# ================= ADMIN COMMANDS =================

@bot.command(name="resetall")
@commands.has_role(ADMIN_ROLE_ID)
async def reset_all_data(ctx):
    await ctx.send("🚨 **WARNING:** Resetting EVERYTHING. Type `confirm` to proceed.")
    def check(m): return m.author == ctx.author and m.content.lower() == 'confirm'
    try:
        await bot.wait_for('message', check=check, timeout=15)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('DELETE FROM users')
            conn.execute('DELETE FROM audit_logs')
        await ctx.send("✅ Database cleared.")
    except asyncio.TimeoutError:
        await ctx.send("❌ Cancelled.")

@bot.hybrid_command(name="setcap")
@commands.has_role(ADMIN_ROLE_ID)
async def setcap(ctx, amount: float):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('UPDATE settings SET value = ? WHERE key = "payout_cap"', (amount,))
    await ctx.send(f"🛡️ Payout Cap: `${amount:,.2f}`")

@bot.hybrid_command(name="setbal")
@commands.has_role(ADMIN_ROLE_ID)
async def setbal(ctx, member: discord.Member, amount: float):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (member.id,))
        conn.execute('UPDATE users SET balance = ? WHERE user_id = ?', (amount, member.id))
    await ctx.send(f"✅ Updated {member.mention} balance to `${amount:,.2f}`")

@bot.hybrid_command(name="close", description="Close and delete the ticket channel")
@commands.has_role(ADMIN_ROLE_ID)
async def close_ticket(ctx):
    if any(ctx.channel.name.startswith(pre) for pre in ["deposit-", "withdraw-", "dealer-"]):
        await ctx.send("⚠️ Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await ctx.channel.delete()
    else:
        await ctx.send("❌ This command can only be used in ticket channels.")

@bot.hybrid_command(name="rename", description="Rename the current ticket channel")
@commands.has_role(ADMIN_ROLE_ID)
async def rename_ticket(ctx, new_name: str):
    if any(ctx.channel.name.startswith(pre) for pre in ["deposit-", "withdraw-", "dealer-"]):
        await ctx.channel.edit(name=new_name)
        await ctx.send(f"✅ Channel renamed to `{new_name}`")
    else:
        await ctx.send("❌ This command can only be used in ticket channels.")

# ================= BLACKJACK =================

class BlackjackView(discord.ui.View):
    def __init__(self, user, bet):
        super().__init__(timeout=60)
        self.user, self.bet = user, bet
        self.deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(self.deck)
        self.p_hand, self.d_hand = [self.deck.pop(), self.deck.pop()], [self.deck.pop(), self.deck.pop()]

    def get_score(self, hand):
        score = sum(hand); aces = hand.count(11)
        while score > 21 and aces: score -= 10; aces -= 1
        return score

    async def end_game(self, interaction):
        ps, ds = self.get_score(self.p_hand), self.get_score(self.d_hand)
        total_pl, cap = get_global_payout_status()
        
        if ps <= 21 and (ds > 21 or ps > ds):
            if total_pl + (self.bet * 0.95) >= cap:
                self.d_hand = [11, 10] 
                ds = 21

        win = 0
        if ps <= 21:
            if ds > 21 or ps > ds: 
                win = self.bet * 1.95 
                res = "🎉 **Win!**"
            elif ps == ds: 
                win = self.bet 
                res = "🤝 **Push**"
            else: res = "💀 **Loss.**"
        else: res = "❌ **Bust!**"

        update_balance(self.user.id, win)
        record_game(self.user.id, "Blackjack", self.bet, win)
        bal, _, _ = get_stats(self.user.id)
        
        embed = discord.Embed(title="🃏 Blackjack Results", color=0x2b2d31)
        embed.add_field(name="Dealer Hand", value=f"Score: `{ds}`\nCards: {self.d_hand}", inline=False)
        embed.add_field(name="Your Hand", value=f"Score: `{ps}`\nCards: {self.p_hand}", inline=False)
        embed.description = f"### {res}\n**Balance:** `${bal:,.2f}`"
        for c in self.children: c.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction, b):
        if interaction.user != self.user: return
        self.p_hand.append(self.deck.pop())
        if self.get_score(self.p_hand) >= 21: await self.end_game(interaction)
        else:
            embed = discord.Embed(title="🃏 Blackjack", color=0x2b2d31)
            embed.add_field(name="Dealer", value=f"Score: `?`\nCards: [{self.d_hand[0]}, ?]")
            embed.add_field(name="You", value=f"Score: `{self.get_score(self.p_hand)}`\nCards: {self.p_hand}")
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction, b):
        if interaction.user != self.user: return
        while self.get_score(self.d_hand) < 17: self.d_hand.append(self.deck.pop())
        await self.end_game(interaction)

@bot.hybrid_command(name="blackjack")
async def blackjack_cmd(ctx, bet: float):
    bal, _, _ = get_stats(ctx.author.id)
    if bal < bet: return await ctx.send("❌ No funds.")
    update_balance(ctx.author.id, -bet)
    
    view = BlackjackView(ctx.author, bet)
    embed = discord.Embed(title="🃏 Blackjack Deal", color=0x2b2d31)
    embed.add_field(name="Dealer", value=f"Score: `?`\nCards: [{view.d_hand[0]}, ?]")
    embed.add_field(name="You", value=f"Score: `{view.get_score(view.p_hand)}`\nCards: {view.p_hand}")
    await ctx.send(embed=embed, view=view)

# ================= MINES =================

class MinesView(discord.ui.View):
    def __init__(self, user_id, bet, bombs):
        super().__init__(timeout=120)
        self.user_id, self.bet, self.bombs, self.revealed, self.active = user_id, bet, bombs, 0, True
        self.grid = [0]*20; bomb_indices = random.sample(range(20), bombs)
        for i in bomb_indices: self.grid[i] = 1
        for i in range(20):
            btn = discord.ui.Button(label="?", style=discord.ButtonStyle.secondary, row=i//5)
            btn.callback = self.make_callback(i)
            self.add_item(btn)
        self.cash_btn = discord.ui.Button(label="💰 Cashout", style=discord.ButtonStyle.success, row=4)
        self.cash_btn.callback = self.cash_call; self.add_item(self.cash_btn)

    def get_multiplier(self):
        return (1 / (math.comb(20-self.bombs, self.revealed)/math.comb(20, self.revealed))) * 0.95

    def make_callback(self, index):
        async def callback(interaction):
            if interaction.user.id != self.user_id: return
            total_pl, cap = get_global_payout_status()
            potential_win = self.bet * self.get_multiplier()
            
            if self.grid[index] == 1 or (total_pl + (potential_win - self.bet) >= cap):
                self.active = False
                for c in self.children: c.disabled = True
                record_game(self.user_id, "Mines", self.bet, 0)
                bal, _, _ = get_stats(self.user_id)
                await interaction.response.edit_message(content=f"💥 **BOOM!** Bal: `${bal:,.2f}`", view=self)
            else:
                self.revealed += 1
                self.children[index].style, self.children[index].label, self.children[index].disabled = discord.ButtonStyle.primary, "💎", True
                self.cash_btn.label = f"💰 Cashout ({self.get_multiplier():.2f}x)"
                await interaction.response.edit_message(view=self)
        return callback

    async def cash_call(self, interaction):
        if self.revealed == 0 or not self.active: return
        win = self.bet * self.get_multiplier()
        update_balance(self.user_id, win); record_game(self.user_id, "Mines", self.bet, win)
        bal, _, _ = get_stats(self.user_id)
        for c in self.children: c.disabled = True
        await interaction.response.edit_message(content=f"✅ **Cashout!** Won `${win:,.2f}`\nBal: `${bal:,.2f}`", view=self)

@bot.hybrid_command(name="mines")
async def mines_cmd(ctx, bet: float, bombs: int):
    bal, _, _ = get_stats(ctx.author.id)
    if bal < bet or not (1<=bombs<=18): return await ctx.send("❌ Error.")
    update_balance(ctx.author.id, -bet)
    await ctx.send(f"💣 **Mines** (Bet: ${bet})", view=MinesView(ctx.author.id, bet, bombs))

# ================= DRAGON TOWER =================

class DragonTowerButton(discord.ui.Button):
    def __init__(self, col, row_idx):
        super().__init__(style=discord.ButtonStyle.secondary, label="🥚", row=row_idx)
        self.col, self.row_idx = col, row_idx

    async def callback(self, interaction):
        v = self.view
        if interaction.user.id != v.user_id or self.row_idx != v.current_row: return 
        total_pl, cap = get_global_payout_status()
        potential_win = v.bet * v.multipliers[v.current_row]
        
        if self.col == v.dragon_cols[v.current_row] or (total_pl + (potential_win - v.bet) >= cap):
            for c in v.children: c.disabled = True
            record_game(v.user_id, "DragonTower", v.bet, 0)
            bal, _, _ = get_stats(v.user_id)
            await interaction.response.edit_message(content=f"🐲 **Dragon!** Bal: `${bal:,.2f}`", view=v)
        else:
            self.style, self.label, self.disabled = discord.ButtonStyle.success, "🍳", True
            v.current_row += 1
            if v.current_row >= 5:
                win = v.bet * v.multipliers[-1]
                update_balance(v.user_id, win); record_game(v.user_id, "DragonTower", v.bet, win)
                bal, _, _ = get_stats(v.user_id)
                await interaction.response.edit_message(content=f"🏰 **Cleared!** Won `${win:,.2f}`", view=v)
            else:
                for c in v.children: 
                    if isinstance(c, DragonTowerButton) and c.row_idx == v.current_row: c.disabled = False
                v.cash_btn.label = f"💰 Cashout ({v.multipliers[v.current_row-1]:.2f}x)"
                await interaction.response.edit_message(view=v)

class DragonTowerView(discord.ui.View):
    def __init__(self, user_id, bet, diff):
        super().__init__(timeout=120); self.user_id, self.bet, self.current_row = user_id, bet, 0
        conf = {"easy": (4, [1.3, 1.5, 1.8, 2.2, 2.7]), "medium": (3, [1.4, 2.0, 2.8, 3.8, 4.8]), "hard": (2, [2.0, 3.8, 6.5, 12.0, 22.0])}
        self.cols, self.multipliers = conf[diff]
        self.dragon_cols = [random.randint(0, self.cols-1) for _ in range(5)]
        for r in range(5):
            for c in range(self.cols): self.add_item(DragonTowerButton(c, r))
        for c in self.children: 
            if isinstance(c, DragonTowerButton) and c.row_idx != 0: c.disabled = True
        self.cash_btn = discord.ui.Button(label="💰 Cashout", style=discord.ButtonStyle.success, row=4)
        self.cash_btn.callback = self.cash_call; self.add_item(self.cash_btn)
        
    async def cash_call(self, interaction):
        if self.current_row == 0: return
        win = self.bet * self.multipliers[self.current_row-1]
        update_balance(self.user_id, win)
        record_game(self.user_id, "DragonTower", self.bet, win)
        bal, _, _ = get_stats(self.user_id)
        for c in self.children: c.disabled = True
        await interaction.response.edit_message(content=f"✅ Won `${win:,.2f}`", view=None)

@bot.hybrid_command(name="dragontower")
async def dragontower_cmd(ctx, bet: float):
    bal, _, _ = get_stats(ctx.author.id)
    if bal < bet: return await ctx.send("❌ No funds.")
    update_balance(ctx.author.id, -bet)
    
    class DragonDiffView(discord.ui.View):
        def __init__(self, user, bet): super().__init__(timeout=60); self.user, self.bet = user, bet
        @discord.ui.button(label="Easy", style=discord.ButtonStyle.success)
        async def easy(self, i, b): await i.response.edit_message(view=DragonTowerView(self.user.id, self.bet, "easy"))
        @discord.ui.button(label="Medium", style=discord.ButtonStyle.primary)
        async def med(self, i, b): await i.response.edit_message(view=DragonTowerView(self.user.id, self.bet, "medium"))
        @discord.ui.button(label="Hard", style=discord.ButtonStyle.danger)
        async def hard(self, i, b): await i.response.edit_message(view=DragonTowerView(self.user.id, self.bet, "hard"))
    await ctx.send("🐉 Select Difficulty Tower:", view=DragonDiffView(ctx.author, bet))

# ================= OTHER GAMES =================

@bot.hybrid_command(name="coinflip")
async def coinflip(ctx, bet: float, side: str):
    bal, _, _ = get_stats(ctx.author.id)
    if bal < bet: return await ctx.send("❌ No funds.")
    update_balance(ctx.author.id, -bet); total_pl, cap = get_global_payout_status()
    res = random.choice(["heads", "tails"])
    if (total_pl + (bet * 0.95) >= cap): 
        res = "tails" if side.lower() == "heads" else "heads"
    
    win = bet * 1.9 if side.lower() == res else 0 
    update_balance(ctx.author.id, win); record_game(ctx.author.id, "Coinflip", bet, win)
    await ctx.send(f"🪙 **{res.upper()}**! P/L: `${(win-bet):+.2f}`")

@bot.hybrid_command(name="roulette")
async def roulette(ctx, bet: float, choice: str):
    bal, _, _ = get_stats(ctx.author.id)
    if bal < bet: return await ctx.send("❌ No funds.")
    update_balance(ctx.author.id, -bet); n = random.randint(0, 36); total_pl, cap = get_global_payout_status()
    red = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    won = (choice.isdigit() and int(choice)==n) or (choice.lower()=="red" and n in red) or (choice.lower()=="black" and n not in red and n!=0)
    p_win = bet * (35.0 if choice.isdigit() else 1.9)
    if won and (total_pl + (p_win - bet) >= cap): 
        won, n = False, (0 if n != 0 else 1)
    win = p_win if won else 0
    update_balance(ctx.author.id, win); record_game(ctx.author.id, "Roulette", bet, win)
    await ctx.send(f"🎡 Landed on: **{n}**! Result: `${(win-bet):+.2f}`")

@bot.hybrid_command(name="slots")
async def slots(ctx, bet: float):
    bal, _, _ = get_stats(ctx.author.id)
    if bal < bet: return await ctx.send("❌ No funds.")
    update_balance(ctx.author.id, -bet); total_pl, cap = get_global_payout_status()
    icons = ["🍒","🍋","🍇","💎","7️⃣"]
    r = random.choices(icons, k=3)
    if total_pl >= cap: r = ["🍒", "🍋", "🍇"]
    win = bet*50 if r[0]==r[1]==r[2]=="7️⃣" else bet*15 if r[0]==r[1]==r[2] else bet*2 if r[0]==r[1] or r[1]==r[2] else 0
    update_balance(ctx.author.id, win); record_game(ctx.author.id, "Slots", bet, win)
    await ctx.send(f"🎰 **[{' | '.join(r)}]** | Bal: `${get_stats(ctx.author.id)[0]:,.2f}`")

@bot.hybrid_command(name="baccarat")
async def baccarat(ctx, bet: float, side: str):
    bal, _, _ = get_stats(ctx.author.id)
    if bal < bet: return await ctx.send("❌ No funds.")
    update_balance(ctx.author.id, -bet); p, b = random.randint(0, 9), random.randint(0, 9); total_pl, cap = get_global_payout_status()
    won = (p>b and side.lower()=="player") or (b>p and side.lower()=="banker") or (p==b and side.lower()=="tie")
    if won and (total_pl + (bet * 0.95) >= cap): p, b = 0, 9
    win = (bet*1.95 if (p>b and side.lower()=="player") or (b>p and side.lower()=="banker") else bet*8.0 if p==b and side.lower()=="tie" else 0)
    update_balance(ctx.author.id, win); record_game(ctx.author.id, "Baccarat", bet, win)
    await ctx.send(f"🎴 P: `{p}` | B: `{b}` | Outcome: `${(win-bet):+.2f}`")

# ================= USER COMMANDS =================

@bot.hybrid_command(name="balance", description="Check your current balance")
async def balance_cmd(ctx):
    bal, wagered, pl = get_stats(ctx.author.id)
    embed = discord.Embed(title=f"💳 {ctx.author.display_name}'s Wallet", color=0x2b2d31)
    embed.add_field(name="Current Balance", value=f"```${bal:,.2f}```", inline=True)
    embed.add_field(name="Total Wagered", value=f"```${wagered:,.2f}```", inline=True)
    embed.add_field(name="Net Profit/Loss", value=f"```${pl:,.2f}```", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="deposit", description="Request to deposit funds via ticket")
async def deposit_ticket(ctx, amount: float):
    if amount <= 0: return await ctx.send("❌ Amount must be positive.")
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.get_role(ADMIN_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await ctx.guild.create_text_channel(name=f"deposit-{ctx.author.name}", overwrites=overwrites)
    
    embed = discord.Embed(title="💵 Deposit Request", color=0x2ecc71)
    embed.add_field(name="User", value=ctx.author.mention)
    embed.add_field(name="Amount", value=f"`${amount:,.2f}`")
    embed.description = "Please wait for a staff member to provide payment details. Admins use `/setbal` to finalize."
    
    await channel.send(content=f"{ctx.author.mention} <@&{ADMIN_ROLE_ID}>", embed=embed)
    await ctx.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

@bot.hybrid_command(name="withdraw", description="Request to withdraw funds via ticket")
async def withdraw_ticket(ctx, amount: float):
    bal, _, _ = get_stats(ctx.author.id)
    if amount <= 0: return await ctx.send("❌ Amount must be positive.")
    if bal < amount: return await ctx.send("❌ Insufficient balance for this withdrawal.")
    
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        ctx.guild.get_role(ADMIN_ROLE_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await ctx.guild.create_text_channel(name=f"withdraw-{ctx.author.name}", overwrites=overwrites)
    
    embed = discord.Embed(title="🏦 Withdrawal Request", color=0xe74c3c)
    embed.add_field(name="User", value=ctx.author.mention)
    embed.add_field(name="Requested Amount", value=f"`${amount:,.2f}`")
    embed.add_field(name="Current Balance", value=f"`${bal:,.2f}`")
    embed.description = "Please provide your payment details (e.g., wallet address). Staff will deduct balance via `/setbal` once sent."
    
    await channel.send(content=f"{ctx.author.mention} <@&{ADMIN_ROLE_ID}>", embed=embed)
    await ctx.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

@bot.command(name="requestdealer")
async def req_dealer_manual(ctx):
    await ctx.send("Click below to request a dealer.", view=DealerRequestView())

class DealerRequestView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Request Dealer", style=discord.ButtonStyle.blurple, custom_id="req_d")
    async def rd(self, interaction, button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            interaction.guild.get_role(ADMIN_ROLE_ID): discord.PermissionOverwrite(read_messages=True)
        }
        c = await interaction.guild.create_text_channel(name=f"dealer-{interaction.user.name}", overwrites=overwrites)
        await c.send(f"🤵 {interaction.user.mention} requested a dealer!"); await interaction.response.send_message(f"✅ Ticket: {c.mention}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}. House edge: 5%.")
    await bot.tree.sync()

bot.run(BOT_TOKEN)
