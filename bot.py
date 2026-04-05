import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os

# 🔐 Bezpieczny token i MongoDB URL z ENV
TOKEN = os.getenv("TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

# 🍃 MongoDB
client = MongoClient(MONGO_URL)
db = client["discord_bot"]
collection = db["raporty"]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 📜 CENNIK
CENNIK = {
    "Leszcz": 1400,
    "Karmazyn": 2000,
    "Płoć": 1600,
    "Karaś srebrzysty": 1450,
    "Vobla": 1200,
    "Sum brązowy": 1400,
    "Ruda żelaza": 50,
    "Ruda złota": 600
}

RYBY = ["Leszcz", "Karmazyn", "Płoć", "Karaś srebrzysty", "Vobla", "Sum brązowy"]

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Zalogowano jako {bot.user}")

# 📊 RAPORT z możliwością przesłania screena
@bot.tree.command(name="raport")
@app_commands.choices(item=[app_commands.Choice(name=n, value=n) for n in CENNIK.keys()])
@app_commands.describe(uid="Twój UID w grze", ilosc="Ilość przedmiotu", screen="Załącz screen")
async def raport(interaction: discord.Interaction, item: app_commands.Choice[str], uid: str, ilosc: int, screen: discord.Attachment):
    if "Blake Family" not in [r.name for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

    # Liczymy kwotę
    if item.value in RYBY:
        kwota = CENNIK[item.value] * (ilosc / 1000)  # ryby: ilość dzielona przez 1000
    else:
        kwota = CENNIK[item.value] * ilosc

    report_id = collection.count_documents({}) + 1

    # Zapis raportu z linkiem do screena
    collection.insert_one({
        "id": report_id,
        "user_id": interaction.user.id,
        "uid": uid,
        "item": item.value,
        "ilosc": ilosc,
        "kwota": kwota,
        "img": screen.url if screen else None,
        "status": "oczekuje"
    })

    await interaction.response.send_message(
        f"✅ Raport zapisany!\n{item.value} | Ilość: {ilosc} = {kwota}$\n📸 Screen dodany!",
        ephemeral=True
    )

# 📊 STATUS
@bot.tree.command(name="status")
async def status(interaction: discord.Interaction, uid: str):
    raporty = collection.find({"uid": uid, "status": "zaakceptowany"})
    suma = 0
    count = 0
    for r in raporty:
        suma += r["kwota"]
        count += 1

    await interaction.response.send_message(
        f"📊 Raporty zaakceptowane: {count}\n💰 Zarobek: {suma}$",
        ephemeral=True
    )

# 💰 PREMIE (widoczne dla wszystkich)
@bot.tree.command(name="premie")
async def premie(interaction: discord.Interaction):
    raporty = collection.find({"status": "zaakceptowany"})
    suma = {}
    for r in raporty:
        uid = r["uid"]
        suma[uid] = suma.get(uid, 0) + r["kwota"]

    text = ""
    for uid, kwota in suma.items():
        text += f"{uid};{kwota};Premia\n"

    await interaction.response.send_message(text or "Brak danych", ephemeral=False)

# 🔘 PRZYCISKI do weryfikacji
class VerifyButtons(discord.ui.View):
    def __init__(self, report_id):
        super().__init__(timeout=None)
        self.report_id = report_id

    @discord.ui.button(label="✅ Akceptuj", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        collection.update_one({"id": self.report_id}, {"$set": {"status": "zaakceptowany"}})
        await interaction.response.send_message("✅ Zaakceptowano", ephemeral=True)

    @discord.ui.button(label="❌ Odrzuć", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        collection.update_one({"id": self.report_id}, {"$set": {"status": "odrzucony"}})
        await interaction.response.send_message("❌ Odrzucono", ephemeral=True)

# 👑 WERYFIKACJA
@bot.tree.command(name="weryfikacja")
async def weryfikacja(interaction: discord.Interaction):
    if "Zarząd Blake Family" not in [r.name for r in interaction.user.roles]:
        await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)
        return

    uids = collection.distinct("uid", {"status": "oczekuje"})
    if not uids:
        await interaction.response.send_message("Brak raportów", ephemeral=True)
        return

    class UIDSelect(discord.ui.Select):
        def __init__(self):
            options = [discord.SelectOption(label=uid) for uid in uids]
            super().__init__(placeholder="Wybierz UID", options=options)

        async def callback(self, interaction: discord.Interaction):
            raporty = collection.find({"uid": self.values[0], "status": "oczekuje"})
            for r in raporty:
                embed = discord.Embed(
                    title=f"UID {r['uid']}",
                    description=f"{r['item']} | Ilość: {r['ilosc']}\n💰 {r['kwota']}$"
                )
                if r["img"]:
                    embed.set_image(url=r["img"])
                await interaction.channel.send(embed=embed, view=VerifyButtons(r["id"]))
            await interaction.response.send_message("Wyświetlono raporty", ephemeral=True)

    view = discord.ui.View()
    view.add_item(UIDSelect())
    await interaction.response.send_message("Wybierz UID:", view=view, ephemeral=True)

bot.run(TOKEN)
