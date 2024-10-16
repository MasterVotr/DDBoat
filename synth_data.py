from flask import Flask, jsonify
import math
import time
from datetime import datetime

app = Flask(__name__)

# Constants for synthetic data generation
CENTER_LAT = 48.199245
CENTER_LON = -3.014487
RADIUS = 10  # meters
ANGULAR_SPEED = (math.pi / 180) * 8  # radians per second (8 degrees per second)
EARTH_RADIUS = 6371000  # meters

start_time = time.time()

def generate_synthetic_data(elapsed_time):
    # Calculate current angle (negative for clockwise motion)
    angle = -elapsed_time * ANGULAR_SPEED  # Negative angle for clockwise motion

    # Calculate current position on the circle
    dx = RADIUS * math.cos(angle)
    dy = RADIUS * math.sin(angle)
    
    # Convert dx and dy to latitude and longitude offsets
    dlat = (dy / EARTH_RADIUS) * (180 / math.pi)
    dlon = (dx / (EARTH_RADIUS * math.cos(math.radians(CENTER_LAT)))) * (180 / math.pi)
    
    current_lat = CENTER_LAT + dlat
    current_lon = CENTER_LON + dlon

    # Calculate boat's velocity components
    vx = RADIUS * math.sin(angle) * ANGULAR_SPEED
    vy = -RADIUS * math.cos(angle) * ANGULAR_SPEED

    # Calculate compass heading from velocity components
    compass_heading_rad = math.atan2(vx, vy)
    compass_heading = (math.degrees(compass_heading_rad) + 360) % 360

    # Set goal position at the center of the circle
    goal_lat = CENTER_LAT
    goal_lon = CENTER_LON

    # Calculate bearing from current position to goal position
    lat1 = math.radians(current_lat)
    lon1 = math.radians(current_lon)
    lat2 = math.radians(goal_lat)
    lon2 = math.radians(goal_lon)
    
    delta_lon = lon2 - lon1
    
    x = math.cos(lat2) * math.sin(delta_lon)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(delta_lon)
    bearing_rad = math.atan2(x, y)
    bearing_degrees = (math.degrees(bearing_rad) + 360) % 360  # Normalize to [0,360)

    # Calculate angle to reference (difference between bearing and heading)
    angle_to_ref = (bearing_degrees - compass_heading + 360) % 360  # Angle to turn to face the goal

    # Calculate distance between current position and goal position using the haversine formula
    delta_lat = lat2 - lat1
    a = math.sin(delta_lat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_to_ref = EARTH_RADIUS * c  # Distance in meters

    # Prepare data
    data = {
        "position": {"lat": current_lat, "lon": current_lon},
        "angle_to_ref": angle_to_ref,       # Degrees
        "distance_to_ref": distance_to_ref, # Meters
        "timestamp": datetime.utcnow().isoformat(),
        "compass_heading": compass_heading  # Degrees
    }

    return data

@app.route('/api/nav_data')
def get_nav_data():
    elapsed_time = time.time() - start_time
    data = generate_synthetic_data(elapsed_time)
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
