#include <Arduino.h>
#include <Wire.h>

#include "imu.h"
#include "motors.h"
#include "serial_protocol.h"
#include "sonar.h"

constexpr uint32_t MOTOR_PERIOD_MS = 100;  // 10 Hz
constexpr uint32_t IMU_PERIOD_MS = 20;     // 50 Hz

static uint32_t lastMotorMs = 0;
static uint32_t lastImuMs = 0;
static uint32_t lastSonarMs = 0;

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

void serviceTelemetry() {
    const uint32_t now = millis();

    if (static_cast<uint32_t>(now - lastMotorMs) >= MOTOR_PERIOD_MS) {
        lastMotorMs = now;
        printTelemetry();
    }

    if (static_cast<uint32_t>(now - lastImuMs) >= IMU_PERIOD_MS) {
        lastImuTelemetryMs = now;
        printImuTelemetry();
    }

    if (static_cast<uint32_t>(now - lastSonarMs) >= SONAR_PERIOD_MS) {
        lastSonarMs = now;
        printSonarTelemetry();
    }
}

void loop() {
    serviceSerialProtocol();
    serviceImu();
    // serviceMotors();
    serviceSonar();
    serviceTelemetry();
    delay(1);
}