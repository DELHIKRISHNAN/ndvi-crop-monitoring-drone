"""
Detailed Closed-Loop Quadruped Controller for Raspberry Pi
==========================================================
Hardware Requirements:
1. Raspberry Pi (3, 4, or 5)
2. PCA9685 16-Channel PWM Servo Driver (connected via I2C)
3. MPU6050 6-DOF IMU (connected via I2C)
4. 8x Servo Motors (e.g., MG996R or SG90)

Dependencies:
    pip install adafruit-circuitpython-pca9685 mpu6050-raspberrypi pygame
"""

import math
import time

import board
import busio
import pygame
from adafruit_motor import servo
from adafruit_pca9685 import PCA9685
from mpu6050 import mpu6050

# ==========================================
# 1. HARDWARE INTERFACE (SERVOS & IMU)
# ==========================================

class ServoController:
    """Manages the PCA9685 board and handles angle-to-PWM conversions"""
    def __init__(self, i2c_address=0x40, frequency=50):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.pca = PCA9685(i2c, address=i2c_address)
        self.pca.frequency = frequency

        # Create 8 servo objects (modify the pins based on how you wired them)
        # Assuming layout:
        # Front-Left: Hip=0, Knee=1
        # Front-Right: Hip=2, Knee=3
        # Back-Left: Hip=4, Knee=5
        # Back-Right: Hip=6, Knee=7
        self.servos = {
            "FL_HIP": servo.Servo(self.pca.channels[0], min_pulse=500, max_pulse=2500),
            "FL_KNEE": servo.Servo(self.pca.channels[1], min_pulse=500, max_pulse=2500),
            "FR_HIP": servo.Servo(self.pca.channels[2], min_pulse=500, max_pulse=2500),
            "FR_KNEE": servo.Servo(self.pca.channels[3], min_pulse=500, max_pulse=2500),
            "BL_HIP": servo.Servo(self.pca.channels[4], min_pulse=500, max_pulse=2500),
            "BL_KNEE": servo.Servo(self.pca.channels[5], min_pulse=500, max_pulse=2500),
            "BR_HIP": servo.Servo(self.pca.channels[6], min_pulse=500, max_pulse=2500),
            "BR_KNEE": servo.Servo(self.pca.channels[7], min_pulse=500, max_pulse=2500),
        }

        # Calibration offsets (Degrees to add/subtract to center cheap servos)
        self.offsets = {
            "FL_HIP": 0.0, "FL_KNEE": 0.0,
            "FR_HIP": 0.0, "FR_KNEE": 0.0,
            "BL_HIP": 0.0, "BL_KNEE": 0.0,
            "BR_HIP": 0.0, "BR_KNEE": 0.0,
        }

    def set_angle(self, joint_name, angle):
        """Sets a servo to a specific angle, applying offsets and safety bounds"""
        target_angle = angle + self.offsets[joint_name]

        # Clip to physical servo limits (0 to 180)
        target_angle = max(0, min(180, target_angle))

        try:
            self.servos[joint_name].angle = target_angle
        except Exception as e:
            print(f"Error setting {joint_name} to {target_angle}: {e}")

class IMUController:
    """Reads Pitch and Roll from the MPU6050 accelerometer/gyro"""
    def __init__(self, i2c_address=0x68):
        try:
            self.sensor = mpu6050(i2c_address)
            self.available = True
        except Exception as e:
            print(f"IMU not found at {hex(i2c_address)}. Error: {e}")
            self.available = False

    def get_angles(self):
        """Returns (pitch, roll) in degrees calculated from accelerometer data"""
        if not self.available:
            return 0.0, 0.0

        try:
            accel_data = self.sensor.get_accel_data()
            x = accel_data['x']
            y = accel_data['y']
            z = accel_data['z']

            # Calculate Pitch and Roll from gravity vector
            pitch = math.degrees(math.atan2(y, math.sqrt(x*x + z*z)))
            roll = math.degrees(math.atan2(-x, z))
            return pitch, roll
        except Exception:
            return 0.0, 0.0


# ==========================================
# 2. ALGORITHM LOGIC (PID, IK, GAIT)
# ==========================================

class PIDController:
    def __init__(self, kp, ki, kd, setpoint=0.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = setpoint
        self.integral = 0.0
        self.prev_error = 0.0
        self.last_time = time.time()

    def update(self, current_value):
        now = time.time()
        dt = now - self.last_time
        if dt <= 0.0:
            dt = 0.01

        error = self.setpoint - current_value
        self.integral += error * dt
        # Prevent integral windup (limit to +/- 30mm of correction)
        self.integral = max(-30, min(30, self.integral))

        derivative = (error - self.prev_error) / dt
        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)

        self.prev_error = error
        self.last_time = now
        return output

class LegIK:
    def __init__(self, hip_length=50.0, knee_length=50.0):
        self.L1 = hip_length
        self.L2 = knee_length

    def solve(self, x, z):
        distance = math.sqrt(x**2 + z**2)
        if distance > (self.L1 + self.L2):
            distance = self.L1 + self.L2 - 0.01

        cos_knee = (self.L1**2 + self.L2**2 - distance**2) / (2 * self.L1 * self.L2)
        knee_rad = math.pi - math.acos(cos_knee)

        alpha = math.acos((self.L1**2 + distance**2 - self.L2**2) / (2 * self.L1 * distance))
        theta = math.atan2(x, abs(z))
        hip_rad = theta + alpha

        # Return angles mapped to 0-180 servo range.
        # (90 is usually straight down for hip, and 90 is straight line for knee)
        hip_deg = 90 + math.degrees(hip_rad)
        knee_deg = 90 - math.degrees(knee_rad)

        return hip_deg, knee_deg


# ==========================================
# 3. MAIN ROBOT CONTROLLER
# ==========================================

class QuadrupedRobot:
    def __init__(self):
        # Initialize Hardware
        self.servos = ServoController()
        self.imu = IMUController()

        # Initialize Joystick (pygame)
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print(f"Joystick detected: {self.joystick.get_name()}")
        else:
            print("No joystick detected. Falling back to default speed.")

        # Dimensions and Kinematics
        self.ik = LegIK(hip_length=50.0, knee_length=50.0)
        self.BASE_HEIGHT = 70.0
        self.MAX_STEP_LENGTH = 40.0
        self.STEP_HEIGHT = 25.0

        # Posture Control (Tuning these values is critical for real hardware)
        self.pitch_pid = PIDController(kp=1.2, ki=0.1, kd=0.05, setpoint=0.0)
        self.roll_pid = PIDController(kp=1.2, ki=0.1, kd=0.05, setpoint=0.0)

    def get_trot_trajectory(self, phase, step_length):
        """Generates raw X, Z foot coordinates for a given phase (0.0 to 1.0) and step length"""
        if phase < 0.5: # Swing
            t = phase * 2.0
            x = -step_length / 2.0 + (step_length * t)
            z = self.BASE_HEIGHT - (math.sin(t * math.pi) * self.STEP_HEIGHT)
        else: # Stance
            t = (phase - 0.5) * 2.0
            x = step_length / 2.0 - (step_length * t)
            z = self.BASE_HEIGHT
        return x, z

    def run(self):
        print("Starting Quadruped Closed-Loop Control with Joystick...")

        try:
            # We track phase continuously to allow dynamic speed and reverse
            current_phase = 0.0
            last_time = time.time()

            while True:
                # 1. TIME & JOYSTICK TRACKING (Fixed frequency loop)
                loop_start = time.time()
                dt = loop_start - last_time
                last_time = loop_start

                # Default values if no joystick
                forward_axis = 0.0
                turn_axis = 0.0

                if self.joystick:
                    pygame.event.pump()
                    # Axis 1 = Left Stick Y (Up/Down) -> Forward speed
                    # Axis 3 = Right Stick X (Left/Right) -> Turn (may vary by controller)
                    forward_axis = -self.joystick.get_axis(1) # Invert so Up is positive
                    turn_axis = self.joystick.get_axis(3)

                    # Apply small deadzone
                    # Apply small deadzone
                    # Apply small deadzone
                    if abs(forward_axis) < 0.1:
                        forward_axis = 0.0

                    if abs(turn_axis) < 0.1:
                        turn_axis = 0.0
                else:
                    # If no joystick, just walk forward slowly
                    forward_axis = 0.5

                # Max speed is ~2 cycles per second
                current_phase = (current_phase + (forward_axis * 2.0 * dt)) % 1.0

                # Diagonal pairs
                phase_pair1 = current_phase                 # FL & BR
                phase_pair2 = (current_phase + 0.5) % 1.0   # FR & BL

                # 2. READ IMU
                pitch, roll = self.imu.get_angles()

                # 3. CALCULATE PID CORRECTIONS (Outputs in millimeters of leg extension)
                pitch_corr = self.pitch_pid.update(pitch)
                roll_corr = self.roll_pid.update(roll)

                # Calculate Step Lengths based on turning
                # If turning right (turn_axis > 0), left legs take longer steps
                left_step_len = self.MAX_STEP_LENGTH * (abs(forward_axis) + turn_axis)
                right_step_len = self.MAX_STEP_LENGTH * (abs(forward_axis) - turn_axis)

                # Cap step lengths to prevent physical overextension
                left_step_len = max(0.0, min(self.MAX_STEP_LENGTH, left_step_len))
                right_step_len = max(0.0, min(self.MAX_STEP_LENGTH, right_step_len))

                # If moving backward, the trajectory plays backwards automatically because
                # current_phase will decrement, but we need step lengths to remain positive distances

                # 4. GENERATE BASE TRAJECTORY FOR EACH LEG
                x_fl, z1 = self.get_trot_trajectory(phase_pair1, left_step_len)
                x_br, _  = self.get_trot_trajectory(phase_pair1, right_step_len)

                x_fr, z2 = self.get_trot_trajectory(phase_pair2, right_step_len)
                x_bl, _  = self.get_trot_trajectory(phase_pair2, left_step_len)

                # 5. APPLY CORRECTIONS & CALCULATE IK FOR ALL 4 LEGS

                # Front-Left (Pitch extends, Roll retracts)
                fl_z = z1 + pitch_corr - roll_corr
                fl_hip, fl_knee = self.ik.solve(x_fl, fl_z)

                # Front-Right (Pitch extends, Roll extends)
                fr_z = z2 + pitch_corr + roll_corr
                fr_hip, fr_knee = self.ik.solve(x_fr, fr_z)

                # Back-Left (Pitch retracts, Roll retracts)
                bl_z = z2 - pitch_corr - roll_corr
                bl_hip, bl_knee = self.ik.solve(x_bl, bl_z)

                # Back-Right (Pitch retracts, Roll extends)
                br_z = z1 - pitch_corr + roll_corr
                br_hip, br_knee = self.ik.solve(x_br, br_z)

                # 6. SEND TO HARDWARE SERVOS
                self.servos.set_angle("FL_HIP", fl_hip)
                self.servos.set_angle("FL_KNEE", fl_knee)

                # Right side servos are typically mounted in mirror orientation.
                # If they are mirrored, we invert the angle (180 - angle)
                self.servos.set_angle("FR_HIP", 180 - fr_hip)
                self.servos.set_angle("FR_KNEE", 180 - fr_knee)

                self.servos.set_angle("BL_HIP", bl_hip)
                self.servos.set_angle("BL_KNEE", bl_knee)

                self.servos.set_angle("BR_HIP", 180 - br_hip)
                self.servos.set_angle("BR_KNEE", 180 - br_knee)

                # 7. REGULATE LOOP FREQUENCY (~50Hz)
                elapsed = time.time() - loop_start
                if elapsed < 0.02:
                    time.sleep(0.02 - elapsed)

        except KeyboardInterrupt:
            print("\nShutting down robot. Moving to rest position.")
            # Send to rest position (base height, center X)
            rest_hip, rest_knee = self.ik.solve(0, self.BASE_HEIGHT)
            for leg in ["FL", "BL"]:
                self.servos.set_angle(f"{leg}_HIP", rest_hip)
                self.servos.set_angle(f"{leg}_KNEE", rest_knee)
            for leg in ["FR", "BR"]:
                self.servos.set_angle(f"{leg}_HIP", 180 - rest_hip)
                self.servos.set_angle(f"{leg}_KNEE", 180 - rest_knee)
            time.sleep(1)

if __name__ == "__main__":
    robot = QuadrupedRobot()
    robot.run()
