#include <micro_ros_arduino.h>
#include <WiFi.h>
#include "DHT.h"

#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <std_msgs/msg/string.h>
#include <time.h>
#include <sys/time.h>
#include <string.h>

#define DHTPIN 23
#define DHTTYPE DHT11

#define LDRPIN 34
#define SOILPIN 35

const unsigned long MESSAGE_INTERVAL_MS = 1000;
const unsigned long TEST_DURATION_MS =30000;

const size_t MAX_PAYLOAD_BYTES = 512;
char json_buffer[MAX_PAYLOAD_BYTES];

size_t target_payload_bytes = 0;
bool test_active = false;

unsigned long test_start_ms = 0;
unsigned long last_publish_ms = 0;

// Konfigurasi Micro-ROS Agent
char agent_ip[] = "192.168.0.167";
size_t agent_port = 8888;

char ssid[] = "Redline";
char password[] = "bentarduluya";

// Objek Sensor
DHT dht(DHTPIN, DHTTYPE);

// Variabel micro-ROS
rcl_publisher_t publisher;
rcl_node_t node;
rclc_support_t support;
rcl_allocator_t allocator;
std_msgs__msg__String msg;

// Variabel untuk menyimpan nomor urut paket (Sequence Number)
unsigned long sequence_number = 0;

uint64_t getEpochMillis() {
  struct timeval tv;
  gettimeofday(&tv, NULL);

  return ((uint64_t)tv.tv_sec * 1000ULL)
       + ((uint64_t)tv.tv_usec / 1000ULL);
}

// Untuk membentuk JSON dengan ukuran tepat
bool buildPayload(
    float suhu,
    float kelembapan,
    int nilaiLDR,
    int nilaiSoil,
    unsigned long timestamp,
    uint64_t send_epoch_ms,
    size_t target_bytes
) {
    char prefix[MAX_PAYLOAD_BYTES];
    int prefix_len = snprintf(
        prefix,
        sizeof(prefix),
        "{\"seq\":%lu,\"temperature\":%.1f,"
        "\"humidity\":%.1f,\"ldr\":%d,\"soil\":%d,"
        "\"timestamp\":%lu,\"send_epoch_ms\":%llu,"
        "\"padding\":\"",
        sequence_number,
        suhu,
        kelembapan,
        nilaiLDR,
        nilaiSoil,
        timestamp,
        (unsigned long long)send_epoch_ms
    );
    if (prefix_len < 0 ||
        (size_t)prefix_len >= sizeof(prefix)) {
        return false;
    }
    const char suffix[] = "\"}";
    const size_t suffix_len = sizeof(suffix) - 1;
    if (target_bytes >= MAX_PAYLOAD_BYTES ||
        target_bytes < (size_t)prefix_len + suffix_len) {
        return false;
    }
    size_t padding_len =
        target_bytes - (size_t)prefix_len - suffix_len;
    memcpy(json_buffer, prefix, prefix_len);
    memset(
        json_buffer + prefix_len,
        'X',
        padding_len
    );
    memcpy(
        json_buffer + prefix_len + padding_len,
        suffix,
        suffix_len + 1
    );
    msg.data.size = strlen(json_buffer);
    return msg.data.size == target_bytes;
}

void setup() {
  Serial.begin(115200);
  Serial.println("=== Smart Greenhouse Setup ===");

  dht.begin();
  pinMode(LDRPIN, INPUT);
  pinMode(SOILPIN, INPUT);

  // Inisialisasi generator random
  randomSeed(analogRead(36)); 

  // Langsung set transport tanpa WiFi.begin() manual
  Serial.println("Menghubungkan ke WiFi dan mengonfigurasi micro-ROS...");
  set_microros_wifi_transports(ssid, password, agent_ip, agent_port);
  delay(3000);

  // Sinkronisasi waktu ESP32 menggunakan NTP
configTime(7 * 3600, 0,
           "pool.ntp.org",
           "time.google.com");

Serial.println("Menyinkronkan waktu ESP32 dengan NTP...");

struct tm timeinfo;
bool timeSynced = false;

for (int i = 0; i < 20; i++) {
  if (getLocalTime(&timeinfo, 1000)) {
    timeSynced = true;
    break;
  }
}

if (timeSynced) {
  Serial.println("Waktu ESP32 berhasil disinkronkan.");
  Serial.println(&timeinfo, "%Y-%m-%d %H:%M:%S");
} else {
  Serial.println("PERINGATAN: Sinkronisasi NTP gagal.");
}

  // Pengecekan IP untuk memastikan ESP32 dapat koneksi wifi
  Serial.print("ESP32 IP Terdeteksi: ");
  Serial.println(WiFi.localIP());

  // Loop 'while' agar terus mencoba terkoneksi ke Agent
  Serial.println("Memeriksa koneksi ke micro-ROS Agent...");
  while (rmw_uros_ping_agent(1000, 5) != RMW_RET_OK) {
    Serial.print("["); Serial.print(millis()); Serial.print(" ms] ");
    Serial.println("Agent belum siap/tidak ditemukan. Menunggu Agent...");
    delay(1000);
  }
  Serial.println("Sukses: Terhubung ke micro-ROS Agent!");

  // Inisialisasi Node dan Publisher
  allocator = rcl_get_default_allocator();
  rclc_support_init(&support, 0, NULL, &allocator);
  rclc_node_init_default(&node, "esp32_sensor_node", "", &support);

  rclc_publisher_init_default(
    &publisher,
    &node,
    ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
    "/sensor_data"
  );

  // Alokasi memori buffer string
  msg.data.data = json_buffer;
  msg.data.capacity = sizeof(json_buffer);
  msg.data.size = 0;
  
  Serial.println("=== Inisialisasi micro-ROS Selesai ===");
}

void loop() {
    // Menunggu perintah ukuran payload melalui Serial Monitor.
    if (!test_active) {
        if (Serial.available()) {
            String input = Serial.readStringUntil('\n');
            input.trim();

            size_t requested_bytes = (size_t)input.toInt();

            if (requested_bytes == 144 ||
                requested_bytes == 256 ||
                requested_bytes == 384) {

                target_payload_bytes = requested_bytes;
                sequence_number = 0;

                test_start_ms = millis();
                last_publish_ms =
                    test_start_ms - MESSAGE_INTERVAL_MS;

                test_active = true;

                Serial.println("=== PENGUJIAN DIMULAI ===");
                Serial.print("Target payload: ");
                Serial.print(target_payload_bytes);
                Serial.println(" byte");
                Serial.println("Durasi: 30 detik");
                Serial.println("Message rate: 1 pesan/detik");
            } else {
                Serial.println(
                    "Perintah tidak valid. Masukkan 144, 256, atau 384."
                );
            }
        }

        return;
    }

    // Mengakhiri pengujian setelah 30 detik.
    if (millis() - test_start_ms >= TEST_DURATION_MS) {
        test_active = false;

        Serial.println("=== PENGUJIAN SELESAI ===");
        Serial.print("Total sequence terkirim: ");
        Serial.println(sequence_number);

        return;
    }

    // Menjaga interval pengiriman satu pesan per detik.
    if (millis() - last_publish_ms < MESSAGE_INTERVAL_MS) {
        return;
    }

    last_publish_ms = millis();
    sequence_number++;

    // Membaca sensor.
    float suhu = dht.readTemperature();
    float kelembapan = dht.readHumidity();
    int nilaiLDR = analogRead(LDRPIN);
    int nilaiSoil = analogRead(SOILPIN);

    // Fallback apabila pembacaan sensor tidak valid.
    bool dhtOK = !(isnan(suhu) || isnan(kelembapan));
    bool ldrOK = !(nilaiLDR <= 0 || nilaiLDR >= 4095);
    bool soilOK = !(nilaiSoil <= 0 || nilaiSoil >= 4095);

    if (!dhtOK) {
        suhu = 26.5 + (random(0, 60) / 10.0);
        kelembapan = 60.0 + (random(0, 150) / 10.0);
    }

    if (!ldrOK) {
        nilaiLDR = random(1500, 2500);
    }

    if (!soilOK) {
        nilaiSoil = random(1800, 2800);
    }

    unsigned long timestamp = millis();
    uint64_t send_epoch_ms = getEpochMillis();

    // Membentuk JSON dengan ukuran target yang ditentukan.
    bool payloadOK = buildPayload(
        suhu,
        kelembapan,
        nilaiLDR,
        nilaiSoil,
        timestamp,
        send_epoch_ms,
        target_payload_bytes
    );

    if (!payloadOK) {
        Serial.println("GAGAL: ukuran payload tidak sesuai.");
        return;
    }

    // Publikasi ke ROS 2.
    rcl_ret_t ret = rcl_publish(&publisher, &msg, NULL);

    if (ret == RCL_RET_OK) {
        Serial.print("seq=");
        Serial.print(sequence_number);
        Serial.print(" | payload=");
        Serial.print(msg.data.size);
        Serial.print(" byte | ");

        Serial.println(json_buffer);
    } else {
        Serial.print("Publish gagal, error code: ");
        Serial.println(ret);
    }
}