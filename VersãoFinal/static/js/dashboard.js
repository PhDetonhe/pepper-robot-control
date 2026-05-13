function formatHora(timestamp) {
    if (!timestamp) {
        return "Em andamento";
    }
    return new Date(timestamp * 1000).toLocaleTimeString("pt-BR");
}

function formatDuracao(inicio, fim) {
    if (!fim) {
        return "Em andamento";
    }

    const total = Math.max(0, Math.round(fim - inicio));
    const minutos = Math.floor(total / 60);
    const segundos = total % 60;

    if (minutos === 0) {
        return `${segundos}s`;
    }

    return `${minutos}m ${segundos}s`;
}

function formatModo(modo) {
    const labels = {
        idle: "Aguardando",
        ouvindo: "Ouvindo",
        indo: "Em deslocamento",
        atendendo: "Atendendo",
    };
    return labels[modo] || modo || "--";
}

function renderHistorico(historico) {
    const container = document.getElementById("historico-lista");

    if (!historico.length) {
        container.className = "history-list empty-state";
        container.textContent = "Nenhum atendimento registrado ainda.";
        return;
    }

    container.className = "history-list";
    const itens = [...historico].reverse();

    container.innerHTML = itens
        .map((item) => {
            const finalizado = item.fim !== null;
            return `
                <article class="history-item">
                    <div class="history-topline">
                        <strong>Grupo ${item.grupo}</strong>
                        <span class="tag ${finalizado ? "" : "warn"}">${finalizado ? "Finalizado" : "Em andamento"}</span>
                    </div>
                    <div class="meta-row">
                        <span>Inicio ${formatHora(item.inicio)}</span>
                        <span>Fim ${formatHora(item.fim)}</span>
                        <span>Duracao ${formatDuracao(item.inicio, item.fim)}</span>
                    </div>
                    <div class="meta-row">
                        <span>Conteudo ${item.conteudo || "inicio"}</span>
                    </div>
                </article>
            `;
        })
        .join("");
}

function renderFila(fila) {
    const container = document.getElementById("queue-bars");

    if (!fila.length) {
        container.className = "queue-bars empty-state";
        container.textContent = "Sem grupos em espera.";
        return;
    }

    container.className = "queue-bars";
    // Nível 12 = mais dúvida = maior prioridade → ordena do maior para o menor
    const ordenada = [...fila].sort((a, b) => {
        if (a.nivel !== b.nivel) {
            return b.nivel - a.nivel;
        }
        return a.tempo - b.tempo;
    });

    // Escala fixa de 12 níveis (igual ao NUM_LEDS do ESP32).
    // Nível 12 = mais dúvida = maior prioridade = barra 100%.
    // Nível 1  = pouca dúvida = menor prioridade = barra ~8%.
    const NIVEL_MAX = 12;

    container.innerHTML = ordenada
        .map((item, index) => {
            const nivelSeguro = Math.max(1, Math.min(item.nivel, NIVEL_MAX));
            const largura = Math.round((nivelSeguro / NIVEL_MAX) * 100);
            const labelNivel = item.urgente ? "⚠️ URGENTE" : (index === 0 ? "Maior prioridade" : `Nível ${item.nivel}`);
            return `
                <article class="bar-item">
                    <div class="bar-head">
                        <strong>Grupo ${item.grupo}</strong>
                        <span>${labelNivel}</span>
                    </div>
                    <div class="bar-track">
                        <div class="bar-fill" style="width: ${largura}%"></div>
                    </div>
                </article>
            `;
        })
        .join("");
}

async function carregarDashboard() {
    const [historicoResponse, sistemaResponse, resumoResponse, filaResponse] = await Promise.all([
        fetch("/historico"),
        fetch("/estado_sistema"),
        fetch("/resumo"),
        fetch("/fila_display"),
    ]);

    const historico = await historicoResponse.json();
    const sistema = await sistemaResponse.json();
    const resumo = await resumoResponse.json();
    const filaDisplay = await filaResponse.json();

    document.getElementById("stat-total").textContent = resumo.total_atendimentos;
    document.getElementById("stat-andamento").textContent = resumo.em_andamento;
    document.getElementById("stat-finalizados").textContent = resumo.finalizados;
    document.getElementById("stat-tempo-medio").textContent = `${resumo.tempo_medio_segundos}s`;

    document.getElementById("live-modo").textContent = formatModo(resumo.modo);
    document.getElementById("live-escuta").textContent = resumo.ouvindo ? "Ativa" : "Pausada";
    document.getElementById("live-grupo").textContent = resumo.grupo_atual ?? "--";
    document.getElementById("live-urgente").textContent = resumo.urgente ?? "Nenhum";
    document.getElementById("live-conteudo").textContent = resumo.conteudo;

    renderFila(filaDisplay || []);
    renderHistorico(historico || []);
}

carregarDashboard();
setInterval(carregarDashboard, 1000);
