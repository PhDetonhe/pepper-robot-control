function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

function pulseUpdate(id) {
    const element = document.getElementById(id);
    if (!element) {
        return;
    }

    element.classList.remove("updated");
    void element.offsetWidth;
    element.classList.add("updated");
}

let lastQuestion = null;
let lastAnswer = null;
let lastThinking = null;
let isEndingAttendance = false;

function updateListenUI(ouvindo) {
    const topStatus = document.getElementById("listen-pill");
    const button = document.getElementById("toggle-listen-button");

    if (topStatus) {
        topStatus.textContent = ouvindo ? "🎤 Ouvindo..." : "✅ Pronto";
        topStatus.classList.toggle("active", ouvindo);
    }

    if (button) {
        button.classList.toggle("listening", ouvindo);
        button.setAttribute("aria-label", ouvindo ? "Desativar escuta" : "Ativar escuta");
        button.querySelector(".voice-button-text").textContent = ouvindo
            ? "Estou ouvindo você"
            : "Toque para falar comigo";
    }
}

function updateEndAttendanceButton(grupoAtual) {
    const button = document.getElementById("encerrar-atendimento-button");
    if (!button) {
        return;
    }

    const hasActiveGroup = grupoAtual !== null && grupoAtual !== undefined;
    button.hidden = !hasActiveGroup;
    button.disabled = !hasActiveGroup || isEndingAttendance;
}

async function carregarEstado() {
    try {
        const [estadoRes, sistemaRes, iaRes] = await Promise.all([
            fetch("/estado"),
            fetch("/estado_sistema"),
            fetch("/ia_estado")
        ]);

        const estado = await estadoRes.json();
        const sistema = await sistemaRes.json();
        const ia = await iaRes.json();

        const ouvindo = Boolean(estado.ouvindo);
        updateListenUI(ouvindo);
        updateEndAttendanceButton(sistema.grupo_atual);

        setText("grupo-urgente", sistema.urgente ?? "Nenhum");

        const questionText = ia.pergunta || "Faça uma pergunta para começar.";
        const answerText = ia.resposta || "Estou pronta para ajudar você.";
        const statusText = ia.processando ? "🤔 Pensando..." : "✅ Pronto";

        setText("ia-pergunta", questionText);
        setText("ia-resposta", answerText);
        setText("ia-status", statusText);

        if (lastQuestion !== null && lastQuestion !== questionText) {
            pulseUpdate("ia-pergunta");
        }

        if (lastAnswer !== null && lastAnswer !== answerText) {
            pulseUpdate("ia-resposta");
        }

        if (lastThinking !== null && lastThinking !== ia.processando) {
            pulseUpdate("ia-status");
        }

        lastQuestion = questionText;
        lastAnswer = answerText;
        lastThinking = ia.processando;
    } catch (error) {
        console.error("Erro ao carregar tela inicial:", error);
        setText("ia-status", "✅ Pronto");
    }
}

async function alternarEscuta() {
    const status = document.getElementById("listen-pill");
    const ativo = status?.classList.contains("active");

    try {
        await fetch("/estado", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                ouvindo: !ativo
            })
        });

        await carregarEstado();
    } catch (error) {
        console.error("Erro ao alternar escuta:", error);
    }
}

async function encerrarAtendimentoManual() {
    if (isEndingAttendance) {
        return;
    }

    isEndingAttendance = true;
    updateEndAttendanceButton(0);

    try {
        await fetch("/encerrar_manual", {
            method: "POST"
        });
    } catch (error) {
        console.error("Erro ao encerrar atendimento manualmente:", error);
    } finally {
        await carregarEstado();
        isEndingAttendance = false;
        await carregarEstado();
    }
}

const button = document.getElementById("toggle-listen-button");
if (button) {
    button.addEventListener("click", alternarEscuta);
}

const endButton = document.getElementById("encerrar-atendimento-button");
if (endButton) {
    endButton.addEventListener("click", encerrarAtendimentoManual);
}

carregarEstado();
setInterval(carregarEstado, 2000);
