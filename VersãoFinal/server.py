
from flask import Flask, request, jsonify, render_template
import time
import requests
import whisper
import os

app = Flask(__name__)

modelo_whisper = whisper.load_model("base")

API_KEY = ""

estado_escuta = False
historico_atendimentos = []

niveis_grupo = {}
conversas = {}

estado_sistema = {
    "modo": "idle",
    "grupo_atual": None,
    "fila": [],
    "urgente": None,
    "conteudo": "inicio",
}

estado_ia = {
    "pergunta": None,
    "resposta": None,
    "processando": False
}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _criar_registro_historico(grupo):
    """
    Cria um registro no histórico para o grupo, mas só se ainda
    não existir um registro aberto (fim=None) para ele.
    Isso evita duplicatas quando /next e /atendimento_start
    são chamados em sequência.
    """
    ja_existe = any(
        item["grupo"] == grupo and item["fim"] is None
        for item in historico_atendimentos
    )
    if not ja_existe:
        historico_atendimentos.append({
            "grupo": grupo,
            "inicio": time.time(),
            "fim": None,
            "conteudo": estado_sistema.get("conteudo", "inicio"),
        })


def finalizar_atendimento(grupo, proximo_modo="ouvindo"):
    if grupo is None:
        return False

    try:
        grupo = int(grupo)
    except (TypeError, ValueError):
        return False

    # Garante que existe registro antes de fechar
    _criar_registro_historico(grupo)

    for item in reversed(historico_atendimentos):
        if item["grupo"] == grupo and item["fim"] is None:
            item["fim"] = time.time()
            break

    estado_sistema["grupo_atual"] = None
    estado_sistema["modo"] = proximo_modo

    conversas.pop(grupo, None)
    niveis_grupo.pop(grupo, None)

    return True


# ─── IA ──────────────────────────────────────────────────────────────────────

def gerar_resposta_ia(pergunta, grupo):
    if grupo not in conversas:
        conversas[grupo] = []

    resposta = ""

    try:
        nivel = niveis_grupo.get(grupo, "desconhecido")

        prompt = f"""
        Grupo: {grupo}
        Nível: {nivel}

        Pergunta:
        {pergunta}
        """

        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Você é a Léia, uma assistente educacional. "
                            "Explique de forma simples, curta e clara para alunos iniciantes, "
                            "dando uma direção para buscarem a própria resposta, ensine bem brevemente. "
                            "NUNCA use LaTeX, markdown matemático, símbolos especiais ou formatação técnica. "
                            "Escreva fórmulas de forma simples e legível em texto comum. "
                            "Exemplo correto: x = (-b +- raiz de b² - 4ac) / 2a "
                            "Responda em no máximo 2 frases."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            },
            timeout=10
        )

        data = r.json()
        if "choices" in data:
            resposta = data["choices"][0]["message"]["content"].strip()
        else:
            print("Resposta inesperada da API:", data)
            resposta = ""

    except Exception as e:
        print("IA falhou, usando fallback:", e)

    if not resposta or len(resposta) < 5:
        pergunta_lower = pergunta.lower()

        if "força" in pergunta_lower:
            resposta = "Força é o que faz algo se mover. Exemplo: empurrar uma mesa faz ela andar."
        elif "energia" in pergunta_lower:
            resposta = "Energia é o que faz as coisas funcionarem. Exemplo: uma bateria liga um LED."
        elif "sensor" in pergunta_lower:
            resposta = "Sensor detecta algo, como distância ou luz."
        elif "movimento" in pergunta_lower:
            resposta = "Movimento é quando algo muda de posição."
        else:
            resposta = "Isso é um conceito de física. Tente testar na prática com objetos."

    conversas[grupo].append(f"Aluno: {pergunta}")
    conversas[grupo].append(f"Tutor: {resposta}")

    print("\n--- IA DEBUG ---")
    print("Grupo:", grupo)
    print("Pergunta:", pergunta)
    print("Resposta:", resposta)
    print("----------------\n")

    return resposta


# ─── PÁGINAS ─────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


# ─── ESP32 ───────────────────────────────────────────────────────────────────

@app.route("/update")
def update():
    grupo = int(request.args.get("grupo"))
    nivel = int(request.args.get("nivel"))
    urgente = request.args.get("urgente") == "1"

    if urgente:
        estado_sistema["urgente"] = grupo
    else:
        # ✅ CORREÇÃO: evita duplicatas na fila — se o grupo já está
        # aguardando, apenas atualiza nível e timestamp em vez de
        # adicionar uma segunda entrada.
        na_fila = next(
            (item for item in estado_sistema["fila"] if item["grupo"] == grupo),
            None
        )
        if na_fila:
            na_fila["nivel"] = nivel
            na_fila["tempo"] = time.time()
        else:
            estado_sistema["fila"].append({
                "grupo": grupo,
                "nivel": nivel,
                "tempo": time.time(),
            })

        niveis_grupo[grupo] = nivel

    return jsonify({"ok": True})


# ─── PEPPER ──────────────────────────────────────────────────────────────────

@app.route("/next")
def next_group():
    if estado_sistema["urgente"] is not None:
        grupo = estado_sistema["urgente"]
        estado_sistema["urgente"] = None
        estado_sistema["grupo_atual"] = grupo
        estado_sistema["modo"] = "indo"

        # ✅ CORREÇÃO: registro criado aqui, no momento em que o grupo
        # é selecionado — não depende mais do /atendimento_start.
        _criar_registro_historico(grupo)

        return jsonify({"grupo": grupo})

    if estado_sistema["fila"]:
        # Nível 12 = mais dúvida = maior prioridade → pega o maior nível primeiro.
        # Em caso de empate, quem chegou antes (menor tempo) tem precedência.
        proximo = max(estado_sistema["fila"], key=lambda x: (x["nivel"], -x["tempo"]))
        estado_sistema["fila"].remove(proximo)

        grupo = proximo["grupo"]
        estado_sistema["grupo_atual"] = grupo
        estado_sistema["modo"] = "indo"

        # ✅ CORREÇÃO: mesmo aqui — histórico aberto no momento certo.
        _criar_registro_historico(grupo)

        return jsonify({"grupo": grupo})

    return jsonify({"grupo": None})

# ─── FILA PARA EXIBIÇÃO (dashboard) ─────────────────────────────────────────
#
# NOVO: /fila_display
# Antes a dashboard lia estado_sistema["fila"] direto via /estado_sistema,
# mas grupos urgentes ficam em estado_sistema["urgente"] (valor único) e
# nunca apareciam nas barras de prioridade.
#
# Esta rota monta uma lista unificada só para exibição — sem alterar a lógica
# interna. O urgente entra com nivel=0 e flag urgente=True para o frontend
# poder destacá-lo com cor/label diferente.
 
@app.route("/fila_display")
def fila_display():
    itens = []
 
    if estado_sistema["urgente"] is not None:
        itens.append({
            "grupo": estado_sistema["urgente"],
            "nivel": 0,
            "tempo": time.time(),
            "urgente": True,
        })
 
    for item in estado_sistema["fila"]:
        itens.append({
            "grupo": item["grupo"],
            "nivel": item["nivel"],
            "tempo": item["tempo"],
            "urgente": False,
        })
 
    return jsonify(itens)

# ─── WHISPER / ÁUDIO ────────────────────────────────────────────────────────

@app.route("/audio", methods=["POST"])
def audio():

    try:

        if "audio" not in request.files:
            return jsonify({
                "ok": False,
                "erro": "Nenhum áudio enviado"
            }), 400

        audio_file = request.files["audio"]

        caminho = "temp_audio.webm"

        audio_file.save(caminho)

        print("\n--- TRANSCRIBINDO ÁUDIO ---")

        resultado = modelo_whisper.transcribe(
            caminho,
            language="pt"
        )

        texto = resultado["text"].strip()

        print("Texto reconhecido:", texto)

        os.remove(caminho)

        estado_ia["pergunta"] = texto
        estado_ia["processando"] = True

        resposta = gerar_resposta_ia(texto, 0)

        estado_ia["resposta"] = resposta
        estado_ia["processando"] = False

        return jsonify({
            "ok": True,
            "texto": texto,
            "resposta": resposta
        })

    except Exception as e:

        print("ERRO WHISPER:", e)

        estado_ia["processando"] = False

        return jsonify({
            "ok": False,
            "erro": str(e)
        }), 500



# ─── PERGUNTA (IA) ───────────────────────────────────────────────────────────

@app.route("/pergunta", methods=["POST"])
def pergunta():
    data = request.get_json()

    texto = data.get("texto", "")
    grupo = int(data.get("grupo", 0))

    estado_ia["pergunta"] = texto
    estado_ia["processando"] = True

    resposta = gerar_resposta_ia(texto, grupo)

    estado_ia["resposta"] = resposta
    estado_ia["processando"] = False

    return jsonify({
        "ok": True,
        "resposta": resposta
    })


# ─── ATENDIMENTO ─────────────────────────────────────────────────────────────

@app.route("/atendimento_start")
def atendimento_start():
    grupo = int(request.args.get("grupo"))

    # ✅ CORREÇÃO: usa o helper — se /next já criou o registro,
    # esta chamada não cria duplicata.
    _criar_registro_historico(grupo)

    estado_sistema["grupo_atual"] = grupo
    estado_sistema["modo"] = "atendendo"

    return jsonify({"ok": True})


# ✅ CORREÇÃO: rota deprecated removida por completo.
# A rota /atendimento_end foi removida pois estava marcada como deprecated
# e retornava erro 400, podendo causar confusão no Pepper ou nos logs.
# Use /encerrar_manual no lugar.


@app.route("/encerrar_manual", methods=["POST"])
def encerrar_manual():
    global estado_escuta

    grupo = estado_sistema.get("grupo_atual")

    if grupo is None:
        return jsonify({"ok": False, "erro": "Nenhum atendimento ativo"}), 400

    finalizado = finalizar_atendimento(grupo, proximo_modo="voltando")
    estado_escuta = False

    return jsonify({
        "ok": True,
        "grupo": grupo,
        "finalizado": finalizado,
        "modo": estado_sistema["modo"]
    })


@app.route("/retorno_concluido", methods=["POST"])
def retorno_concluido():
    global estado_escuta

    estado_escuta = True
    estado_sistema["modo"] = "ouvindo"
    estado_sistema["grupo_atual"] = None

    return jsonify({"ok": True, "modo": estado_sistema["modo"]})


# ─── ESTADO / CONSULTA ───────────────────────────────────────────────────────

@app.route("/estado_sistema")
def estado_sistema_api():
    return jsonify(estado_sistema)


@app.route("/ia_estado")
def ia_estado():
    return jsonify(estado_ia)


@app.route("/historico")
def historico():
    return jsonify(historico_atendimentos)


@app.route("/conteudo")
def conteudo():
    return jsonify({
        "conteudo": estado_sistema["conteudo"]
    })


@app.route("/resumo")
def resumo():
    total = len(historico_atendimentos)
    finalizados = len([h for h in historico_atendimentos if h["fim"] is not None])

    tempos = [
        h["fim"] - h["inicio"]
        for h in historico_atendimentos
        if h["fim"] is not None
    ]
    tempo_medio = round(sum(tempos) / len(tempos)) if tempos else 0

    return jsonify({
        "total_atendimentos": total,
        "em_andamento": total - finalizados,
        "finalizados": finalizados,
        "tempo_medio_segundos": tempo_medio,   # ✅ CORREÇÃO: calculado de verdade
        "modo": estado_sistema["modo"],
        "grupo_atual": estado_sistema["grupo_atual"],
        "fila": estado_sistema["fila"],
        "urgente": estado_sistema["urgente"],
        "conteudo": estado_sistema["conteudo"],
        "ouvindo": estado_escuta
    })


@app.route("/estado", methods=["GET", "POST"])
def estado():
    global estado_escuta

    if request.method == "POST":
        data = request.get_json(silent=True) or {}

        estado_escuta = bool(data.get("ouvindo", False))

        if estado_sistema["modo"] in ["idle", "ouvindo"]:
            estado_sistema["modo"] = "ouvindo" if estado_escuta else "idle"

    return jsonify({
        "ouvindo": estado_escuta
    })


# ─── START ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)