"""
Simulation Launch File
======================
Brings up the Gazebo Ignition farmland world alongside the ROS 2 bridge
and the PID tuning node in a single ``ros2 launch`` invocation.

Usage:
    ros2 launch ndvi_drone_sim sim_launch.py
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
)
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("ndvi_drone_sim")

    # --- Launch arguments ---------------------------------------------------
    world_arg = DeclareLaunchArgument(
        "world",
        default_value=PathJoinSubstitution([pkg_share, "worlds", "farmland.sdf"]),
        description="Path to the SDF world file",
    )

    use_sim_time_arg = DeclareLaunchArgument(
        "use_sim_time",
        default_value="true",
        description="Use simulation clock",
    )

    # --- Gazebo Ignition ----------------------------------------------------
    gz_sim = ExecuteProcess(
        cmd=[
            "gz",
            "sim",
            "-r",
            LaunchConfiguration("world"),
        ],
        output="screen",
    )

    # --- ROS ↔ Gazebo bridge ------------------------------------------------
    ros_gz_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/imu@sensor_msgs/msg/Imu[gz.msgs.IMU",
            "/navsat@sensor_msgs/msg/NavSatFix[gz.msgs.NavSat",
            "/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist",
        ],
        output="screen",
        parameters=[{"use_sim_time": LaunchConfiguration("use_sim_time")}],
    )

    # --- PID tuning node ----------------------------------------------------
    pid_node = Node(
        package="ndvi_drone_sim",
        executable="pid_tuning_node",
        name="pid_tuning_node",
        output="screen",
        parameters=[
            {"use_sim_time": LaunchConfiguration("use_sim_time")},
            PathJoinSubstitution([pkg_share, "config", "pid_params.yaml"]),
        ],
    )

    return LaunchDescription(
        [
            world_arg,
            use_sim_time_arg,
            gz_sim,
            ros_gz_bridge,
            pid_node,
        ]
    )
