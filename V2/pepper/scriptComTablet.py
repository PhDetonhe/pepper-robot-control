import urllib2
import json
import time

DISTANCIA_CORREDOR = 1.5
DISTANCIA_FINAL = 1.5
ANGULO_90 = 1.57

class MyClass(GeneratedClass):

    def __init__(self):
        GeneratedClass.__init__(self)

        self.base_url = "http://SEU_IP:5000"

        self.grupo_atual = None
        self.ouvindo_ativo = False
        self.processando = False

    def onInput_onStart(self):
        tablet = self.session().service("ALTabletService")
        tablet.enableWifi()
        tablet.showWebview(self.base_url + "/")

        self.loop()

    def loop(self):
        while True:
            try:
                data = json.loads(urllib2.urlopen(self.base_url + "/estado_sistema").read())

                modo = data.get("modo")
                grupo = data.get("grupo_atual")

                # chamar próximo grupo
                if modo == "ouvindo" and not self.processando:
                    if not hasattr(self, "last_next") or time.time() - self.last_next > 3:
                        try:
                            urllib2.urlopen(self.base_url + "/next")
                            self.last_next = time.time()
                        except:
                            pass

                # ir até grupo
                if modo == "indo" and grupo is not None and not self.processando:
                    self.processando = True
                    self.grupo_atual = grupo
                    self.ir_para_grupo(grupo)

                # voltar pra base
                if modo == "voltando" and self.grupo_atual is not None and not self.processando:
                    self.processando = True
                    self.voltar_base()

                # iniciar escuta
                if modo == "ouvindo" and not self.ouvindo_ativo:
                    self.iniciar_reconhecimento()

                # parar escuta
                if modo != "ouvindo" and self.ouvindo_ativo:
                    self.parar_reconhecimento()

                # detectar silêncio (final da frase)
                if self.ouvindo_ativo and not self.processando:
                    if hasattr(self, "ultimo_audio"):
                        if time.time() - self.ultimo_audio > 2.5 and len(self.frase_buffer) > 0:

                            frase = " ".join(self.frase_buffer)
                            print("Frase final:", frase)

                            self.processando = True
                            self.parar_reconhecimento()

                            self.enviar_pergunta(frase)

            except Exception as e:
                print("Erro loop:", e)

            time.sleep(2)

    # ------------------------
    # MOVIMENTO
    # ------------------------

    def ir_para_grupo(self, grupo):
        motion = self.session().service("ALMotion")

        try:
            motion.wakeUp()
            motion.setStiffnesses("Body", 1.0)

            self.falar("Indo até o grupo " + str(grupo))

            motion.moveTo(DISTANCIA_CORREDOR, 0, 0)

            self.falar("Cheguei no ponto de decisão")

            if grupo == 1:
                self.falar("Virando para a direita")
                motion.moveTo(0, 0, -ANGULO_90)

            elif grupo == 2:
                self.falar("Virando para a esquerda")
                motion.moveTo(0, 0, ANGULO_90)

            else:
                self.falar("Grupo não reconhecido")
                self.processando = False
                return

            motion.moveTo(DISTANCIA_FINAL, 0, 0)

        except Exception as e:
            print("Erro movimento:", e)

        self.cheguei(grupo)

    def voltar_base(self):
        motion = self.session().service("ALMotion")
        grupo = self.grupo_atual

        if grupo is None:
            self.processando = False
            return

        try:
            self.parar_reconhecimento()

            self.falar("Encerrando atendimento")
            self.falar("Voltando para a posição inicial")

            motion.wakeUp()
            motion.setStiffnesses("Body", 1.0)

            motion.moveTo(-DISTANCIA_FINAL, 0, 0)

            if grupo == 1:
                motion.moveTo(0, 0, ANGULO_90)
            elif grupo == 2:
                motion.moveTo(0, 0, -ANGULO_90)
            else:
                motion.moveTo(0, 0, 3.14)

            motion.moveTo(-DISTANCIA_CORREDOR, 0, 0)

            self.falar("Voltei para a base")
            self.falar("Pronta para o próximo grupo")

            req = urllib2.Request(
                self.base_url + "/retorno_concluido",
                json.dumps({}),
                {"Content-Type": "application/json"}
            )
            urllib2.urlopen(req)

        except Exception as e:
            print("Erro voltar base:", e)

        finally:
            self.grupo_atual = None
            self.processando = False

    def cheguei(self, grupo):
        self.falar("Cheguei no grupo " + str(grupo))

        try:
            urllib2.urlopen(self.base_url + "/atendimento_start?grupo=" + str(grupo))
        except:
            print("Erro start")

        self.falar("Estou ouvindo, pode falar")

    # ------------------------
    # VOZ
    # ------------------------

    def iniciar_reconhecimento(self):
        if self.ouvindo_ativo:
            return

        self.ouvindo_ativo = True

        self.asr = self.session().service("ALSpeechRecognition")
        self.memory = self.session().service("ALMemory")

        self.asr.pause(True)
        self.asr.setLanguage("Portuguese")

        self.asr.setVocabulary([], True)

        self.asr.pause(False)
        self.asr.subscribe("ASR")

        self.frase_buffer = []
        self.ultimo_audio = time.time()

        self.subscriber = self.memory.subscriber("WordRecognized")
        self.connection = self.subscriber.signal.connect(self.onSpeechRecognized)

        print("Escutando frase completa...")

    def parar_reconhecimento(self):
        if not self.ouvindo_ativo:
            return

        try:
            self.asr.unsubscribe("ASR")

            if hasattr(self, "subscriber"):
                self.subscriber.signal.disconnect(self.connection)

        except Exception as e:
            print("Erro parar ASR:", e)

        self.ouvindo_ativo = False
        self.frase_buffer = []

    def onSpeechRecognized(self, value):
        if self.processando:
            return

        if not value or len(value) < 2:
            return

        palavra = value[0]
        confianca = value[1]

        if confianca < 0.3:
            return

        print("Ouvi:", palavra)

        # evita repetição
        if not self.frase_buffer or self.frase_buffer[-1] != palavra:
            self.frase_buffer.append(palavra)

        self.ultimo_audio = time.time()

    # ------------------------
    # IA
    # ------------------------

    def enviar_pergunta(self, texto):
        try:
            url = self.base_url + "/pergunta"

            data = json.dumps({
                "texto": texto,
                "grupo": self.grupo_atual
            })

            req = urllib2.Request(url, data, {"Content-Type": "application/json"})
            response = urllib2.urlopen(req)

            resultado = json.loads(response.read())
            resposta = resultado.get("resposta", "Não consegui responder.")

            self.falar(resposta)

        except Exception as e:
            print("Erro IA:", e)
            self.falar("Tive um problema ao pensar.")

        time.sleep(2)
        self.finalizar()

    # ------------------------
    # FINALIZAÇÃO
    # ------------------------

    def finalizar(self):
        try:
            req = urllib2.Request(
                self.base_url + "/encerrar_manual",
                json.dumps({}),
                {"Content-Type": "application/json"}
            )
            urllib2.urlopen(req)
        except:
            print("Erro encerrar_manual")

        self.processando = False

    # ------------------------
    # FALA
    # ------------------------

    def falar(self, texto):
        try:
            tts = self.session().service("ALTextToSpeech")
            tts.say(texto)
        except:
            print("Erro TTS")