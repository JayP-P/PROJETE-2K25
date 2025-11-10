#include <SPI.h>
#include <LoRa.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>

#define SS 22
#define RST 5
#define DI0 21

HardwareSerial gpsSerial(2);
TinyGPSPlus gps;

void setup() {
  Serial.begin(9600);
  pinMode(33, INPUT);
  pinMode(32, INPUT);

  LoRa.setPins(SS, RST, DI0);
  gpsSerial.begin(9600, SERIAL_8N1, 16, 17);

  if (!LoRa.begin(433E6)) {
    Serial.println("Falha ao iniciar o LoRa!");
    while (1);
  }

  Serial.println("LoRa inicializado com sucesso!");
}

void loop() {
  // Lê e processa os dados do GPS de forma eficiente
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  int mq7 = analogRead(32);
  int mq2 = analogRead(33);

  Serial.print("MQ7: ");
  Serial.println(mq7);
  Serial.print("MQ2: ");
  Serial.println(mq2);

  if (mq2 > 500 || mq7 > 500) {
    Serial.println("Pico detectado!");
    if (gps.location.isValid()) {
      unsigned long startTime = millis();
      Serial.println("Enviando via LoRa por 10 segundos...");

      while (millis() - startTime < 10000) { // Envia por 10 segundos
        // Atualiza os dados do GPS no loop de envio
        while (gpsSerial.available() > 0) {
          gps.encode(gpsSerial.read());
        }

        Serial.print("Enviando via LoRa: Lat=");
        Serial.print(gps.location.lat(), 6);
        Serial.print(", Lon=");
        Serial.println(gps.location.lng(), 6);

        LoRa.beginPacket();
        LoRa.print("[A,");
        LoRa.print(gps.location.lat(), 6);
        LoRa.print(gps.location.lng(), 6);
        LoRa.print("]");
        LoRa.endPacket();

        delay(500); // Intervalo entre os envios
      }
    } else {
      Serial.println("AGUARDANDO FIXO GPS...");
      delay(1000);
    }
  }
  delay(300); // Intervalo de leitura entre os sensores
}
