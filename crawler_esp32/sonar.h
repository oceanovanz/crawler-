#ifndef SONAR_H
#define SONAR_H

#include <cstdint>

static const int TRIG_PIN = 5;
static const int ECHO_PIN = 18;
static const int SERVO_PIN = 16;

int calculateDistance();

void setupSonar();
void serviceSonar();

bool isSonarOnline();
int getSonarDistance();
int getSonarAngle();

#endif