#ifndef SERIAL_PROTOCOL_H
#define SERIAL_PROTOCOL_H

#include <cstdint>

#define SERIAL_BAUD 115200

void printTelemetry();
void printImuTelemetry();
void printSonarTelemetry();

void setupSerialProtocol();
void serviceSerialProtocol();

void printStatus();

#endif