#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_NeoPixel.h>

const char* ssid     = "Wi-fi ADM";
const char* password = "ac8ce4ss8";

const char* serverUrl = "http://10.121.227.219:5000/update";

#define BOTAO_ENVIO   5
#define BOTAO_URGENTE 18
#define POT     34
#define LED_PIN  13

#define NUM_LEDS 10
#define GRUPO    1

Adafruit_NeoPixel fita(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// ─── CONTROLE ───────────────────────────
unsigned long lastDebounceEnvio = 0;
unsigned long lastDebounceUrgente = 0;
unsigned long debounceDelay = 50;

unsigned long lastSendTime = 0;
unsigned long sendCooldown = 3000;

bool lastEnvioState = HIGH;
bool lastUrgenteState = HIGH;

bool envioState = HIGH;
bool urgenteState = HIGH; 

bool urgente = false;

// ─── LED ────────────────────────────────
uint32_t corPorNivel(int nivel) {
  float t = (float)(nivel - 1) / (NUM_LEDS - 1);

  uint8_t r, g;

  if (t <= 0.5f) {
    r = t * 2 * 255;
    g = 255;
  } else {
    r = 255;
    g = (1 - (t - 0.5f) * 2) * 255;
  }

  return fita.Color(r, g, 0);
}

void atualizarFita(int nivel) {
  fita.clear();

  for (int i = 0; i < nivel; i++) {
    fita.setPixelColor(i, corPorNivel(nivel));
  }

  fita.show();
}

// ─── WIFI ───────────────────────────────
void garantirWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("🔄 Reconectando WiFi...");

  WiFi.disconnect();
  WiFi.begin(ssid, password);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 10) {
    Serial.print(".");
    delay(500);
    tentativas++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi conectado!");
  } else {
    Serial.println("\n❌ Falha ao conectar WiFi");
  }
}

// ─── ENVIO HTTP ─────────────────────────
void enviarDados(int nivel) {
  garantirWiFi();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ Sem WiFi - envio cancelado");
    return;
  }

  HTTPClient http;

  String url = String(serverUrl) +
               "?grupo=" + GRUPO +
               "&nivel=" + nivel +
               "&urgente=" + String(urgente ? 1 : 0);

  Serial.println("\n📤 ENVIANDO DADOS:");
  Serial.println(url);

  for (int i = 0; i < 3; i++) {
    http.begin(url);
    int code = http.GET();

    Serial.print("Tentativa ");
    Serial.print(i + 1);
    Serial.print(" | HTTP Code: ");
    Serial.println(code);

    if (code > 0) {
      Serial.println("✅ Enviado com sucesso!");
      http.end();
      return;
    }

    http.end();
    delay(500);
  }

  Serial.println("❌ Falha no envio após 3 tentativas");
}

// ─── SETUP ──────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=== SISTEMA INICIADO ===");

  pinMode(BOTAO_ENVIO, INPUT_PULLUP);
  pinMode(BOTAO_URGENTE, INPUT_PULLUP);
  pinMode(POT, INPUT);

  fita.begin();
  fita.setBrightness(80);
  fita.show();

  WiFi.begin(ssid, password);
  Serial.println("🔌 Tentando conectar WiFi...");
}

// ─── LOOP ───────────────────────────────
void loop() {
  int valorPot = analogRead(POT);
  int nivel = map(valorPot, 0, 4095, 1, NUM_LEDS);

  atualizarFita(nivel);

  // ─── BOTÃO URGENTE (CORRIGIDO) ───
int readUrgente = digitalRead(BOTAO_URGENTE);

  if (readUrgente != lastUrgenteState) {
    lastDebounceUrgente = millis();
  }

  if ((millis() - lastDebounceUrgente) > debounceDelay) {
    if (readUrgente == LOW && urgenteState == HIGH) {
      urgente = !urgente;

      Serial.print("🔴 URGENTE TOGGLE: ");
      Serial.println(urgente ? "ON (1)" : "OFF (0)");
    }
    urgenteState = readUrgente;
  }

  lastUrgenteState = readUrgente;
  // ─── BOTÃO ENVIO ───
  int readEnvio = digitalRead(BOTAO_ENVIO);

  if (readEnvio != lastEnvioState) {
    lastDebounceEnvio = millis();
  }

  if ((millis() - lastDebounceEnvio) > debounceDelay) {
    if (readEnvio == LOW && envioState == HIGH) {

      Serial.println("📥 BOTÃO ENVIO PRESSIONADO");

      if (millis() - lastSendTime > sendCooldown) {
        Serial.print("Estado urgente atual: ");
        Serial.println(urgente ? "1" : "0");

        enviarDados(nivel);
        lastSendTime = millis();
      } else {
        Serial.println("⏳ Cooldown ativo, não enviou");
      }
    }
    envioState = readEnvio;
  }

  lastEnvioState = readEnvio;
}