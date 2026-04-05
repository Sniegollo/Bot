import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os

TOKEN = os.getenv("TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

# ---------------- BAZA ----------------
mongo_client = MongoClient(MONGO_URL)
db = mongo_client["discord_bot"]
config_collection = db["config"]
raporty_collection = db["raporty"]

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- READY ----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Zalogowano jako {bot.user}")

# ---------------- PEŁNY CENNIK ----------------
PEŁNY_CENNIK = [
    {"item": "Leszcz", "cena": 1400, "sztuki": 1000},
    {"item": "Karmazyn", "cena": 2000, "sztuki": 1000},
    {"item": "Płoć", "cena": 1600, "sztuki": 1000},
    {"item": "Karaś srebrzysty", "cena": 1450, "sztuki": 1000},
    {"item": "Vobla", "cena": 1200, "sztuki": 1000},
    {"item": "Sum brązowy", "cena": 1400, "sztuki": 1000},
    {"item": "Ruda żelaza", "cena": 50, "sztuki": 1},
    {"item": "Ruda złota", "cena": 600, "sztuki": 1}
]

# ---------------- PANEL ----------------
class PanelView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Ustaw rolę raport/status", style=discord.ButtonStyle.green)
    async def set_raport(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleModal(interaction, "role_raport"))

    @discord.ui.button(label="Ustaw rolę weryfikacja", style=discord.ButtonStyle.green)
    async def set_weryfikacja(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleModal(interaction, "role_weryfikacja"))

    @discord.ui.button(label="Ustaw rolę premie", style=discord.ButtonStyle.green)
    async def set_premie(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RoleModal(interaction, "role_premie"))

class RoleModal(discord.ui.Modal, title="Wprowadź ID roli"):
    rola = discord.ui.TextInput(label="Wklej ID roli")
    def __init__(self, interaction, field):
        super().__init__()
        self.field = field
    async def on_submit(self, interaction: discord.Interaction):
        config_collection.update_one({"guild_id": interaction.guild.id}, {"$set": {self.field: int(self.rola.value)}})
        await interaction.response.send_message(f"✅ Ustawiono rolę {self.field}", ephemeral=True)

@bot.tree.command(name="panel")
async def panel(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Tylko właściciel serwera może tworzyć panel", ephemeral=True)
        return
    if not config_collection.find_one({"guild_id": interaction.guild.id}):
        config_collection.insert_one({
            "guild_id": interaction.guild.id,
            "role_raport": None,
            "role_weryfikacja": None,
            "role_premie": None
        })
    config = config_collection.find_one({"guild_id": interaction.guild.id})
    roles_text = f"Raport/Status: {config.get('role_raport')}\nWeryfikacja: {config.get('role_weryfikacja')}\nPremie: {config.get('role_premie')}"
    view = PanelView(interaction.guild.id)
    await interaction.response.send_message(f"🛠 Panel:\n{roles_text}", view=view, ephemeral=True)

@bot.tree.command(name="panel_edit")
async def panel_edit(interaction: discord.Interaction):
    await panel(interaction)

@bot.tree.command(name="panel_delete")
async def panel_delete(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Tylko właściciel może usuwać panel", ephemeral=True)
        return
    config_collection.delete_one({"guild_id": interaction.guild.id})
    await interaction.response.send_message("🗑️ Panel usunięty.", ephemeral=True)

# ---------------- RAPORT DROPDOWN ----------------
class ItemDropdown(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=x["item"]) for x in PEŁNY_CENNIK]
        super().__init__(placeholder="Wybierz przedmiot", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        interaction.user.selected_item = self.values[0]
        await interaction.response.send_message(f"Wybrano {self.values[0]}. Teraz użyj /raport z uid, ilość i screen", ephemeral=True)

@bot.tree.command(name="raport")
@app_commands.describe(uid="UID", ilosc="Ilość sztuk", screen="Screen")
async def raport(interaction: discord.Interaction, uid: str, ilosc: int, screen: discord.Attachment):
    if not hasattr(interaction.user, "selected_item"):
        view = discord.ui.View()
        view.add_item(ItemDropdown())
        await interaction.response.send_message("Wybierz przedmiot z dropdownu:", view=view, ephemeral=True)
        return
    item_name = interaction.user.selected_item
    entry = next((x for x in PEŁNY_CENNIK if x["item"] == item_name), None)
    if not entry:
        await interaction.response.send_message("❌ Wybrany przedmiot nie istnieje.", ephemeral=True)
        return
    kwota = (ilosc / entry["sztuki"]) * entry["cena"]
    raporty_collection.insert_one({
        "guild_id": interaction.guild.id,
        "uid": uid,
        "item": item_name,
        "ilosc": ilosc,
        "kwota": kwota,
        "img": screen.url,
        "status": "oczekuje"
    })
    del interaction.user.selected_item
    await interaction.response.send_message(f"✅ Dodano raport {item_name} ({int(kwota)}$)", ephemeral=True)

# ---------------- STATUS ----------------
@bot.tree.command(name="status")
async def status(interaction: discord.Interaction, uid: str):
    raporty = raporty_collection.find({"guild_id": interaction.guild.id, "uid": uid, "status": "zaakceptowany"})
    suma = sum(r["kwota"] for r in raporty)
    await interaction.response.send_message(f"💰 {int(suma)}$", ephemeral=True)

# ---------------- WERYFIKACJA ----------------
class WeryfikacjaView(discord.ui.View):
    def __init__(self, raport_id):
        super().__init__(timeout=None)
        self.raport_id = raport_id

    @discord.ui.button(label="✅ Akceptuj", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        raporty_collection.update_one({"_id": self.raport_id}, {"$set": {"status": "zaakceptowany"}})
        await interaction.message.delete()

    @discord.ui.button(label="❌ Odrzuć", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        raporty_collection.update_one({"_id": self.raport_id}, {"$set": {"status": "odrzucony"}})
        await interaction.message.delete()

@bot.tree.command(name="weryfikacja")
async def weryfikacja(interaction: discord.Interaction):
    config = config_collection.find_one({"guild_id": interaction.guild.id})
    role_weryfikacja = config.get("role_weryfikacja")
    if role_weryfikacja not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Nie masz uprawnień do weryfikacji", ephemeral=True)
        return
    raporty = list(raporty_collection.find({"guild_id": interaction.guild.id, "status": "oczekuje"}))
    if not raporty:
        await interaction.response.send_message("📭 Brak raportów do weryfikacji", ephemeral=True)
        return
    for r in raporty:
        embed = discord.Embed(title=f"UID {r['uid']}", description=f"{r['item']} | {r['ilosc']}\n💰 {int(r['kwota'])}$")
        embed.set_image(url=r["img"])
        view = WeryfikacjaView(r["_id"])
        await interaction.user.send(embed=embed, view=view)
    await interaction.response.send_message("📨 Wysłano raporty na priv", ephemeral=True)

# ---------------- PREMIE ----------------
@bot.tree.command(name="premie")
async def premie(interaction: discord.Interaction):
    config = config_collection.find_one({"guild_id": interaction.guild.id})
    role_premie = config.get("role_premie")
    if role_premie not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Nie masz uprawnień do premii", ephemeral=True)
        return
    raporty = raporty_collection.find({"guild_id": interaction.guild.id, "status": "zaakceptowany"})
    suma = {}
    for r in raporty:
        suma[r["uid"]] = suma.get(r["uid"], 0) + r["kwota"]
    text = ""
    for uid, kwota in suma.items():
        text += f"{uid};{int(kwota)};Premia\n"
    await interaction.response.send_message(text or "Brak danych")
    raporty_collection.delete_many({"guild_id": interaction.guild.id, "status": "zaakceptowany"})

bot.run(TOKEN)
