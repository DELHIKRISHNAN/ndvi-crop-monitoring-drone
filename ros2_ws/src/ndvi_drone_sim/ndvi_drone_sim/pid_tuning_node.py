"""
PID Tuning Node
===============
ROS 2 node that reads IMU + NavSat feedback from the simulated drone
and publishes velocity commands via a configurable PID controller.

This is the core node for validating PID gains in Gazebo before
deploying to the real Pixhawk.

Subscribes:
    /imu       (sensor_msgs/Imu)
    /navsat    (sensor_msgs/NavSatFix)

Publishes:
    /cmd_vel   (geometry_msgs/Twist)

Parameters (loaded from pid_params.yaml):
    kp_roll, ki_roll, kd_roll
    kp_pitch, ki_pitch, kd_pitch
    kp_yaw, ki_yaw, kd_yaw
    kp_altitude, ki_altitude, kd_altitude
    target_altitude (m)
    control_rate_hz
"""

from __future__ import annotations

import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Imu, NavSatFix


class PIDController:
    """Textbook PID with anti-windup clamping."""

    def __init__(self, kp: float = 1.0, ki: float = 0.0, kd: float = 0.0,
                 output_limits: tuple = (-1.0, 1.0)):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limits = output_limits

        self._integral = 0.0
        self._prev_error = 0.0

    def update(self, error: float, dt: float) -> float:
        if dt <= 0:
            return 0.0

        self._integral += error * dt
        # Anti-windup clamp
        self._integral = max(
            self.output_limits[0],
            min(self.output_limits[1], self._integral),
        )

        derivative = (error - self._prev_error) / dt
        self._prev_error = error

        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        return max(self.output_limits[0], min(self.output_limits[1], output))

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0


class PIDTuningNode(Node):
    """ROS 2 node for PID-based multirotor attitude + altitude control."""

    def __init__(self):
        super().__init__("pid_tuning_node")

        # Declare parameters with defaults
        self.declare_parameter("kp_roll", 1.2)
        self.declare_parameter("ki_roll", 0.01)
        self.declare_parameter("kd_roll", 0.3)

        self.declare_parameter("kp_pitch", 1.2)
        self.declare_parameter("ki_pitch", 0.01)
        self.declare_parameter("kd_pitch", 0.3)

        self.declare_parameter("kp_yaw", 0.8)
        self.declare_parameter("ki_yaw", 0.005)
        self.declare_parameter("kd_yaw", 0.1)

        self.declare_parameter("kp_altitude", 1.5)
        self.declare_parameter("ki_altitude", 0.05)
        self.declare_parameter("kd_altitude", 0.4)

        self.declare_parameter("target_altitude", 10.0)
        self.declare_parameter("control_rate_hz", 50.0)

        # Build PID controllers from params
        self.roll_pid = PIDController(
            self._p("kp_roll"), self._p("ki_roll"), self._p("kd_roll"),
        )
        self.pitch_pid = PIDController(
            self._p("kp_pitch"), self._p("ki_pitch"), self._p("kd_pitch"),
        )
        self.yaw_pid = PIDController(
            self._p("kp_yaw"), self._p("ki_yaw"), self._p("kd_yaw"),
        )
        self.alt_pid = PIDController(
            self._p("kp_altitude"), self._p("ki_altitude"), self._p("kd_altitude"),
            output_limits=(-2.0, 2.0),
        )

        self.target_altitude = self._p("target_altitude")
        rate_hz = self._p("control_rate_hz")
        self._dt = 1.0 / rate_hz

        # State
        self._current_roll = 0.0
        self._current_pitch = 0.0
        self._current_yaw = 0.0
        self._current_altitude = 0.0

        # Subscriptions
        self.create_subscription(Imu, "/imu", self._imu_callback, 10)
        self.create_subscription(NavSatFix, "/navsat", self._navsat_callback, 10)

        # Publisher
        self._cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)

        # Control loop timer
        self.create_timer(self._dt, self._control_loop)

        self.get_logger().info(
            f"PID tuning node started — target altitude {self.target_altitude}m, "
            f"control rate {rate_hz}Hz"
        )

    def _p(self, name: str):
        return self.get_parameter(name).value

    # -- callbacks ----------------------------------------------------------

    def _imu_callback(self, msg: Imu):
        q = msg.orientation
        # Convert quaternion to Euler angles
        sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z)
        cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y)
        self._current_roll = math.atan2(sinr_cosp, cosr_cosp)

        sinp = 2.0 * (q.w * q.y - q.z * q.x)
        self._current_pitch = math.asin(max(-1.0, min(1.0, sinp)))

        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self._current_yaw = math.atan2(siny_cosp, cosy_cosp)

    def _navsat_callback(self, msg: NavSatFix):
        self._current_altitude = msg.altitude

    # -- control loop -------------------------------------------------------

    def _control_loop(self):
        # Attitude errors (target = level = 0 for roll/pitch)
        roll_err = 0.0 - self._current_roll
        pitch_err = 0.0 - self._current_pitch
        yaw_err = 0.0 - self._current_yaw
        alt_err = self.target_altitude - self._current_altitude

        # PID outputs
        roll_cmd = self.roll_pid.update(roll_err, self._dt)
        pitch_cmd = self.pitch_pid.update(pitch_err, self._dt)
        yaw_cmd = self.yaw_pid.update(yaw_err, self._dt)
        alt_cmd = self.alt_pid.update(alt_err, self._dt)

        # Publish
        twist = Twist()
        twist.linear.x = pitch_cmd    # forward/back
        twist.linear.y = roll_cmd     # left/right
        twist.linear.z = alt_cmd      # up/down
        twist.angular.z = yaw_cmd     # yaw rotation
        self._cmd_pub.publish(twist)


def main(args=None):
    rclpy.init(args=args)
    node = PIDTuningNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
