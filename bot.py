import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os

TOKEN = os.getenv("TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

client = MongoClient(MONGO_URL)
db = client["discord_bot"]

collection = db["raporty"]
config_collection = db["config"]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 🟢 READY
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Zalogowano jako {bot.user}")

# 🟢 PANEL
@bot.tree.command(name="panel")
async def panel(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Tylko właściciel", ephemeral=True)
        return

    if config_collection.find_one({"guild_id": interaction.guild.id}):
        await interaction.response.send_message("⚠️ Panel już istnieje", ephemeral=True)
        return

    config_collection.insert_one({
        "guild_id": interaction.guild.id,
        "cennik": {},
        "role_raport": [],
        "role_weryfikacja": [],
        "role_premie": []
    })

    await interaction.response.send_message("✅ Panel utworzony!", ephemeral=True)

# 🟢 PANEL EDIT
@bot.tree.command(name="panel_edit")
@app_commands.describe(tryb="Tryb", nazwa="Item", cena="Cena", rola="Rola")
@app_commands.choices(tryb=[
    app_commands.Choice(name="Cennik", value="cennik"),
    app_commands.Choice(name="Raport", value="raport"),
    app_commands.Choice(name="Weryfikacja", value="weryfikacja"),
    app_commands.Choice(name="Premie", value="premie")
])
async def panel_edit(interaction: discord.Interaction, tryb: app_commands.Choice[str], nazwa: str = None, cena: int = None, rola: discord.Role = None):

    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ Tylko właściciel", ephemeral=True)
        return

    config = config_collection.find_one({"guild_id": interaction.guild.id})

    if not config:
        await interaction.response.send_message("❌ Najpierw /panel", ephemeral=True)
        return

    if tryb.value == "cennik":
        config_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {f"cennik.{nazwa}": cena}}
        )
        await interaction.response.send_message("✅ Dodano do cennika", ephemeral=True)

    elif tryb.value == "raport":
        config_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$addToSet": {"role_raport": rola.id}}
        )
        await interaction.response.send_message("✅ Rola raport ustawiona", ephemeral=True)

    elif tryb.value == "weryfikacja":
        config_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$addToSet": {"role_weryfikacja": rola.id}}
        )
        await interaction.response.send_message("✅ Rola weryfikacji ustawiona", ephemeral=True)

    elif tryb.value == "premie":
        config_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$addToSet": {"role_premie": rola.id}}
        )
        await interaction.response.send_message("✅ Rola premii ustawiona", ephemeral=True)

# 🟢 RAPORT
@bot.tree.command(name="raport")
@app_commands.describe(uid="UID", item="Item", ilosc="Ilość", screen="Screen")
async def raport(interaction: discord.Interaction, uid: str, item: str, ilosc: int, screen: discord.Attachment):

    config = config_collection.find_one({"guild_id": interaction.guild.id})

    if not config:
        await interaction.response.send_message("❌ Brak konfiguracji (/panel)", ephemeral=True)
        return

    if not any(r.id in config["role_raport"] for r in interaction.user.roles):
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

    cennik = config["cennik"]

    if item not in cennik:
        await interaction.response.send_message("❌ Nie ma w cenniku", ephemeral=True)
        return

    # ryby /1000
    if item.lower() not in ["ruda żelaza", "ruda złota"]:
        kwota = cennik[item] * (ilosc / 1000)
    else:
        kwota = cennik[item] * ilosc

    collection.insert_one({
        "guild_id": interaction.guild.id,
        "uid": uid,
        "item": item,
        "ilosc": ilosc,
        "kwota": kwota,
        "img": screen.url,
        "status": "oczekuje"
    })

    await interaction.response.send_message(f"✅ Dodano raport ({int(kwota)}$)", ephemeral=True)

# 🟢 STATUS
@bot.tree.command(name="status")
async def status(interaction: discord.Interaction, uid: str):

    config = config_collection.find_one({"guild_id": interaction.guild.id})

    if not any(r.id in config["role_raport"] for r in interaction.user.roles):
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

    raporty = collection.find({
        "guild_id": interaction.guild.id,
        "uid": uid,
        "status": "zaakceptowany"
    })

    suma = sum(r["kwota"] for r in raporty)

    await interaction.response.send_message(f"💰 {int(suma)}$", ephemeral=True)

# 🟢 PREMIE
@bot.tree.command(name="premie")
async def premie(interaction: discord.Interaction):

    config = config_collection.find_one({"guild_id": interaction.guild.id})

    if not any(r.id in config["role_premie"] for r in interaction.user.roles):
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

    raporty = collection.find({
        "guild_id": interaction.guild.id,
        "status": "zaakceptowany"
    })

    suma = {}
    for r in raporty:
        suma[r["uid"]] = suma.get(r["uid"], 0) + r["kwota"]

    text = ""
    for uid, kwota in suma.items():
        text += f"{uid};{int(kwota)};Premia\n"

    await interaction.response.send_message(text or "Brak danych")

    collection.delete_many({
        "guild_id": interaction.guild.id,
        "status": "zaakceptowany"
    })

# 🟢 WERYFIKACJA
@bot.tree.command(name="weryfikacja")
async def weryfikacja(interaction: discord.Interaction):

    config = config_collection.find_one({"guild_id": interaction.guild.id})

    if not any(r.id in config["role_weryfikacja"] for r in interaction.user.roles):
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

    raporty = collection.find({
        "guild_id": interaction.guild.id,
        "status": "oczekuje"
    })

    for r in raporty:
        embed = discord.Embed(
            title=f"UID {r['uid']}",
            description=f"{r['item']} | {r['ilosc']}\n💰 {int(r['kwota'])}$"
        )
        embed.set_image(url=r["img"])

        view = discord.ui.View()

        async def accept(i):
            collection.update_one(r, {"$set": {"status": "zaakceptowany"}})
            await i.message.delete()

        async def reject(i):
            collection.update_one(r, {"$set": {"status": "odrzucony"}})
            await i.message.delete()

        view.add_item(discord.ui.Button(label="✅", style=discord.ButtonStyle.success, custom_id=str(r["_id"])))
        view.add_item(discord.ui.Button(label="❌", style=discord.ButtonStyle.danger, custom_id=str(r["_id"])))

        await interaction.user.send(embed=embed)

    await interaction.response.send_message("📨 Wysłano raporty na priv", ephemeral=True)

bot.run(TOKEN)
