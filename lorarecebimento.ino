#include <SPI.h>
#include <LoRa.h>

#define SS 21
#define RST 22
#define DI0 4

bool loraConnected = false;

void setupLoRa() {
  Serial.print("Status LoRa: ");
  if (LoRa.begin(433E6)) {
    Serial.println("Conectado");
    loraConnected = true;
  } else {
    Serial.println("Falha!");
    loraConnected = false;
  }
}

void setup() {
  Serial.begin(115200);
  LoRa.setPins(SS, RST, DI0);
  setupLoRa();
}

void loop() {
  if (!loraConnected) {
    // Tenta reconectar a cada 5 segundos se a conexao falhou
    delay(5000);
    Serial.println("<S>Connecting...");
    setupLoRa();
    return;
  }
  
  int packetSize = LoRa.parsePacket();
  
  if (packetSize) {
    String receivedData = "";

    while (LoRa.available()) {
      receivedData += (char)LoRa.read();
    }

    if(receivedData.charAt(0)=='[' && receivedData.charAt(receivedData.length()-1)==']')
    {
      // Remove the first and last characters (the brackets)
      String cleanData = receivedData.substring(1, receivedData.length() - 1);
      Serial.println(cleanData);      
    }
    else
    {
    // Imprime apenas os dados recebidos via LoRa
      //Serial.print("[DISCARD]:");
      //Serial.println(receivedData); 
    }
  }
}
