# -*- coding: utf-8 -*-

import qi
import urllib2
import json
import time

# ─── CONFIGURAÇÕES DE MOVIMENTO ──────────────────────────────────────────────
# Distância em metros do home até o grupo (anda em linha reta após virar)
DISTANCIA_ATE_GRUPO = 2.0

# Ângulo de rotação em radianos (~90 graus)
ANGULO_90 = 1.57

# Intervalo de polling do servidor em segundos
POLL_INTERVALO = 1


class MyClass(GeneratedClass):

    def __init__(self):
        GeneratedClass.__init__(self)

        self.base_url = "http://172.16.80.26:5000"

        # Estados possíveis: IDLE | INDO | ATENDENDO | VOLTANDO
        self.estado      = "IDLE"
        self.grupo_atual = None

        # Impede que o loop dispare ações duplicadas enquanto o robô se move
        self.processando = False

    # ─── START ───────────────────────────────────────────────────────────────

    def onInput_onStart(self):
        self.timer = qi.PeriodicTask()
        self.timer.setCallback(self.update)
        self.timer.setUsPeriod(POLL_INTERVALO * 1000000)
        self.timer.start(True)

        self.falar("Sistema iniciado. Aguardando grupos.")

    # ─── LOOP PRINCIPAL ──────────────────────────────────────────────────────

    def update(self):
        if self.processando:
            return

        try:
            data = json.loads(
                urllib2.urlopen(self.base_url + "/estado_sistema").read()
            )
        except Exception as e:
            print("Erro /estado_sistema:", e)
            return

        modo  = data.get("modo")
        grupo = data.get("grupo_atual")

        # IDLE: pede próximo grupo
        if modo == "ouvindo" and self.estado == "IDLE":
            print("Buscando proximo grupo...")
            try:
                urllib2.urlopen(self.base_url + "/next")
            except Exception as e:
                print("Erro /next:", e)

        # Servidor selecionou grupo: ir até ele
        elif modo == "indo" and self.estado == "IDLE":
            self.processando = True
            self.grupo_atual = grupo
            self.ir_para_grupo(grupo)

        # Botão "Encerrar" pressionado na web: voltar
        elif modo == "voltando" and self.estado == "ATENDENDO":
            self.processando = True
            self.voltar_base()

    # ─── MOVIMENTO: IR AO GRUPO ──────────────────────────────────────────────

    def ir_para_grupo(self, grupo):
        """
        Do HOME:
          Grupo 1 (direita): gira -90 graus, depois anda reto
          Grupo 2 (esquerda): gira +90 graus, depois anda reto
        """
        motion = self.session().service("ALMotion")

        try:
            self.estado = "INDO"
            motion.wakeUp()
            motion.setStiffnesses("Body", 1.0)

            self.falar("Indo ate o grupo " + str(grupo))

            if grupo == 1:
                motion.moveTo(0, 0, -ANGULO_90)
                motion.moveTo(DISTANCIA_ATE_GRUPO, 0, 0)

            elif grupo == 2:
                motion.moveTo(0, 0, ANGULO_90)
                motion.moveTo(DISTANCIA_ATE_GRUPO, 0, 0)

            else:
                self.falar("Grupo invalido")
                self.estado      = "IDLE"
                self.processando = False
                return

            self.cheguei(grupo)

        except Exception as e:
            print("Erro no movimento ir:", e)
            self.estado      = "IDLE"
            self.processando = False

    # ─── CHEGADA ─────────────────────────────────────────────────────────────

    def cheguei(self, grupo):
        self.estado = "ATENDENDO"

        try:
            urllib2.urlopen(
                self.base_url + "/atendimento_start?grupo=" + str(grupo)
            )
        except Exception as e:
            print("Erro /atendimento_start:", e)

        self.falar(
            "Ola! Sou a Leia. "
            "Pode fazer sua pergunta no microfone. "
            "Quando terminar, pressione encerrar na tela."
        )

        # Libera o loop para monitorar modo == voltando
        self.processando = False

    # ─── VOLTA PARA HOME ─────────────────────────────────────────────────────

    def voltar_base(self):
        """
        Desfaz o percurso exato de ida:
          Grupo 1: recua → gira +90 graus (volta a olhar para frente)
          Grupo 2: recua → gira -90 graus (volta a olhar para frente)
        """
        motion = self.session().service("ALMotion")
        grupo  = self.grupo_atual

        try:
            self.estado = "VOLTANDO"
            self.falar("Atendimento encerrado. Voltando para a base.")

            motion.moveTo(-DISTANCIA_ATE_GRUPO, 0, 0)

            if grupo == 1:
                motion.moveTo(0, 0, ANGULO_90)
            elif grupo == 2:
                motion.moveTo(0, 0, -ANGULO_90)

            self.falar("Cheguei na base. Aguardando o proximo grupo.")

            req = urllib2.Request(
                self.base_url + "/retorno_concluido",
                json.dumps({}),
                {"Content-Type": "application/json"}
            )
            urllib2.urlopen(req)

        except Exception as e:
            print("Erro ao voltar:", e)

        self.estado      = "IDLE"
        self.grupo_atual = None
        self.processando = False

    # ─── TTS ─────────────────────────────────────────────────────────────────

    def falar(self, texto):
        try:
            tts = self.session().service("ALTextToSpeech")
            tts.setLanguage("Portuguese")
            tts.setParameter("speed", 90)
            tts.setParameter("pitchShift", 1.0)
            print("TTS:", texto)
            tts.say(texto)
        except Exception as e:
            print("Erro TTS:", e)

    # ─── STOP ────────────────────────────────────────────────────────────────

    def onInput_onStop(self):
        try:
            self.timer.stop()
        except Exception:
            pass
        self.onUnload()

    def onUnload(self):
        self.processando = False
        self.estado      = "IDLE"
        self.grupo_atual = None