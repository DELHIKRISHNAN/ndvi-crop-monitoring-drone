import math
import time


class SimplePID:
    """A basic PID controller for closed-loop feedback"""
    def __init__(self, kp, ki, kd, setpoint=0.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = setpoint
        self.integral = 0.0
        self.prev_error = 0.0
        self.last_time = time.time()

    def update(self, current_value):
        current_time = time.time()
        dt = current_time - self.last_time
        if dt <= 0.0:
            dt = 0.01

        error = self.setpoint - current_value
        self.integral += error * dt
        derivative = (error - self.prev_error) / dt

        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)

        self.prev_error = error
        self.last_time = current_time
        return output

class QuadrupedLeg:
    def __init__(self, name, hip_length, knee_length, is_front, is_left):
        self.name = name
        self.L1 = hip_length
        self.L2 = knee_length
        self.is_front = is_front
        self.is_left = is_left

    def calculate_ik(self, x, z):
        """
        Inverse Kinematics for a 2-DOF leg.
        Given a target (x, z) foot position relative to the hip, returns (hip_angle, knee_angle).
        """
        distance_to_target = math.sqrt(x**2 + z**2)

        # Prevent impossible reaches
        if distance_to_target > (self.L1 + self.L2):
            distance_to_target = self.L1 + self.L2 - 0.01

        # Angle of the knee (Law of Cosines)
        cos_knee = (self.L1**2 + self.L2**2 - distance_to_target**2) / (2 * self.L1 * self.L2)
        knee_angle_rad = math.pi - math.acos(cos_knee)

        # Angle of the hip
        alpha = math.acos((self.L1**2 + distance_to_target**2 - self.L2**2) / (2 * self.L1 * distance_to_target))
        theta = math.atan2(x, abs(z))
        hip_angle_rad = theta + alpha

        return math.degrees(hip_angle_rad), math.degrees(knee_angle_rad)

class ClosedLoopQuadruped:
    def __init__(self):
        # Physical dimensions (mm)
        self.HIP_LENGTH = 50.0
        self.KNEE_LENGTH = 50.0
        self.BASE_HEIGHT = 70.0 # Normal standing height

        # Legs
        self.legs = {
            "FL": QuadrupedLeg("Front-Left", self.HIP_LENGTH, self.KNEE_LENGTH, is_front=True, is_left=True),
            "FR": QuadrupedLeg("Front-Right", self.HIP_LENGTH, self.KNEE_LENGTH, is_front=True, is_left=False),
            "BL": QuadrupedLeg("Back-Left", self.HIP_LENGTH, self.KNEE_LENGTH, is_front=False, is_left=True),
            "BR": QuadrupedLeg("Back-Right", self.HIP_LENGTH, self.KNEE_LENGTH, is_front=False, is_left=False)
        }

        # Gait parameters
        self.step_length = 40.0
        self.step_height = 25.0
        self.gait_speed = 1.0

        # Posture Controllers (Closed Loop PID)
        # We want pitch and roll to be 0 (perfectly level)
        self.pitch_pid = SimplePID(kp=0.5, ki=0.01, kd=0.1, setpoint=0.0)
        self.roll_pid = SimplePID(kp=0.5, ki=0.01, kd=0.1, setpoint=0.0)

    def read_imu(self):
        """
        Simulates reading an IMU (Inertial Measurement Unit like MPU6050).
        In a real robot, you would read the actual I2C sensor here.
        Returns: (pitch_angle_degrees, roll_angle_degrees)
        """
        # Simulating an external disturbance: the robot is pitching forward 5 degrees and rolling right 3 degrees
        simulated_pitch = 5.0
        simulated_roll = -3.0
        return simulated_pitch, simulated_roll

    def get_foot_trajectory(self, phase_time):
        """Generates standard Trot Gait (X, Z) coordinates"""
        if phase_time < 0.5:
            # SWING PHASE
            t = phase_time * 2.0
            x = -self.step_length / 2.0 + (self.step_length * t)
            z = self.BASE_HEIGHT - (math.sin(t * math.pi) * self.step_height)
        else:
            # STANCE PHASE
            t = (phase_time - 0.5) * 2.0
            x = self.step_length / 2.0 - (self.step_length * t)
            z = self.BASE_HEIGHT
        return x, z

    def apply_posture_correction(self, leg, base_x, base_z, pitch_correction, roll_correction):
        """
        Modifies the leg's Z-height based on the PID output to maintain a level body.
        - Pitch correction > 0 means the robot is pitching forward, so we need to extend front legs and retract back legs.
        - Roll correction > 0 means the robot is rolling right, so we need to extend right legs and retract left legs.
        """
        z_adj = base_z

        # Apply Pitch Correction
        if leg.is_front:
            z_adj += pitch_correction
        else:
            z_adj -= pitch_correction

        # Apply Roll Correction
        if leg.is_left:
            z_adj -= roll_correction
        else:
            z_adj += roll_correction

        return base_x, z_adj

    def run_control_loop(self):
        print("Starting CLOSED-LOOP trot gait... Press Ctrl+C to stop.")
        start_time = time.time()

        try:
            while True:
                current_time = time.time() - start_time
                cycle_time = (current_time * self.gait_speed) % 1.0

                # Diagonal pairs for Trot Gait
                phase_1 = cycle_time                 # FL & BR
                phase_2 = (cycle_time + 0.5) % 1.0   # FR & BL

                # 1. READ SENSORS (Feedback)
                current_pitch, current_roll = self.read_imu()

                # 2. CALCULATE CORRECTIONS (PID)
                # The PID outputs how many millimeters to adjust the legs to fix the angle error
                pitch_correction = self.pitch_pid.update(current_pitch)
                roll_correction = self.roll_pid.update(current_roll)

                # 3. CALCULATE BASE TRAJECTORY
                x1, z1 = self.get_foot_trajectory(phase_1)
                x2, z2 = self.get_foot_trajectory(phase_2)

                # 4. APPLY CLOSED-LOOP CORRECTIONS & INVERSE KINEMATICS
                angles = {}
                for leg_name, leg in self.legs.items():
                    # Determine which phase this leg is in
                    x_base, z_base = (x1, z1) if leg_name in ["FL", "BR"] else (x2, z2)

                    # Apply the IMU feedback correction to the Z height
                    x_corr, z_corr = self.apply_posture_correction(leg, x_base, z_base, pitch_correction, roll_correction)

                    # Calculate final servo angles
                    hip, knee = leg.calculate_ik(x_corr, z_corr)
                    angles[leg_name] = (hip, knee)

                # 5. SEND TO MOTORS
                print(f"IMU(P:{current_pitch:5.1f} R:{current_roll:5.1f}) | "
                      f"PID_Adj(P:{pitch_correction:5.1f}mm R:{roll_correction:5.1f}mm) | "
                      f"FL_Z:{z1 + pitch_correction - roll_correction:5.1f}mm")

                time.sleep(0.05) # 20 Hz control loop

        except KeyboardInterrupt:
            print("Stopping robot.")

if __name__ == "__main__":
    bot = ClosedLoopQuadruped()
    bot.run_control_loop()
