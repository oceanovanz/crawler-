#ifndef IMU_H
#define IMU_H

#include <Adafruit_BNO08x.h>
#include <Arduino.h>

#include <cstdint>

// I2C configuration
constexpr uint8_t BNO_SDA_PIN = 21;
constexpr uint8_t BNO_SCL_PIN = 22;
constexpr uint8_t BNO_RESET_PIN = 27;

constexpr uint32_t BNO_I2C_FREQUENCY_HZ = 100000;

constexpr uint8_t BNO_ADDRESS_PRIMARY = 0x4A;
constexpr uint8_t BNO_ADDRESS_ALTERNATE = 0x4B;

// IMU configuration
constexpr uint32_t IMU_RETRY_PERIOD_MS = 2000;
constexpr uint32_t IMU_RESET_LOW_MS = 20;
constexpr uint32_t IMU_RESET_SETTLE_MS = 500;
constexpr uint32_t IMU_REPORT_INTERVAL_US = 20000;
constexpr sh2_SensorId_t ORIENTATION_REPORT = SH2_GAME_ROTATION_VECTOR;

enum class ImuInitState {
    IDLE,
    RESETTING,
    WAITING_AFTER_RESET,
};

// Lifecycle
void setupImu(bool i2cAvailable);
void serviceImu();

// Status
bool isImuOnline();
bool isOrientationValid();

uint8_t getActiveImuAddress();

// Orientation
float getYaw();
float getPitch();
float getRoll();

#endif