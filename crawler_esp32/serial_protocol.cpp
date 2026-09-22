#include "serial_protocol.h"

#include <Arduino.h>
#include <stdio.h>
#include <string.h>

#include "imu.h"
#include "motors.h"
#include "sonar.h"

// Internal state
constexpr size_t COMMAND_BUFFER_SIZE = 80;
char commandBuffer[COMMAND_BUFFER_SIZE];
static size_t commandLength = 0;

// ---------- Internal helpers ----------

static void handleCommand(const char* line) {
    // ARM
    if (strcmp(line, "ARM") == 0) {
        armMotors();
        return;
    }

    // STOP / DISARM
    if (strcmp(line, "STOP") == 0 || strcmp(line, "DISARM") == 0) {
        stopAndDisarm("OPERATOR_STOP");
        return;
    }

    // PING
    if (strcmp(line, "PING") == 0) {
        Serial.println("PONG");
        return;
    }

    // STATUS
    if (strcmp(line, "STATUS") == 0) {
        printStatus();
        return;
    }

    // MOTOR COMMAND -> M <left> <right> (values -1000 to +1000)
    int left = 0;
    int right = 0;
    if (sscanf(line, "M %d %d", &left, &right) == 2) {
        setMotorTargets(left, right);
        return;
    }

    // Unknown command
    Serial.println("ERR,BAD_COMMAND");
}

// ---------- Public functions ----------

void setupSerialProtocol() {
    Serial.begin(SERIAL_BAUD);

    commandLength = 0;
    commandBuffer[0] = '\0';
}

void serviceSerialProtocol() {
    while (Serial.available() > 0) {
        const char c = static_cast<char>(Serial.read());

        if (c == '\n' || c == '\r') {
            if (commandLength > 0) {
                commandBuffer[commandLength] = '\0';
                handleCommand(commandBuffer);
                commandLength = 0;
            }

            continue;
        }

        if (commandLength < COMMAND_BUFFER_SIZE - 1) {
            commandBuffer[commandLength++] = c;
        } else {
            // Overflow: discard the current command.
            commandLength = 0;
            Serial.println("ERR,COMMAND_TOO_LONG");
        }
    }
}

void printTelemetry() {
    // T,<timestamp>,<left_motor>,<right_motor>,<armed>,
    Serial.printf("T,%lu,%d,%d,%d\n", static_cast<unsigned long>(millis()), getCurrentLeft(), getCurrentRight(),
                  isArmed() ? 1 : 0);
}

void printImuTelemetry() {
    // I,<timestamp>,<imu_online>,<orientation_valid>,<yaw>,<pitch>,<roll>
    Serial.printf("I,%lu,%d,%d,%.2f,%.2f,%.2f\n", static_cast<unsigned long>(millis()), isImuOnline() ? 1 : 0,
                  isOrientationValid() ? 1 : 0, getYaw(), getPitch(), getRoll());
}

void printSonarTelemetry() {
    // S,<timestamp>,<sonar_online>,<angle>,<distance>
    Serial.printf("S,%lu,%d,%d,%d\n", static_cast<unsigned long>(millis()), isSonarOnline() ? 1 : 0, getSonarAngle(),
                  getSonarDistance());
}
