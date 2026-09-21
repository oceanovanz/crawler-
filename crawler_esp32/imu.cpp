#include "imu.h"

// -----------------------------------------------------------------------------
// Internal state
// -----------------------------------------------------------------------------

static Adafruit_BNO08x bno08x(-1);
static sh2_SensorValue_t sensorValue;

static ImuInitState imuInitState = ImuInitState::IDLE;

static uint32_t imuResetStartMs = 0;
static uint8_t activeImuAddress = 0;
static uint32_t lastImuRetryMs = 0;

static bool imuOnline = false;
static bool orientationValid = false;
static float yawDeg = 0.0f;
static float pitchDeg = 0.0f;
static float rollDeg = 0.0f;

// ---------- Internal helpers ----------

static bool i2cAddressResponds(uint8_t address) {
    Wire.beginTransmission(address);
    return Wire.endTransmission() == 0;
}

static void printI2cProbe(uint8_t address) {
    Serial.printf("I2C_PROBE,0x%02X,%s\n", address, i2cAddressResponds(address) ? "FOUND" : "NO_RESPONSE");
}

static bool enableImuReport() { return bno08x.enableReport(ORIENTATION_REPORT, IMU_REPORT_INTERVAL_US); }

static void beginImuHardwareReset() {
    Serial.println("IMU_HARD_RESET");

    pinMode(BNO_RESET_PIN, OUTPUT);
    digitalWrite(BNO_RESET_PIN, LOW);
}

static void finishImuHardwareReset() {
    digitalWrite(BNO_RESET_PIN, HIGH);

    Serial.println("IMU_RESET_RELEASED");
}

static bool startImuAtAddress(uint8_t address) {
    Serial.printf("IMU_TRY,0x%02X\n", address);

    if (!bno08x.begin_I2C(address, &Wire)) {
        return false;
    }

    activeImuAddress = address;

    if (!enableImuReport()) {
        Serial.printf("WARN,IMU_REPORT_ENABLE_FAILED,0x%02X\n", activeImuAddress);
        activeImuAddress = 0;
        return false;
    }

    return true;
}

static bool startImu() {
    Serial.println("IMU_START_ATTEMPT");

    orientationValid = false;
    activeImuAddress = 0;
    imuOnline = false;

    const bool primaryPresent = i2cAddressResponds(BNO_ADDRESS_PRIMARY);
    const bool alternatePresent = i2cAddressResponds(BNO_ADDRESS_ALTERNATE);

    Serial.printf("I2C_PROBE,0x4A,%s\n", primaryPresent ? "FOUND" : "NO_RESPONSE");
    Serial.printf("I2C_PROBE,0x4B,%s\n", alternatePresent ? "FOUND" : "NO_RESPONSE");

    if (primaryPresent) {
        return startImuAtAddress(BNO_ADDRESS_PRIMARY);
    }

    if (alternatePresent) {
        return startImuAtAddress(BNO_ADDRESS_ALTERNATE);
    }

    return false;
}

static void quaternionToEuler(float qr, float qi, float qj, float qk) {
    const float sinrCosp = 2.0f * (qr * qi + qj * qk);
    const float cosrCosp = 1.0f - 2.0f * (qi * qi + qj * qj);

    rollDeg = atan2f(sinrCosp, cosrCosp) * 180.0f / PI;

    float sinp = 2.0f * (qr * qj - qk * qi);
    sinp = constrain(sinp, -1.0f, 1.0f);

    pitchDeg = asinf(sinp) * 180.0f / PI;

    const float sinyCosp = 2.0f * (qr * qk + qi * qj);
    const float cosyCosp = 1.0f - 2.0f * (qj * qj + qk * qk);

    yawDeg = atan2f(sinyCosp, cosyCosp) * 180.0f / PI;

    if (yawDeg < 0.0f) {
        yawDeg += 360.0f;
    }
}

// ---------- Public functions ----------

void setupImu(bool i2cAvailable) {
    imuOnline = false;
    imuInitState = ImuInitState::IDLE;

    if (!i2cAvailable) {
        Serial.println("WARN,IMU_I2C_UNAVAILABLE");
        return;
    }

    lastImuRetryMs = millis() - IMU_RETRY_PERIOD_MS;

    Serial.println("IMU_INIT_SCHEDULED");
}

void serviceImu() {
    const uint32_t now = millis();

    // IMU working normally
    if (imuOnline) {
        if (bno08x.wasReset()) {
            orientationValid = false;

            if (!enableImuReport()) {
                imuOnline = false;
                activeImuAddress = 0;
                Serial.println("WARN,IMU_REPORT_RESTART_FAILED");
                return;
            }

            Serial.println("WARN,IMU_RESET_RECOVERED");
        }

        while (bno08x.getSensorEvent(&sensorValue)) {
            switch (sensorValue.sensorId) {
                case SH2_GAME_ROTATION_VECTOR:
                    quaternionToEuler(sensorValue.un.gameRotationVector.real, sensorValue.un.gameRotationVector.i,
                                      sensorValue.un.gameRotationVector.j, sensorValue.un.gameRotationVector.k);
                    orientationValid = true;
                    break;

                case SH2_ROTATION_VECTOR:
                    quaternionToEuler(sensorValue.un.rotationVector.real, sensorValue.un.rotationVector.i,
                                      sensorValue.un.rotationVector.j, sensorValue.un.rotationVector.k);
                    orientationValid = true;
                    break;

                default:
                    break;
            }
        }
        return;
    }

    // IMU is currently being held in reset
    if (imuInitState == ImuInitState::RESETTING) {
        if (static_cast<uint32_t>(now - imuResetStartMs) >= IMU_RESET_LOW_MS) {
            finishImuHardwareReset();

            imuResetStartMs = now;
            imuInitState = ImuInitState::WAITING_AFTER_RESET;
        }
        return;
    }

    // Reset has been released; wait for BNO085 to boot
    if (imuInitState == ImuInitState::WAITING_AFTER_RESET) {
        if (static_cast<uint32_t>(now - imuResetStartMs) >= IMU_RESET_SETTLE_MS) {
            Serial.println("IMU_RESET_SETTLED");

            imuOnline = startImu();
            if (imuOnline) {
                Serial.printf("OK,IMU_ONLINE,ADDRESS=0x%02X\n", activeImuAddress);
                imuInitState = ImuInitState::IDLE;
            } else {
                Serial.println("WARN,IMU_RETRY_FAILED");
                imuInitState = ImuInitState::IDLE;
            }
        }

        return;
    }

    // Waiting for next retry
    if (imuInitState == ImuInitState::IDLE) {
        if (static_cast<uint32_t>(now - lastImuRetryMs) < IMU_RETRY_PERIOD_MS) {
            return;
        }
        lastImuRetryMs = now;

        Serial.println("IMU_OFFLINE_RETRY");

        beginImuHardwareReset();

        imuResetStartMs = now;
        imuInitState = ImuInitState::RESETTING;
        return;
    }
}

// ---------- Getters ----------

bool isImuOnline() { return imuOnline; }

bool isOrientationValid() { return orientationValid; }

uint8_t getActiveImuAddress() { return activeImuAddress; }

float getYaw() { return yawDeg; }

float getPitch() { return pitchDeg; }

float getRoll() { return rollDeg; }