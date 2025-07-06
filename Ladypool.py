import os
import json
import discord
import requests
import time
import re
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from asyncio import sleep
from datetime import timedelta, datetime

# Carrega variáveis
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ID do Ryann
ID_RYANN = "1101706170202325145"

# ID do canal para enviar relatório de mute por palavrão
ID_CANAL_RELATORIO = 1359283338350821634

# Configurações
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Estado da IA e memória
MEMORIA_ARQUIVO = "memoria.json"
PALAVROES_ARQUIVO = "palavroes.json"
modo_ensino = {}
ia_ativa = False
responder_somente_ryann = False
ultimo_uso_ia = 0
COOLDOWN_IA = 5
respondendo_agora = False
usuarios_com_permissao = [ID_RYANN]
canais_bloqueados = []

def carregar_memoria():
    try:
        with open(MEMORIA_ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def salvar_memoria(memoria):
    with open(MEMORIA_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(memoria, f, indent=4, ensure_ascii=False)

memoria = carregar_memoria()

def carregar_palavroes():
    try:
        with open(PALAVROES_ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def salvar_palavroes(lista):
    with open(PALAVROES_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)

palavroes = carregar_palavroes()

def atualizar_regex_palavroes():
    global regex_palavroes
    regex_palavroes = [re.compile(rf"\b{re.escape(p.lower())}\b", re.IGNORECASE) for p in palavroes]

atualizar_regex_palavroes()

def gerar_resposta_ia(mensagem):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {"role": "system", "content": "Você é a Ladypool. Responda com poucas palavras, simples, parecendo humana. Se não souber, diga que não sabe."},
            {"role": "user", "content": mensagem}
        ],
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return "Deu ruim... tenta de novo depois 😬"
    except Exception as e:
        return f"Erro ao chamar IA: {e}"

@bot.event
async def on_ready():
    print(f"Ladypool conectada como {bot.user}")
    try:
        synced = await tree.sync()
        print(f"Slash commands sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

@bot.event
async def on_message(message):
    global ia_ativa, responder_somente_ryann, ultimo_uso_ia, respondendo_agora

    if message.author.bot:
        return

    user_id = str(message.author.id)
    conteudo_bruto = message.content.strip().lower()
    canal_id = message.channel.id

    # Sai / Volta Ladypool
    if user_id == ID_RYANN:
        if conteudo_bruto == "sai, ladypool":
            if canal_id not in canais_bloqueados:
                canais_bloqueados.append(canal_id)
                await message.reply("Ok, vou ficar quietinha nesse canal. 🤐", mention_author=True)
            return
        elif conteudo_bruto == "volta, ladypool":
            if canal_id in canais_bloqueados:
                canais_bloqueados.remove(canal_id)
                await message.reply("Voltei! Pode deixar comigo. 😉", mention_author=True)
            return

    if canal_id in canais_bloqueados:
        return

    # Permissões de ensino
    if user_id == ID_RYANN:
        if "ladypool, permissao para tal" in conteudo_bruto and message.mentions:
            alvo_id = str(message.mentions[0].id)
            if alvo_id not in usuarios_com_permissao:
                usuarios_com_permissao.append(alvo_id)
            await message.reply(f"✅ {message.mentions[0].mention} agora pode adicionar/remover palavrões.", mention_author=True)
            return
        elif "ladypool, proibir tal" in conteudo_bruto and message.mentions:
            alvo_id = str(message.mentions[0].id)
            if alvo_id in usuarios_com_permissao:
                usuarios_com_permissao.remove(alvo_id)
            await message.reply(f"🚫 {message.mentions[0].mention} não pode mais adicionar/remover palavrões.", mention_author=True)
            return

    # Add palavrão
    if conteudo_bruto == "add" and user_id in usuarios_com_permissao and message.reference:
        try:
            alvo = await message.channel.fetch_message(message.reference.message_id)
            termo = alvo.content.lower().strip()
            if termo in memoria or termo in palavroes:
                await message.reply(f"⚠️ O termo **'{termo}'** já foi adicionado anteriormente.", mention_author=True)
                return
            memoria[termo] = "Essa palavra não pode ser usada."
            salvar_memoria(memoria)
            palavroes.append(termo)
            salvar_palavroes(palavroes)
            atualizar_regex_palavroes()
            await message.reply(f"✅ Termo **'{termo}'** bloqueado: memória + mute automático.", mention_author=True)
        except:
            await message.reply("❌ Não consegui ler a mensagem anterior.", mention_author=True)
        return

    # Remove palavrão
    if conteudo_bruto == "remove" and user_id in usuarios_com_permissao and message.reference:
        try:
            alvo = await message.channel.fetch_message(message.reference.message_id)
            termo = alvo.content.lower().strip()
            if termo not in memoria and termo not in palavroes:
                await message.reply(f"⚠️ O termo **'{termo}'** não está na lista de bloqueados.", mention_author=True)
                return
            if termo in memoria:
                memoria.pop(termo)
                salvar_memoria(memoria)
            if termo in palavroes:
                palavroes.remove(termo)
                salvar_palavroes(palavroes)
                atualizar_regex_palavroes()
            await message.reply(f"✅ Termo **'{termo}'** removido da lista de bloqueados.", mention_author=True)
        except:
            await message.reply("❌ Não consegui ler a mensagem anterior.", mention_author=True)
        return

    # Mute automático por palavrão
    if user_id != ID_RYANN and user_id not in usuarios_com_permissao:
        texto = message.content.lower()
        for rp in regex_palavroes:
            if rp.search(texto):
                try:
                    await message.author.timeout(timedelta(hours=1), reason="Palavrão")
                except Exception as e:
                    await message.channel.send(f"❌ Não consegui mutar {message.author.mention}: {e}")
                    return
                await message.channel.send(f"⚠️ {message.author.mention} foi mutado por 1 hora por usar palavrão.")
                canal_relatorio = bot.get_channel(ID_CANAL_RELATORIO)
                if canal_relatorio:
                    agora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    await canal_relatorio.send(
                        f"**Relatório de Exílio!**\n\n"
                        f"**Responsável:** {bot.user.mention}\n"
                        f"**Indivíduo:** {message.author.display_name}\n"
                        f"**Justificativas:** Palavrão detectado: '{message.content}'\n"
                        f"**Data e horário:** {agora_str}"
                    )
                return

    if bot.user not in message.mentions and user_id not in modo_ensino:
        return await bot.process_commands(message)

    if responder_somente_ryann and user_id != ID_RYANN:
        return

    if user_id == ID_RYANN:
        if "ladypool, ativar ia" in conteudo_bruto:
            ia_ativa = True
            await message.reply("Certo, IA ativada.", mention_author=True)
            return
        elif "ladypool, desativar ia" in conteudo_bruto:
            ia_ativa = False
            await message.reply("Certo, IA desativada.", mention_author=True)
            return
        elif "ladypool, responde somente" in conteudo_bruto:
            responder_somente_ryann = True
            await message.reply("Todo mundo está silenciado, Rauan737_", mention_author=True)
            return
        elif "ladypool, falar com todo mundo" in conteudo_bruto:
            responder_somente_ryann = False
            await message.reply("Agora posso voltar a falar com o pessoal do exército.", mention_author=True)
            return

    referencia = None
    if message.reference:
        try:
            referencia = await message.channel.fetch_message(message.reference.message_id)
        except:
            pass

    conteudo = message.content.replace(f"<@{bot.user.id}>", "").strip().lower()
    alvo = referencia if referencia and referencia.author.id != bot.user.id else message

    if not conteudo and not referencia:
        await message.reply("Sim?", mention_author=True)
        return

    agora = time.time()
    if ia_ativa and agora - ultimo_uso_ia < COOLDOWN_IA:
        return

    if canal_id in canais_bloqueados:
        return

    async with message.channel.typing():
        await sleep(3)

        if user_id == ID_RYANN and user_id in modo_ensino:
            pergunta = modo_ensino.pop(user_id)
            memoria[pergunta] = conteudo
            salvar_memoria(memoria)
            await alvo.reply("Entendido! Vou lembrar disso.", mention_author=True)
            return

        if ia_ativa:
            if respondendo_agora:
                return
            respondendo_agora = True
            resposta = gerar_resposta_ia(conteudo)
            await alvo.reply(resposta, mention_author=True)
            ultimo_uso_ia = time.time()
            respondendo_agora = False
            return

        if conteudo in memoria:
            await alvo.reply(memoria[conteudo], mention_author=True)
            return

        if user_id == ID_RYANN:
            modo_ensino[user_id] = conteudo
            await alvo.reply("Ainda não aprendi isso. Pode me ensinar? 🤓", mention_author=True)
            return

        await alvo.reply("Perdoe-me, ainda não sei responder isso.", mention_author=True)

    await bot.process_commands(message)

@tree.command(name="ajuda", description="Exibe opções de ajuda")
async def ajuda_command(interaction: discord.Interaction):
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Como me alisto?", style=discord.ButtonStyle.primary, custom_id="alistar"))
    view.add_item(discord.ui.Button(label="Como me revogo?", style=discord.ButtonStyle.danger, custom_id="revogar"))
    view.add_item(discord.ui.Button(label="Como denuncio?", style=discord.ButtonStyle.secondary, custom_id="denunciar"))
    await interaction.response.send_message("Escolha uma opção:", view=view)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.channel.id in canais_bloqueados:
        return
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data.get("custom_id")
        respostas = {
            "alistar": "🪖 Entre no jogo do EB e aguarde um graduado. Se demorar, abra um ticket.",
            "revogar": "🧾 Vá ao canal de suporte e abra um ticket de revogação.",
            "denunciar": "🚨 Vá ao suporte e abra um ticket de denúncia."
        }
        if cid in respostas:
            await interaction.response.send_message(respostas[cid], ephemeral=True)

@tree.command(name="calcular", description="Faz um cálculo simples")
@app_commands.describe(expressao="Ex: 5 + 2 ou 10 x 4")
async def calcular(interaction: discord.Interaction, expressao: str):
    if interaction.channel.id in canais_bloqueados:
        return
    try:
        expressao = expressao.replace("x", "*").replace("X", "*").replace("÷", "/")
        resultado = eval(expressao)
        await interaction.response.send_message(f"🧠 Resultado de `{expressao}` = **{resultado}**", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Expressão inválida. Ex: `5 + 2` ou `10 x 4`.", ephemeral=True)

bot.run(TOKEN)
