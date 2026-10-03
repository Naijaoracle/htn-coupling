// Minimal AD8232 raw logger for ESP32.
// ECG output: AD8232 OUTPUT -> GPIO34 (ADC1, input only).
// USB serial format: sample,t_us,ecg_adc
// Battery isolated from mains while electrodes are attached.

constexpr int ECG_PIN = 34;
constexpr uint32_t SAMPLE_HZ = 250;
constexpr uint32_t PERIOD_US = 1000000UL / SAMPLE_HZ;

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(ECG_PIN, ADC_11db);
  delay(300);
  Serial.println("columns,t_us,ecg_adc");
}

void loop() {
  static uint32_t next_us = micros();
  const uint32_t now = micros();
  if ((int32_t)(now - next_us) < 0) return;
  next_us += PERIOD_US;
  const uint16_t ecg = analogRead(ECG_PIN);
  Serial.print("sample,");
  Serial.print(now);
  Serial.print(',');
  Serial.println(ecg);
}
