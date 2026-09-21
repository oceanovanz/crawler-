#include <Arduino.h>
#include <Wire.h>

#include "imu.h"
#include "motors.h"
#include "serial_protocol.h"
#include "sonar.h"

constexpr uint32_t TELEMETRY_PERIOD_MS = 100;

uint32_t lastTelemetryMs = 0;

void setup() {
    // Serial command handling
    setupSerialProtocol();
    delay(1000);

    // I2C
    const bool wireOk = Wire.begin(BNO_SDA_PIN, BNO_SCL_PIN, BNO_I2C_FREQUENCY_HZ);

    if (!wireOk) {
        Serial.println("WARN,I2C_BUS_SETUP_FAILED");
    } else {
        Serial.printf("OK,I2C_STARTED,SDA=%u,SCL=%u,FREQ=%lu\n", BNO_SDA_PIN, BNO_SCL_PIN,
                      static_cast<unsigned long>(BNO_I2C_FREQUENCY_HZ));
    }

    // // Motors
    // if (!setupMotors()) {
    //     Serial.println("FATAL,PWM_SETUP_FAILED");

    //     while (true) {
    //         disarmMotors();
    //         delay(1000);
    //     }
    // }

    // IMU
    setupImu(wireOk);

    // Sonar
    setupSonar();

    // Always start disarmed
    // disarmMotors();

    Serial.println("READY,DISARMED");
}

void loop() {
    serviceSerialProtocol();
    serviceImu();
    // serviceMotors();
    serviceSonar();

    const uint32_t now = millis();

    if (static_cast<uint32_t>(now - lastTelemetryMs) >= TELEMETRY_PERIOD_MS) {
        lastTelemetryMs = now;
        printStatus();
    }

    delay(1);
}