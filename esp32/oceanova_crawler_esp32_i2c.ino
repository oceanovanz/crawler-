#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BNO08x.h>
#include <math.h>

/*
  Oceanova rapid prototype crawler controller
  Target: classic ESP32 DevKit / ESP32-WROOM-32
  Motor drivers: 2 x IBT-2 / BTS7960
  IMU: BNO085 over I2C

  Serial command protocol at 115200 baud:
    ARM
    M <left> <right>     values -1000 to +1000
    STOP                 immediate stop and disarm
    DISARM               immediate stop and disarm
    STATUS
    PING

  A valid M command must arrive at least every 500 ms while armed.

  BNO085 I2C wiring:
    VIN/VCC -> ESP32 3V3
    GND     -> ESP32 GND
    SDA     -> GPIO 21
    SCL     -> GPIO 22

  For I2C mode, do not pull P0/PS0 or P1/PS1 high.
  On many breakout boards they can simply be left unconnected.
*/

constexpr uint8_t LEFT_RPWM_PIN = 25;
constexpr uint8_t LEFT_LPWM_PIN = 26;
constexpr uint8_t RIGHT_RPWM_PIN = 32;
constexpr uint8_t RIGHT_LPWM_PIN = 33;
constexpr uint8_t DRIVER_ENABLE_PIN = 4;

constexpr uint8_t BNO_SDA_PIN = 21;
constexpr uint8_t BNO_SCL_PIN = 22;
constexpr uint32_t BNO_I2C_FREQUENCY_HZ = 100000;
constexpr uint8_t BNO_ADDRESS_PRIMARY = 0x4A;
constexpr uint8_t BNO_ADDRESS_ALTERNATE = 0x4B;

constexpr bool LEFT_MOTOR_INVERT = false;
constexpr bool RIGHT_MOTOR_INVERT = true;

constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t COMMAND_TIMEOUT_MS = 500;
constexpr uint32_t MOTOR_UPDATE_MS = 10;
constexpr uint32_t TELEMETRY_PERIOD_MS = 100;
constexpr uint32_t PWM_FREQUENCY_HZ = 20000;
constexpr uint8_t PWM_RESOLUTION_BITS = 10;
constexpr uint16_t PWM_MAX = (1U << PWM_RESOLUTION_BITS) - 1U;
constexpr int16_t RAMP_STEP = 25;
constexpr uint32_t IMU_REPORT_INTERVAL_US = 20000;
constexpr sh2_SensorId_t ORIENTATION_REPORT = SH2_GAME_ROTATION_VECTOR;

Adafruit_BNO08x bno08x(-1);
sh2_SensorValue_t sensorValue;

bool imuOnline = false;
bool orientationValid = false;
bool armed = false;
uint8_t activeImuAddress = 0;

int16_t targetLeft = 0;
int16_t targetRight = 0;
int16_t currentLeft = 0;
int16_t currentRight = 0;

float yawDeg = 0.0f;
float pitchDeg = 0.0f;
float rollDeg = 0.0f;

uint32_t lastMotorCommandMs = 0;
uint32_t lastMotorUpdateMs = 0;
uint32_t lastTelemetryMs = 0;

char commandBuffer[80];
size_t commandLength = 0;

int16_t clampCommand(int value) {
  if (value > 1000) return 1000;
  if (value < -1000) return -1000;
  return static_cast<int16_t>(value);
}

int16_t approachTarget(int16_t current, int16_t target) {
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

uint16_t commandToDuty(int16_t command) {
  const uint32_t magnitude = static_cast<uint32_t>(abs(static_cast<int>(command)));
  return static_cast<uint16_t>((magnitude * PWM_MAX) / 1000U);
}

void writeOneMotor(uint8_t rpwmPin, uint8_t lpwmPin, int16_t command, bool invert) {
  if (invert) command = -command;
  const uint16_t duty = commandToDuty(command);
  ledcWrite(rpwmPin, 0);
  ledcWrite(lpwmPin, 0);
  if (command > 0) ledcWrite(rpwmPin, duty);
  else if (command < 0) ledcWrite(lpwmPin, duty);
}

void writeMotorOutputs(int16_t left, int16_t right) {
  writeOneMotor(LEFT_RPWM_PIN, LEFT_LPWM_PIN, left, LEFT_MOTOR_INVERT);
  writeOneMotor(RIGHT_RPWM_PIN, RIGHT_LPWM_PIN, right, RIGHT_MOTOR_INVERT);
}

void disableOutputsImmediate() {
  digitalWrite(DRIVER_ENABLE_PIN, LOW);
  targetLeft = targetRight = currentLeft = currentRight = 0;
  writeMotorOutputs(0, 0);
}

void stopAndDisarm(const char *reason) {
  armed = false;
  disableOutputsImmediate();
  Serial.print("FAULT,");
  Serial.println(reason);
}

void quaternionToEuler(float qr, float qi, float qj, float qk) {
  const float sinrCosp = 2.0f * (qr * qi + qj * qk);
  const float cosrCosp = 1.0f - 2.0f * (qi * qi + qj * qj);
  rollDeg = atan2f(sinrCosp, cosrCosp) * 180.0f / PI;

  float sinp = 2.0f * (qr * qj - qk * qi);
  sinp = constrain(sinp, -1.0f, 1.0f);
  pitchDeg = asinf(sinp) * 180.0f / PI;

  const float sinyCosp = 2.0f * (qr * qk + qi * qj);
  const float cosyCosp = 1.0f - 2.0f * (qj * qj + qk * qk);
  yawDeg = atan2f(sinyCosp, cosyCosp) * 180.0f / PI;
  if (yawDeg < 0.0f) yawDeg += 360.0f;
}

bool i2cAddressResponds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void printI2cProbe(uint8_t address) {
  Serial.printf("I2C_PROBE,0x%02X,%s\n", address,
                i2cAddressResponds(address) ? "FOUND" : "NO_RESPONSE");
}

bool enableImuReport() {
  return bno08x.enableReport(ORIENTATION_REPORT, IMU_REPORT_INTERVAL_US);
}

bool startImuAtAddress(uint8_t address) {
  Serial.printf("IMU_TRY,0x%02X\n", address);
  if (!bno08x.begin_I2C(address, &Wire)) return false;
  activeImuAddress = address;
  if (!enableImuReport()) {
    Serial.printf("WARN,IMU_REPORT_ENABLE_FAILED,0x%02X\n", activeImuAddress);
    activeImuAddress = 0;
    return false;
  }
  return true;
}

bool startImu() {
  orientationValid = false;
  activeImuAddress = 0;
  printI2cProbe(BNO_ADDRESS_PRIMARY);
  printI2cProbe(BNO_ADDRESS_ALTERNATE);
  if (startImuAtAddress(BNO_ADDRESS_PRIMARY)) return true;
  if (startImuAtAddress(BNO_ADDRESS_ALTERNATE)) return true;
  return false;
}

void serviceImu() {
  if (!imuOnline) return;
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
        quaternionToEuler(sensorValue.un.gameRotationVector.real,
                          sensorValue.un.gameRotationVector.i,
                          sensorValue.un.gameRotationVector.j,
                          sensorValue.un.gameRotationVector.k);
        orientationValid = true;
        break;
      case SH2_ROTATION_VECTOR:
        quaternionToEuler(sensorValue.un.rotationVector.real,
                          sensorValue.un.rotationVector.i,
                          sensorValue.un.rotationVector.j,
                          sensorValue.un.rotationVector.k);
        orientationValid = true;
        break;
      default:
        break;
    }
  }
}

void printStatus() {
  Serial.printf("T,%lu,%.2f,%.2f,%.2f,%d,%d,%d,%d,%d\n",
                static_cast<unsigned long>(millis()), yawDeg, pitchDeg, rollDeg,
                currentLeft, currentRight, armed ? 1 : 0, imuOnline ? 1 : 0,
                orientationValid ? 1 : 0);
}

void handleCommand(const char *line) {
  if (strcmp(line, "ARM") == 0) {
    disableOutputsImmediate();
    armed = true;
    lastMotorCommandMs = millis();
    Serial.println("OK,ARMED");
    return;
  }
  if (strcmp(line, "STOP") == 0 || strcmp(line, "DISARM") == 0) {
    stopAndDisarm("OPERATOR_STOP");
    return;
  }
  if (strcmp(line, "PING") == 0) {
    Serial.println("PONG");
    return;
  }
  if (strcmp(line, "STATUS") == 0) {
    printStatus();
    return;
  }

  int left = 0;
  int right = 0;
  if (sscanf(line, "M %d %d", &left, &right) == 2) {
    if (!armed) {
      Serial.println("ERR,DISARMED");
      return;
    }
    targetLeft = clampCommand(left);
    targetRight = clampCommand(right);
    lastMotorCommandMs = millis();
    return;
  }
  Serial.println("ERR,BAD_COMMAND");
}

void serviceSerial() {
  while (Serial.available() > 0) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      commandBuffer[commandLength] = '\0';
      if (commandLength > 0) handleCommand(commandBuffer);
      commandLength = 0;
      continue;
    }
    if (commandLength < sizeof(commandBuffer) - 1U) {
      commandBuffer[commandLength++] = c;
    } else {
      commandLength = 0;
      Serial.println("ERR,COMMAND_TOO_LONG");
    }
  }
}

void serviceMotors() {
  const uint32_t now = millis();
  if (armed && static_cast<uint32_t>(now - lastMotorCommandMs) > COMMAND_TIMEOUT_MS) {
    stopAndDisarm("COMMAND_TIMEOUT");
    return;
  }
  if (static_cast<uint32_t>(now - lastMotorUpdateMs) < MOTOR_UPDATE_MS) return;
  lastMotorUpdateMs = now;
  if (!armed) {
    disableOutputsImmediate();
    return;
  }
  currentLeft = approachTarget(currentLeft, targetLeft);
  currentRight = approachTarget(currentRight, targetRight);
  writeMotorOutputs(currentLeft, currentRight);
  digitalWrite(DRIVER_ENABLE_PIN, HIGH);
}

void setup() {
  pinMode(DRIVER_ENABLE_PIN, OUTPUT);
  digitalWrite(DRIVER_ENABLE_PIN, LOW);
  Serial.begin(SERIAL_BAUD);
  delay(300);

  bool pwmOk = true;
  pwmOk &= ledcAttach(LEFT_RPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  pwmOk &= ledcAttach(LEFT_LPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  pwmOk &= ledcAttach(RIGHT_RPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  pwmOk &= ledcAttach(RIGHT_LPWM_PIN, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  writeMotorOutputs(0, 0);

  if (!pwmOk) {
    Serial.println("FATAL,PWM_SETUP_FAILED");
    while (true) {
      digitalWrite(DRIVER_ENABLE_PIN, LOW);
      delay(1000);
    }
  }

  const bool wireOk = Wire.begin(BNO_SDA_PIN, BNO_SCL_PIN, BNO_I2C_FREQUENCY_HZ);
  if (!wireOk) {
    Serial.println("WARN,I2C_BUS_SETUP_FAILED");
  } else {
    Serial.printf("OK,I2C_STARTED,SDA=%u,SCL=%u,FREQ=%lu\n",
                  BNO_SDA_PIN, BNO_SCL_PIN,
                  static_cast<unsigned long>(BNO_I2C_FREQUENCY_HZ));
  }

  imuOnline = wireOk && startImu();
  if (imuOnline) {
    Serial.printf("OK,IMU_ONLINE,ADDRESS=0x%02X\n", activeImuAddress);
  } else {
    Serial.println("WARN,IMU_NOT_FOUND_AT_0x4A_OR_0x4B");
  }

  disableOutputsImmediate();
  Serial.println("READY,DISARMED");
}

void loop() {
  serviceSerial();
  serviceImu();
  serviceMotors();
  const uint32_t now = millis();
  if (static_cast<uint32_t>(now - lastTelemetryMs) >= TELEMETRY_PERIOD_MS) {
    lastTelemetryMs = now;
    printStatus();
  }
  delay(1);
}
