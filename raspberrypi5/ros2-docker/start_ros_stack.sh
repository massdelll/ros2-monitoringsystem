
#!/bin/bash
set -e

source /opt/ros/jazzy/setup.bash
source /root/microros-workspace/install/setup.bash

# Jalankan micro-ROS Agent
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8888 &
AGENT_PID=$!

# Tunggu Agent mulai berjalan
sleep 3

# Jalankan rosbridge WebSocket
ros2 launch rosbridge_server rosbridge_websocket_launch.xml &
ROSBRIDGE_PID=$!

# Hentikan proses anak ketika container dihentikan
cleanup() {
    kill "$AGENT_PID" "$ROSBRIDGE_PID" 2>/dev/null || true
    wait
}

trap cleanup SIGTERM SIGINT

wait
