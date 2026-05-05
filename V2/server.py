from flask import Flask, request, jsonify, render_template
import time
import requests

app = Flask(__name__)

API_KEY=""

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


def finalizar_atendimento(grupo, proximo_modo="ouvindo"):
    if grupo is None:
        return False

    try:
        grupo = int(grupo)
    except (TypeError, ValueError):
        return False

    for item in reversed(historico_atendimentos):
        if item["grupo"] == grupo and item["fim"] is None:
            item["fim"] = time.time()
            break

    estado_sistema["grupo_atual"] = None
    estado_sistema["modo"] = proximo_modo

    # limpa memÃ³ria
    conversas.pop(grupo, None)
    niveis_grupo.pop(grupo, None)

    return True

# ------------------------
# IA
# ------------------------

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
                        "content": "Você é a Léia, uma assistente educacional. Explique de forma simples, curta e clara para alunos iniciantes, dando uma direção para buscarem a própria resposta, ensine bem brevemente. Responda em no máximo 2 frases."
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
            
        # 🔥 LIMITA TAMANHO
        # resposta = resposta[:300]

    except Exception as e:
        print("IA falhou, usando fallback:", e)

    # fallback continua igual
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

# ------------------------
# PÁGINAS
# ------------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

# ------------------------
# ESP32
# ------------------------

@app.route("/update")
def update():
    grupo = int(request.args.get("grupo"))
    nivel = int(request.args.get("nivel"))
    urgente = request.args.get("urgente") == "1"

    if urgente:
        estado_sistema["urgente"] = grupo
    else:
        estado_sistema["fila"].append({
            "grupo": grupo,
            "nivel": nivel,
            "tempo": time.time(),
        })

        niveis_grupo[grupo] = nivel

    return jsonify({"ok": True})

# ------------------------
# PEPPER
# ------------------------

@app.route("/next")
def next_group():
    if estado_sistema["urgente"] is not None:
        grupo = estado_sistema["urgente"]
        estado_sistema["urgente"] = None
        estado_sistema["grupo_atual"] = grupo
        estado_sistema["modo"] = "indo"
        return jsonify({"grupo": grupo})

    if estado_sistema["fila"]:
        proximo = min(estado_sistema["fila"], key=lambda x: (x["nivel"], x["tempo"]))
        estado_sistema["fila"].remove(proximo)

        grupo = proximo["grupo"]
        estado_sistema["grupo_atual"] = grupo
        estado_sistema["modo"] = "indo"

        return jsonify({"grupo": grupo})

    return jsonify({"grupo": None})

# ------------------------
# PERGUNTA (IA)
# ------------------------

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

# ------------------------
# ATENDIMENTO
# ------------------------

@app.route("/atendimento_start")
def atendimento_start():
    grupo = int(request.args.get("grupo"))

    historico_atendimentos.append({
        "grupo": grupo,
        "inicio": time.time(),
        "fim": None
    })

    estado_sistema["grupo_atual"] = grupo
    estado_sistema["modo"] = "atendendo"

    return jsonify({"ok": True})

@app.route("/atendimento_end")
def atendimento_end():
    grupo = int(request.args.get("grupo"))

    for item in reversed(historico_atendimentos):
        if item["grupo"] == grupo and item["fim"] is None:
            item["fim"] = time.time()
            break

    estado_sistema["grupo_atual"] = None
    estado_sistema["modo"] = "ouvindo"

    # limpa memória
    conversas.pop(grupo, None)
    niveis_grupo.pop(grupo, None)

    return jsonify({"error": "deprecated endpoint"}), 400


@app.route("/encerrar_manual", methods=["POST"])
def encerrar_manual():
    global estado_escuta

    grupo = estado_sistema.get("grupo_atual")

    # ❌ nenhum atendimento ativo
    if grupo is None:
        return jsonify({
            "ok": False,
            "erro": "Nenhum atendimento ativo"
        }), 400

    finalizado = finalizar_atendimento(grupo, proximo_modo="voltando")

    # 🔇 desliga escuta enquanto volta
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


# estado do sistema (já resolvido)
@app.route("/estado_sistema")
def estado_sistema_api():
    return jsonify(estado_sistema)


# estado da IA (front usa)
@app.route("/ia_estado")
def ia_estado():
    return jsonify(estado_ia)


# histórico (dashboard usa)
@app.route("/historico")
def historico():
    return jsonify(historico_atendimentos)

@app.route("/conteudo")
def conteudo():
    return jsonify({
        "conteudo": estado_sistema["conteudo"]
    })

# resumo simples (dashboard usa)
@app.route("/resumo")
def resumo():
    total = len(historico_atendimentos)
    finalizados = len([h for h in historico_atendimentos if h["fim"] is not None])

    return jsonify({
        "total_atendimentos": total,
        "em_andamento": total - finalizados,
        "finalizados": finalizados,
        "tempo_medio_segundos": 0,
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

        # 🔥 não sobrescreve se já estiver atendendo
        if estado_sistema["modo"] in ["idle", "ouvindo"]:
            estado_sistema["modo"] = "ouvindo" if estado_escuta else "idle"

    return jsonify({
        "ouvindo": estado_escuta
    })
# ------------------------

app.run(host="0.0.0.0", port=5000)
