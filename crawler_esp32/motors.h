#ifndef MOTORS_H
#define MOTORS_H

#include <Arduino.h>

#include <cstdint>

// Motor pins
constexpr uint8_t LEFT_RPWM_PIN = 25;
constexpr uint8_t LEFT_LPWM_PIN = 26;
constexpr uint8_t RIGHT_RPWM_PIN = 32;
constexpr uint8_t RIGHT_LPWM_PIN = 33;
constexpr uint8_t DRIVER_ENABLE_PIN = 4;

// Motor configuration
constexpr bool LEFT_MOTOR_INVERT = false;
constexpr bool RIGHT_MOTOR_INVERT = true;

constexpr uint32_t COMMAND_TIMEOUT_MS = 500;
constexpr uint32_t MOTOR_UPDATE_MS = 10;

constexpr uint32_t PWM_FREQUENCY_HZ = 20000;
constexpr uint8_t PWM_RESOLUTION_BITS = 10;

constexpr uint16_t PWM_MAX = (1U << PWM_RESOLUTION_BITS) - 1U;

constexpr int16_t RAMP_STEP = 25;

// Lifecycle
bool setupMotors();
void serviceMotors();

// Commands
void armMotors();
void disarmMotors();
void stopAndDisarm(const char* reason);

void setMotorTargets(int16_t left, int16_t right);

// Status
bool isArmed();

int16_t getTargetLeft();
int16_t getTargetRight();

int16_t getCurrentLeft();
int16_t getCurrentRight();

#endif