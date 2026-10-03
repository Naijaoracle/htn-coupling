#include <Arduino.h>
#include <stdint.h>
#include <Wire.h>
#include "MAX30105.h"

constexpr int ECG_PIN = 34;
constexpr uint32_t ECG_HZ = 250;
constexpr uint32_t ECG_PERIOD_US = 1000000UL / ECG_HZ;

MAX30105 max30102;
uint32_t last_red = 0;
uint32_t last_ir = 0;
volatile uint32_t last_red_shared = 0;
volatile uint32_t last_ir_shared = 0;
bool max_ok = false;

void ppgTask(void*) {
  for (;;) {
    if (max_ok && max30102.check()) {
      last_red_shared = max30102.getRed();
      last_ir_shared = max30102.getIR();
      max30102.nextSample();
    }
    vTaskDelay(1);
  }
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(ECG_PIN, ADC_11db);
  Wire.begin(21, 22);
  if (!max30102.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("max30102_error");
  } else {
    max_ok = true;
    max30102.setup(0x1F, 4, 2, 25, 411, 4096);
    max30102.setPulseAmplitudeRed(0x24);
    max30102.setPulseAmplitudeIR(0x24);
    Serial.println("max30102_ok");
  }
  xTaskCreatePinnedToCore(ppgTask, "ppg", 4096, nullptr, 1, nullptr, 0);
  Serial.println("columns,t_us,ecg_adc,red,ir");
}

void loop() {
  static uint32_t next_us = micros();
  const uint32_t now = micros();
  last_red = last_red_shared;
  last_ir = last_ir_shared;
  if ((int32_t)(now - next_us) < 0) return;
  next_us = now + ECG_PERIOD_US;
  Serial.print("sample,");
  Serial.print(now);
  Serial.print(',');
  Serial.print(analogRead(ECG_PIN));
  Serial.print(',');
  Serial.print(last_red);
  Serial.print(',');
  Serial.println(last_ir);
}
