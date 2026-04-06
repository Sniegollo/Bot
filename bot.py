import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os

TOKEN = os.getenv("TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

mongo = MongoClient(MONGO_URL)
db = mongo["bot"]
config_db = db["config"]
raporty_db = db["raporty"]

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- READY ----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot działa jako {bot.user}")

# ---------------- PANEL ----------------
@bot.tree.command(name="panel")
async def panel(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("❌ Tylko właściciel", ephemeral=True)

    if config_db.find_one({"guild_id": interaction.guild.id}):
        return await interaction.response.send_message("⚠️ Panel już istnieje", ephemeral=True)

    config_db.insert_one({
        "guild_id": interaction.guild.id,
        "kategorie": [],
        "role_raport": None,
        "role_weryfikacja": None,
        "role_premie": None
    })

    await interaction.response.send_message("✅ Panel utworzony → użyj /panel_edit", ephemeral=True)

# ---------------- MODALE ----------------
class KategoriaModal(discord.ui.Modal, title="Dodaj kategorię"):
    nazwa = discord.ui.TextInput(label="Nazwa kategorii")

    async def on_submit(self, interaction: discord.Interaction):
        cfg = config_db.find_one({"guild_id": interaction.guild.id})
        cfg["kategorie"].append({"nazwa": self.nazwa.value, "itemy": []})
        config_db.update_one({"guild_id": interaction.guild.id}, {"$set": cfg})
        await interaction.response.send_message("✅ Dodano kategorię", ephemeral=True)

class ItemModal(discord.ui.Modal, title="Dodaj item"):
    nazwa = discord.ui.TextInput(label="Nazwa")
    cena = discord.ui.TextInput(label="Cena")
    sztuki = discord.ui.TextInput(label="Za ile sztuk")

    def __init__(self, kategoria):
        super().__init__()
        self.kategoria = kategoria

    async def on_submit(self, interaction: discord.Interaction):
        cfg = config_db.find_one({"guild_id": interaction.guild.id})

        for kat in cfg["kategorie"]:
            if kat["nazwa"] == self.kategoria:
                kat["itemy"].append({
                    "item": self.nazwa.value,
                    "cena": int(self.cena.value),
                    "sztuki": int(self.sztuki.value)
                })

        config_db.update_one({"guild_id": interaction.guild.id}, {"$set": cfg})
        await interaction.response.send_message("✅ Dodano item", ephemeral=True)

# ---------------- PANEL EDIT ----------------
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Dodaj kategorię", style=discord.ButtonStyle.blurple)
    async def add_kat(self, interaction, button):
        await interaction.response.send_modal(KategoriaModal())

    @discord.ui.button(label="➕ Dodaj item", style=discord.ButtonStyle.green)
    async def add_item(self, interaction, button):
        cfg = config_db.find_one({"guild_id": interaction.guild.id})
        if not cfg["kategorie"]:
            return await interaction.response.send_message("❌ Najpierw dodaj kategorię", ephemeral=True)

        class KatSelect(discord.ui.Select):
            def __init__(self):
                options = [discord.SelectOption(label=k["nazwa"]) for k in cfg["kategorie"]]
                super().__init__(placeholder="Wybierz kategorię", options=options)

            async def callback(self, i):
                await i.response.send_modal(ItemModal(self.values[0]))

        view = discord.ui.View()
        view.add_item(KatSelect())
        await interaction.response.send_message("Wybierz kategorię:", view=view, ephemeral=True)

    @discord.ui.button(label="🎭 Role", style=discord.ButtonStyle.gray)
    async def roles(self, interaction, button):
        await interaction.response.send_message("Wpisz ID roli przez komendy (na razie manual)", ephemeral=True)

@bot.tree.command(name="panel_edit")
async def panel_edit(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("❌ Tylko właściciel", ephemeral=True)

    await interaction.response.send_message("⚙️ Panel:", view=PanelView(), ephemeral=True)

# ---------------- PANEL DELETE ----------------
@bot.tree.command(name="panel_delete")
async def panel_delete(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("❌ Tylko właściciel", ephemeral=True)

    config_db.delete_one({"guild_id": interaction.guild.id})
    await interaction.response.send_message("🗑 Panel usunięty", ephemeral=True)

# ---------------- RAPORT UI ----------------
class ItemSelect(discord.ui.Select):
    def __init__(self, items):
        options = [
            discord.SelectOption(label=i["item"], description=f"{i['cena']}$/{i['sztuki']}")
            for i in items[:25]
        ]
        super().__init__(placeholder="Wybierz item", options=options)

    async def callback(self, interaction):
        self.view.item = self.values[0]
        await interaction.response.send_message(f"Wybrano {self.values[0]}", ephemeral=True)

class KatSelect(discord.ui.Select):
    def __init__(self, kategorie):
        options = [discord.SelectOption(label=k["nazwa"]) for k in kategorie]
        super().__init__(placeholder="Wybierz kategorię", options=options)

    async def callback(self, interaction):
        cfg = config_db.find_one({"guild_id": interaction.guild.id})
        kat = next(k for k in cfg["kategorie"] if k["nazwa"] == self.values[0])

        view = discord.ui.View()
        view.add_item(ItemSelect(kat["itemy"]))
        await interaction.response.send_message("📦 Wybierz item:", view=view, ephemeral=True)

@bot.tree.command(name="raport")
async def raport(interaction: discord.Interaction):
    cfg = config_db.find_one({"guild_id": interaction.guild.id})
    if not cfg or not cfg["kategorie"]:
        return await interaction.response.send_message("❌ Brak panelu", ephemeral=True)

    view = discord.ui.View()
    view.add_item(KatSelect(cfg["kategorie"]))

    await interaction.response.send_message("📂 Wybierz kategorię:", view=view, ephemeral=True)

# ---------------- PREMIE ----------------
@bot.tree.command(name="premie")
async def premie(interaction: discord.Interaction):
    raporty = raporty_db.find({"guild_id": interaction.guild.id, "status": "zaakceptowany"})
    suma = {}

    for r in raporty:
        suma[r["uid"]] = suma.get(r["uid"], 0) + r["kwota"]

    text = ""
    for uid, kwota in suma.items():
        text += f"{uid};{int(kwota)};Premia\n"

    await interaction.response.send_message(text or "Brak danych")
    raporty_db.delete_many({"guild_id": interaction.guild.id, "status": "zaakceptowany"})

bot.run(TOKEN)
