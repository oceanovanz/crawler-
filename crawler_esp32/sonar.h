#ifndef SONAR_H
#define SONAR_H

#include <cstdint>

static const int TRIG_PIN = 5;
static const int ECHO_PIN = 18;
static const int SERVO_PIN = 16;

static const float WAVE_SPEED = 0.343;  // mm / µs
static const uint32_t SONAR_PERIOD_MS = 60;

int calculateDistance();

void setupSonar();
void serviceSonar();

bool isSonarOnline();
int getSonarDistance();
int getSonarAngle();

#endif