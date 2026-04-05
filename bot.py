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

# ---------------- MODALE ----------------
class CennikModal(discord.ui.Modal, title="Dodaj pozycję do cennika"):
    nazwa = discord.ui.TextInput(label="Nazwa przedmiotu")
    cena = discord.ui.TextInput(label="Cena")
    sztuki = discord.ui.TextInput(label="Ile sztuk przypada na 1 jednostkę")

    def __init__(self, interaction):
        super().__init__()
        self.interaction_ref = interaction

    async def on_submit(self, interaction: discord.Interaction):
        nazwa = self.nazwa.value
        cena = int(self.cena.value)
        sztuki = int(self.sztuki.value)
        guild_id = interaction.guild.id

        config = config_collection.find_one({"guild_id": guild_id})
        if not config:
            await interaction.response.send_message("❌ Panel nie istnieje. Najpierw /panel", ephemeral=True)
            return

        cennik = config.get("cennik", [])
        cennik.append({"item": nazwa, "cena": cena, "sztuki": sztuki})
        config_collection.update_one({"guild_id": guild_id}, {"$set": {"cennik": cennik}})
        await interaction.response.send_message(f"✅ Dodano {nazwa} = {cena}$ za {sztuki} sztuk", ephemeral=True)

class RoleModal(discord.ui.Modal, title="Wprowadź ID roli"):
    rola = discord.ui.TextInput(label="Wklej ID roli")

    def __init__(self, interaction, field):
        super().__init__()
        self.interaction_ref = interaction
        self.field = field

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        config_collection.update_one({"guild_id": guild_id}, {"$set": {self.field: int(self.rola.value)}})
        await interaction.response.send_message(f"✅ Ustawiono rolę {self.field}", ephemeral=True)

# ---------------- PANEL ----------------
@bot.tree.command(name="panel")
async def panel(interaction: discord.Interaction):
    """Tworzy pusty panel (tylko serwer i pola)."""
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Tylko właściciel może tworzyć panel", ephemeral=True)
        return

    if config_collection.find_one({"guild_id": interaction.guild.id}):
        await interaction.response.send_message("⚠️ Panel już istnieje. Użyj /panel_edit aby zmieniać", ephemeral=True)
        return

    config_collection.insert_one({
        "guild_id": interaction.guild.id,
        "cennik": [],
        "role_raport": None,
        "role_weryfikacja": None,
        "role_premie": None
    })

    await interaction.response.send_message("✅ Panel został utworzony. Teraz użyj /panel_edit aby dodać cennik i rangi.", ephemeral=True)

# ---------------- PANEL EDIT ----------------
class PanelEditView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Dodaj pozycję do cennika", style=discord.ButtonStyle.blurple)
    async def add_cennik(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CennikModal(interaction))

    @discord.ui.button(label="Ustaw rolę raport/status", style=discord.ButtonStyle.green)
    async def set_raport(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RoleModal(interaction, "role_raport")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ustaw rolę weryfikacja", style=discord.ButtonStyle.green)
    async def set_weryfikacja(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RoleModal(interaction, "role_weryfikacja")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ustaw rolę premie", style=discord.ButtonStyle.green)
    async def set_premie(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RoleModal(interaction, "role_premie")
        await interaction.response.send_modal(modal)

@bot.tree.command(name="panel_edit")
async def panel_edit(interaction: discord.Interaction):
    """Tu dodajesz cennik i rangi panelu."""
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Tylko właściciel może edytować panel", ephemeral=True)
        return

    config = config_collection.find_one({"guild_id": interaction.guild.id})
    if not config:
        await interaction.response.send_message("❌ Panel nie istnieje. Najpierw wpisz /panel", ephemeral=True)
        return

    view = PanelEditView(interaction.guild.id)
    await interaction.response.send_message("🛠 Panel edycji:", view=view, ephemeral=True)

# ---------------- PANEL DELETE ----------------
@bot.tree.command(name="panel_delete")
async def panel_delete(interaction: discord.Interaction):
    """Usuwa konfigurację panelu, żeby móc zacząć od nowa."""
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Tylko właściciel może usuwać panel", ephemeral=True)
        return

    config = config_collection.find_one({"guild_id": interaction.guild.id})
    if not config:
        await interaction.response.send_message("❌ Panel nie istnieje", ephemeral=True)
        return

    config_collection.delete_one({"guild_id": interaction.guild.id})
    await interaction.response.send_message("🗑️ Panel został usunięty. Możesz utworzyć nowy za pomocą /panel.", ephemeral=True)

# ---------------- RAPORT ----------------
@bot.tree.command(name="raport")
@app_commands.describe(uid="UID", item="Przedmiot z cennika", ilosc="Ilość sztuk", screen="Screen")
async def raport(interaction: discord.Interaction, uid: str, item: str, ilosc: int, screen: discord.Attachment):
    config = config_collection.find_one({"guild_id": interaction.guild.id})
    if not config:
        await interaction.response.send_message("❌ Panel nie ustawiony.", ephemeral=True)
        return

    if not config.get("role_raport") or config["role_raport"] not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

    cennik = config.get("cennik", [])
    entry = next((x for x in cennik if x["item"].lower() == item.lower()), None)
    if not entry:
        await interaction.response.send_message("❌ Brak takiego przedmiotu w cenniku", ephemeral=True)
        return

    kwota = (ilosc / entry["sztuki"]) * entry["cena"]

    raporty_collection.insert_one({
        "guild_id": interaction.guild.id,
        "uid": uid,
        "item": item,
        "ilosc": ilosc,
        "kwota": kwota,
        "img": screen.url,
        "status": "oczekuje"
    })

    await interaction.response.send_message(f"✅ Dodano raport {item} ({int(kwota)}$)", ephemeral=True)

# ---------------- STATUS ----------------
@bot.tree.command(name="status")
async def status(interaction: discord.Interaction, uid: str):
    config = config_collection.find_one({"guild_id": interaction.guild.id})
    if not config:
        await interaction.response.send_message("❌ Brak panelu", ephemeral=True)
        return

    if not config.get("role_raport") or config["role_raport"] not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

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
    if not config or not config.get("role_weryfikacja"):
        await interaction.response.send_message("❌ Brak konfiguracji lub roli weryfikacji", ephemeral=True)
        return

    if config["role_weryfikacja"] not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
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
    if not config or not config.get("role_premie"):
        await interaction.response.send_message("❌ Brak konfiguracji lub roli premii", ephemeral=True)
        return

    if config["role_premie"] not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
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
