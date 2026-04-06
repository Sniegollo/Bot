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
    print(f"Zalogowano jako {bot.user}")

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

# ---------------- ROLE SYSTEM ----------------
class RoleSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Raport/Status"),
            discord.SelectOption(label="Weryfikacja"),
            discord.SelectOption(label="Premie")
        ]
        super().__init__(placeholder="Wybierz rolę", options=options)

    async def callback(self, interaction: discord.Interaction):
        role_type = self.values[0]

        class RoleModal(discord.ui.Modal, title="Ustaw ID roli"):
            role_id = discord.ui.TextInput(label="ID roli")

            async def on_submit(self, i: discord.Interaction):
                cfg = config_db.find_one({"guild_id": i.guild.id})

                if role_type == "Raport/Status":
                    cfg["role_raport"] = int(self.role_id.value)
                elif role_type == "Weryfikacja":
                    cfg["role_weryfikacja"] = int(self.role_id.value)
                elif role_type == "Premie":
                    cfg["role_premie"] = int(self.role_id.value)

                config_db.update_one({"guild_id": i.guild.id}, {"$set": cfg})
                await i.response.send_message("✅ Ustawiono rolę", ephemeral=True)

        await interaction.response.send_modal(RoleModal())

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

    @discord.ui.button(label="🎭 Ustaw role", style=discord.ButtonStyle.gray)
    async def roles(self, interaction, button):
        view = discord.ui.View()
        view.add_item(RoleSelect())
        await interaction.response.send_message("Wybierz rolę:", view=view, ephemeral=True)

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

# ---------------- RAPORT MODAL ----------------
class RaportModal(discord.ui.Modal, title="Uzupełnij raport"):
    uid = discord.ui.TextInput(label="UID")
    ilosc = discord.ui.TextInput(label="Ilość")

    def __init__(self, item_data):
        super().__init__()
        self.item_data = item_data

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "📸 Wyślij screen w tej samej rozmowie (60s)",
            ephemeral=True
        )

        def check(m):
            return m.author == interaction.user and m.attachments

        try:
            msg = await bot.wait_for("message", timeout=60.0, check=check)
        except:
            return await interaction.followup.send("❌ Brak screena", ephemeral=True)

        ilosc = int(self.ilosc.value)
        kwota = (ilosc / self.item_data["sztuki"]) * self.item_data["cena"]

        raporty_db.insert_one({
            "guild_id": interaction.guild.id,
            "uid": self.uid.value,
            "item": self.item_data["item"],
            "ilosc": ilosc,
            "kwota": kwota,
            "img": msg.attachments[0].url,
            "status": "oczekuje"
        })

        embed = discord.Embed(title="✅ RAPORT DODANY", color=discord.Color.green())
        embed.add_field(name="📦 Item", value=self.item_data["item"])
        embed.add_field(name="🔢 Ilość", value=ilosc)
        embed.add_field(name="💰 Kwota", value=f"{int(kwota)}$")

        await interaction.followup.send(embed=embed, ephemeral=True)

# ---------------- SELECTY ----------------
class ItemSelect(discord.ui.Select):
    def __init__(self, items):
        self.items = items
        options = [
            discord.SelectOption(label=i["item"], description=f"{i['cena']}$/{i['sztuki']}")
            for i in items[:25]
        ]
        super().__init__(placeholder="Wybierz item", options=options)

    async def callback(self, interaction):
        selected = next(i for i in self.items if i["item"] == self.values[0])
        await interaction.response.send_modal(RaportModal(selected))

class KatSelect(discord.ui.Select):
    def __init__(self, kategorie):
        self.kategorie = kategorie
        options = [discord.SelectOption(label=k["nazwa"]) for k in kategorie]
        super().__init__(placeholder="Wybierz kategorię", options=options)

    async def callback(self, interaction):
        kat = next(k for k in self.kategorie if k["nazwa"] == self.values[0])

        view = discord.ui.View()
        view.add_item(ItemSelect(kat["itemy"]))

        await interaction.response.send_message("📦 Wybierz item:", view=view, ephemeral=True)

# ---------------- RAPORT ----------------
@bot.tree.command(name="raport")
async def raport(interaction: discord.Interaction):
    cfg = config_db.find_one({"guild_id": interaction.guild.id})

    if not cfg or not cfg["kategorie"]:
        return await interaction.response.send_message("❌ Brak panelu", ephemeral=True)

    if cfg["role_raport"] not in [r.id for r in interaction.user.roles]:
        return await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)

    view = discord.ui.View()
    view.add_item(KatSelect(cfg["kategorie"]))

    await interaction.response.send_message("📂 Wybierz kategorię:", view=view, ephemeral=True)

# ---------------- STATUS ----------------
@bot.tree.command(name="status")
async def status(interaction: discord.Interaction, uid: str):
    raporty = raporty_db.find({
        "guild_id": interaction.guild.id,
        "uid": uid,
        "status": "zaakceptowany"
    })

    suma = sum(r["kwota"] for r in raporty)

    embed = discord.Embed(title="📊 Status", color=discord.Color.gold())
    embed.add_field(name="💰 Zarobione", value=f"{int(suma)}$")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------- WERYFIKACJA ----------------
class WeryfikacjaView(discord.ui.View):
    def __init__(self, raport_id):
        super().__init__(timeout=None)
        self.raport_id = raport_id

    @discord.ui.button(label="✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        raporty_db.update_one({"_id": self.raport_id}, {"$set": {"status": "zaakceptowany"}})
        await interaction.message.delete()

    @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction, button):
        raporty_db.update_one({"_id": self.raport_id}, {"$set": {"status": "odrzucony"}})
        await interaction.message.delete()

@bot.tree.command(name="weryfikacja")
async def weryfikacja(interaction: discord.Interaction):
    cfg = config_db.find_one({"guild_id": interaction.guild.id})

    if cfg["role_weryfikacja"] not in [r.id for r in interaction.user.roles]:
        return await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)

    raporty = raporty_db.find({"guild_id": interaction.guild.id, "status": "oczekuje"})

    for r in raporty:
        embed = discord.Embed(title="📋 RAPORT", color=discord.Color.blue())
        embed.add_field(name="UID", value=r["uid"])
        embed.add_field(name="Item", value=r["item"])
        embed.add_field(name="Ilość", value=r["ilosc"])
        embed.add_field(name="Kwota", value=f"{int(r['kwota'])}$")
        embed.set_image(url=r["img"])

        await interaction.user.send(embed=embed, view=WeryfikacjaView(r["_id"]))

    await interaction.response.send_message("📨 Wysłano na priv", ephemeral=True)

# ---------------- PREMIE ----------------
@bot.tree.command(name="premie")
async def premie(interaction: discord.Interaction):
    cfg = config_db.find_one({"guild_id": interaction.guild.id})

    if cfg["role_premie"] not in [r.id for r in interaction.user.roles]:
        return await interaction.response.send_message("❌ Brak dostępu", ephemeral=True)

    raporty = raporty_db.find({
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

    raporty_db.delete_many({
        "guild_id": interaction.guild.id,
        "status": "zaakceptowany"
    })

bot.run(TOKEN)
