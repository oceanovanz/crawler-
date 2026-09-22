#include "sonar.h"

#include <ESP32Servo.h>

// ---------- Internal state ----------

static Servo sonarServo;

static bool increasingAngle = true;
static int sonarAngle = 15;
static int sonarDistance = -1;

static uint32_t lastSonarMs = 0;

// ---------- Internal helpers ----------

int calculateDistance() {
    // Ensure trigger starts LOW
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);

    // Send 10 us trigger pulse
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    // Measure echo pulse
    const unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000);

    if (duration == 0) {  // no echo was received
        return -1;
    } else {
        return duration * WAVE_SPEED / 2;
    }
}

// ---------- Public functions ----------

void setupSonar() {
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);

    sonarServo.setPeriodHertz(50);
    sonarServo.attach(SERVO_PIN, 500, 2400);

    Serial.printf("1:   sonarDistance=%.2f, angle=%.2f\n", sonarAngle, sonarDistance);

    sonarServo.write(sonarAngle);
}

void serviceSonar() {
    const uint32_t now = millis();
    if (static_cast<uint32_t>(now - lastSonarMs) < SONAR_PERIOD_MS) {
        return;
    }
    lastSonarMs = now;

    // Trigger sonar
    sonarDistance = calculateDistance();

    // Move servo
    sonarServo.write(sonarAngle);

    // Move to next angle
    if (increasingAngle) {
        if (sonarAngle >= 165) {
            increasingAngle = false;
            sonarAngle--;
        } else {
            sonarAngle++;
        }
    } else {
        if (sonarAngle <= 15) {
            increasingAngle = true;
            sonarAngle++;
        } else {
            sonarAngle--;
        }
    }
}

// ---------- Getters ----------

bool isSonarOnline() { return true; }  // TODO

int getSonarDistance() { return sonarDistance; }

int getSonarAngle() { return sonarAngle; }