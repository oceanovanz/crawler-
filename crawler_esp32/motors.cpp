#include "motors.h"

// Internal state
static int16_t targetLeft = 0;
static int16_t targetRight = 0;

static int16_t currentLeft = 0;
static int16_t currentRight = 0;

static bool armed = false;

static uint32_t lastMotorCommandMs = 0;
static uint32_t lastMotorUpdateMs = 0;

// ---------- Internal helpers ----------

static int16_t clampCommand(int value) {
    if (value > 1000) return 1000;
    if (value < -1000) return -1000;

    return static_cast<int16_t>(value);
}

static int16_t approachTarget(int16_t current, int16_t target) {
    if (current < target) {
        const int32_t next = static_cast<int32_t>(current) + RAMP_STEP;
        return static_cast<int16_t>(next > target ? target : next);
    }

    if (current > target) {
        const int32_t next = static_cast<int32_t>(current) - RAMP_STEP;
        return static_cast<int16_t>(next < target ? target : next);
    }

    return current;
}

static uint16_t commandToDuty(int16_t command) {
    const uint32_t magnitude = static_cast<uint32_t>(abs(static_cast<int>(command)));
    return static_cast<uint16_t>((magnitude * PWM_MAX) / 1000U);
}

static void writeOneMotor(uint8_t rpwmPin, uint8_t lpwmPin, int16_t command, bool invert) {
    if (invert) {
        command = -command;
    }

    const uint16_t duty = commandToDuty(command);

    ledcWrite(rpwmPin, 0);
    ledcWrite(lpwmPin, 0);

    if (command > 0) {
        ledcWrite(rpwmPin, duty);
    } else if (command < 0) {
        ledcWrite(lpwmPin, duty);
    }
}

static void writeMotorOutputs(int16_t left, int16_t right) {
    writeOneMotor(LEFT_RPWM_PIN, LEFT_LPWM_PIN, left, LEFT_MOTOR_INVERT);
    writeOneMotor(RIGHT_RPWM_PIN, RIGHT_LPWM_PIN, right, RIGHT_MOTOR_INVERT);
}

// ---------- Public functions ----------

bool setupMotors() {
    pinMode(DRIVER_ENABLE_PIN, OUTPUT);
    digitalWrite(DRIVER_ENABLE_PIN, LOW);

    bool pwmOk = true;

    pwmOk &= ledcAttach(LEFT_RPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
    pwmOk &= ledcAttach(LEFT_LPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
    pwmOk &= ledcAttach(RIGHT_RPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
    pwmOk &= ledcAttach(RIGHT_LPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);

    writeMotorOutputs(0, 0);

    return pwmOk;
}

void armMotors() {
    // Start from zero whenever we arm.
    targetLeft = 0;
    targetRight = 0;

    currentLeft = 0;
    currentRight = 0;

    writeMotorOutputs(0, 0);

    armed = true;

    lastMotorCommandMs = millis();

    Serial.println("OK,ARMED");
}

void disarmMotors() {
    armed = false;

    targetLeft = 0;
    targetRight = 0;

    currentLeft = 0;
    currentRight = 0;

    digitalWrite(DRIVER_ENABLE_PIN, LOW);
    writeMotorOutputs(0, 0);
}

void stopAndDisarm(const char* reason) {
    disarmMotors();

    Serial.print("FAULT,");
    Serial.println(reason);
}

void setMotorTargets(int16_t left, int16_t right) {
    if (!armed) {
        Serial.println("ERR,DISARMED");
        return;
    }

    targetLeft = clampCommand(left);
    targetRight = clampCommand(right);

    lastMotorCommandMs = millis();
}

void serviceMotors() {
    const uint32_t now = millis();

    // Safety watchdog
    if (armed && static_cast<uint32_t>(now - lastMotorCommandMs) > COMMAND_TIMEOUT_MS) {
        stopAndDisarm("COMMAND_TIMEOUT");
        return;
    }

    // Motor update rate
    if (static_cast<uint32_t>(now - lastMotorUpdateMs) < MOTOR_UPDATE_MS) {
        return;
    }

    lastMotorUpdateMs = now;

    if (!armed) {
        writeMotorOutputs(0, 0);
        digitalWrite(DRIVER_ENABLE_PIN, LOW);

        return;
    }

    // Smoothly approach targets
    currentLeft = approachTarget(currentLeft, targetLeft);
    currentRight = approachTarget(currentRight, targetRight);

    writeMotorOutputs(currentLeft, currentRight);
    digitalWrite(DRIVER_ENABLE_PIN, HIGH);
}

// ---------- Getters ----------

bool isArmed() { return armed; }

int16_t getTargetLeft() { return targetLeft; }

int16_t getTargetRight() { return targetRight; }

int16_t getCurrentLeft() { return currentLeft; }

int16_t getCurrentRight() { return currentRight; }