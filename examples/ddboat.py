# ddboat_utils.py
# python 3.5 so no print f"
"""
DDBOAT Utility Module

This module provides utility functions for interacting with the DDBOAT platform.
It includes functions for GPS data handling, IMU data acquisition,
compass calibration and heading calculation, motor control, and data logging to GPX and KML files.

Dependencies:
- gps_driver_v2
- imu9_driver_v2
- arduino_driver_v2
- pyproj
- numpy
- gpxpy
- simplekml

Ensure that the 'drivers-ddboat-v2' directory is in the same directory as this module
or adjust the sys.path accordingly.


"""
import signal

import sys
import os
import time
import numpy as np
from pyproj import Proj
import gpxpy.gpx
import simplekml
from datetime import datetime
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
latest_nav_data = {}

# Access to the drivers (adjust the path as needed)
sys.path.append(os.path.join(os.path.dirname(__file__), 'drivers-ddboat-v2'))

import gps_driver_v2 as gpddrv
import imu9_driver_v2 as imudrv
import arduino_driver_v2 as arddrv

# Constants for UTM projection (adjust zone as needed)
UTM_ZONE = 30  # For Brittany, France

# Initialize the projection from WGS84 to UTM
projDegree2Meter = Proj(
    proj='utm',
    zone=UTM_ZONE,
    ellps='WGS84',
    datum='WGS84',
    units='m',
    no_defs=True
)

# Magnetic correction
b = np.array([[6.],[1468.],[-4455.]])
A = np.array([[[-73.05261869,-5.55853209,-7.24944167],[-1.10974578,61.19152157,4.77293562],[8.48208413,1.2818979,-66.35225166]]])
A_inv = np.linalg.inv(A[0])  # A is a 3D array, so we need to use A[0]

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/nav_data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            # Use global latest_nav_data
            global latest_nav_data
            self.wfile.write(json.dumps(latest_nav_data).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'404 Not Found')


def run_server(port=8000):
    server_address = ('0.0.0.0', port)  # Changed from '' to '0.0.0.0'
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print("Server running on port {}".format(port))
    httpd.serve_forever()

class Coordinate:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def distance_to(self, other: 'Coordinate') -> float:
        """
        Calculate the Euclidean distance to another coordinate.
        
        Parameters:
        - other (Coordinate): The other coordinate.

        Returns:
        - float: Distance to the other coordinate.
        """
        return np.hypot(self.x - other.x, self.y - other.y)

    def angle_to(self, other: 'Coordinate', current_heading: float) -> float:
        """
        Calculate the angle from the current heading to another coordinate.
        
        Parameters:
        - other (Coordinate): The other coordinate.
        - current_heading (float): Current heading of the boat in degrees.

        Returns:
        - float: Angle from current heading to the other coordinate in degrees (-180 to 180).
        """
        dx = other.x - self.x
        dy = other.y - self.y
        target_heading = np.degrees(np.arctan2(dy, dx))
        target_heading = 90 - target_heading  # Convert to geographic angle
        if target_heading < 0:
            target_heading += 360
        
        angle_diff = target_heading - current_heading
        if angle_diff > 180:
            angle_diff -= 360
        elif angle_diff < -180:
            angle_diff += 360
        
        return angle_diff

    def __str__(self) -> str:
        return "Coordinate(x={}, y={})".format(self.x, self.y)

    def __repr__(self) -> str:
        return self.__str__()

def cvt_gll_ddmm_2_dd(gll_data):
    """
    Convert GPS coordinates from DDMM.MMMM format to decimal degrees (DD.DDDDD).

    Parameters:
    - gll_data (list): GPS GLL data containing latitude and longitude in DDMM.MMMM format.

    Returns:
    - tuple: (latitude in decimal degrees, longitude in decimal degrees)
    """
    ilat = gll_data[0]
    ilon = gll_data[2]
    olat = float(int(ilat / 100))
    olon = float(int(ilon / 100))
    olat_mm = (ilat % 100) / 60
    olon_mm = (ilon % 100) / 60
    olat += olat_mm
    olon += olon_mm
    if gll_data[1] == 'S':
        olat = -olat
    if gll_data[3] == 'W':
        olon = -olon
    return olat, olon


def initialize_gps():
    """
    Initialize the GPS module.

    Returns:
    - gps (GpsIO): An instance of the GPS I/O class.
    """
    gps = gpddrv.GpsIO(1)
    gps.set_filter_speed("0.4")
    gps.get_filter_speed()
    gps.set_filter_speed("0")
    gps.get_filter_speed()
    return gps



def save_gps_data(lat_lon_list, filename='gps_data.kml'):
    """
    Save GPS data to a KML file.

    Parameters:
    - lat_lon_list (list): List of (latitude, longitude) tuples.
    - filename (str): Name of the KML file to save.
    """
    print("Saving GPS data to {}...".format(filename))
    kml = simplekml.Kml()
    for i, (lat, lon) in enumerate(lat_lon_list):
        kml.newpoint(name="GPS_{}".format(i), coords=[(lon, lat)])
    kml.save(filename)
    print("GPS data saved to {}".format(filename))

def signal_handler(sig, frame):
    """
    Handle Ctrl+C signal by saving GPS data and exiting.
    """
    print("\nCtrl+C pressed. Saving GPS data and exiting...")
    save_gps_data(lat_lon_list)
    sys.exit(0)

def read_gps_data(gps):
    """
    Read GPS data from the GPS module.

    Parameters:
    - gps (GpsIO): An instance of the GPS I/O class.

    Returns:
    - tuple: (latitude in decimal degrees, longitude in decimal degrees)
    """
    while True:
        rmc_ok, rmc_data = gps.read_rmc_non_blocking()
        if rmc_ok:
            lat_lon = cvt_gll_ddmm_2_dd(rmc_data)
            if lat_lon[0] is not None and lat_lon[1] is not None:
                return lat_lon
        time.sleep(0.01)


def convert_to_utm(lat, lon):
    """
    Convert latitude and longitude to UTM (x, y) coordinates.

    Parameters:
    - lat (float): Latitude in decimal degrees.
    - lon (float): Longitude in decimal degrees.

    Returns:
    - Coordinate: UTM coordinates as a Coordinate instance.
    """
    x, y = projDegree2Meter(lon, lat)
    return Coordinate(x, y)

def initialize_imu():
    """
    Initialize the IMU module.

    Returns:
    - imu (Imu9IO): An instance of the IMU I/O class.
    """
    imu = imudrv.Imu9IO()
    return imu

def read_imu_data(imu):
    """
    Read raw data from the IMU sensors.

    Parameters:
    - imu (Imu9IO): An instance of the IMU I/O class.

    Returns:
    - dict: Dictionary containing raw data from accelerometer, gyroscope, and magnetometer.
    """
    data = {
        'accelerometer': imu.read_accel_raw(),
        'gyroscope': imu.read_gyro_raw(),
        'magnetometer': imu.read_mag_raw()
    }
    return data

def apply_compass_calibration(mag_raw):
    """
    Apply calibration to raw magnetometer data.

    Parameters:
    - mag_raw (tuple): Raw magnetometer data (x, y, z).

    Returns:
    - numpy.ndarray: Calibrated magnetometer data [x_calib, y_calib, z_calib].
    """
    mag_raw_vector = np.array([[mag_raw[0]], [mag_raw[1]], [mag_raw[2]]])
    mag_calib = np.dot(A_inv, (mag_raw_vector + b))
    return mag_calib.flatten()  # Convert to 1D array

def compute_compass_heading(mag_calib):
    """
    Compute compass heading from calibrated magnetometer data.

    Parameters:
    - mag_calib (numpy.ndarray): Calibrated magnetometer data [x_calib, y_calib, z_calib].

    Returns:
    - float: Compass heading in degrees (0° to 360°).
    """
    x_calib, y_calib, _ = mag_calib
    heading_rad = np.arctan2(y_calib, x_calib)
    heading_deg = np.degrees(heading_rad)
    if heading_deg < 0:
        heading_deg += 360
    return heading_deg

def initialize_motors():
    """
    Initialize the motor control module.

    Returns:
    - ard (ArduinoIO): An instance of the Arduino I/O class for motor control.
    """
    ard = arddrv.ArduinoIO()
    return ard

def set_motor_speeds(ard, left_speed, right_speed):
    """
    Set the speeds of the left and right motors.

    Parameters:
    - ard (ArduinoIO): An instance of the Arduino I/O class.
    - left_speed (int): Speed for the left motor (-255 to 255).
    - right_speed (int): Speed for the right motor (-255 to 255).
    """
    ard.send_arduino_cmd_motor(left_speed, right_speed)

def stop_motors(ard):
    """
    Stop both motors.

    Parameters:
    - ard (ArduinoIO): An instance of the Arduino I/O class.
    """
    ard.send_arduino_cmd_motor(0, 0)

def log_to_gpx(lat_lon_list, filename='gps_data.gpx'):
    """
    Log GPS data to a GPX file for visualization.

    Parameters:
    - lat_lon_list (list): List of (latitude, longitude) tuples.
    - filename (str): Name of the GPX file to save.
    """
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)
    for lat, lon in lat_lon_list:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon))
    with open(filename, 'w') as f:
        f.write(gpx.to_xml())

def log_to_kml(lat_lon_list, filename='gps_data.kml'):
    """
    Log GPS data to a KML file for visualization.

    Parameters:
    - lat_lon_list (list): List of (latitude, longitude) tuples.
    - filename (str): Name of the KML file to save.
    """
    kml = simplekml.Kml()
    for i, (lat, lon) in enumerate(lat_lon_list):
        kml.newpoint(name="GPS_{}".format(i), coords=[(lon, lat)])
    kml.save(filename)

def navigation(gps, imu, ref_coord: Coordinate, lat_lon_list):
    global latest_nav_data

    """
    Perform navigation by reading GPS and IMU data, computing positions and headings.

    Parameters:
    - gps (GpsIO): An instance of the GPS I/O class.
    - imu (Imu9IO): An instance of the IMU I/O class.
    - ref_coord (Coordinate): The reference coordinate to navigate towards.
    - lat_lon_list (list): List to store latitude and longitude tuples.
    
    Returns:
    - current_coord (Coordinate): The current UTM coordinate.
    - compass_heading (float): The current compass heading in degrees.
    """
    # Read GPS data
    lat, lon = read_gps_data(gps)
    current_coord = convert_to_utm(lat, lon)
    distance = current_coord.distance_to(ref_coord)

    # Read IMU data
    imu_data = read_imu_data(imu)
    mag_raw = imu_data['magnetometer']

    # Apply calibration and compute compass heading
    mag_calib = apply_compass_calibration(mag_raw)
    compass_heading = compute_compass_heading(mag_calib)

    # Calculate angle to reference point
    angle_to_ref = current_coord.angle_to(ref_coord, compass_heading)

    latest_nav_data = {
        "timestamp": datetime.now().isoformat(),
        "position": {"lat": lat, "lon": lon},
        "distance_to_ref": float(distance),  # Ensure it's JSON serializable
        "angle_to_ref": float(angle_to_ref),
        "compass_heading": float(compass_heading)
    }

    # Print outputs
    print("Timestamp: {}".format(datetime.now()))
    print("Position: ({:.6f}, {:.6f})".format(lat, lon))
    print("Distance to Reference Point: {:.2f} meters".format(distance))
    print("Angle to Reference Point: {:.2f} degrees".format(angle_to_ref))
    print("Compass Heading: {:.2f} degrees".format(compass_heading))
    print(80 * "-")

    # Append GPS data to list
    lat_lon_list.append((lat, lon))

    return current_coord, compass_heading


def main_example():
    """
    Main function demonstrating the usage of the utility functions.
    """
    # Initialize modules
    gps = initialize_gps()
    imu = initialize_imu()
    ard = initialize_motors()

    # Lists to store GPS data
    global lat_lon_list
    lat_lon_list = []

    # Reference point (example coordinates)
    ref_lat = 48.199111
    ref_lon = -3.014930
    ref_coord = convert_to_utm(ref_lat, ref_lon)

    # Mission control
    waypoint_coords = []
    waypoint_coords_idx = 0
    
    ## Goal point (example coordinates)
    #goal: 48.19940238351465, -3.01552277111258
    goal_lat = 48.19940238351465
    goal_lon = -3.01552277111258
    goal_coord = convert_to_utm(goal_lat, goal_lon)
    waypoint_coords.append(goal_coord)
    
    ## Start point
    start_coord, _ = navigation(gps, imu, ref_coord, lat_lon_list)
    waypoint_coords.append(start_coord)
    
    waypoint_coord = waypoint_coords[waypoint_coords_idx]

    # Control constants
    rot_a = 0.1
    rot_b = 0
    acc_a = 2
    acc_b = 0
    acceptable_heading_err = 20 # acceptable heading err in degrees
    acceptable_distance_err = 5 # acceptable distance err in meters

    # Wait for the GPS to stabilize
    time.sleep(5)

    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    print("Starting navigation. Press Ctrl+C to stop and save GPS data.")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    print("Starting navigation. Press Ctrl+C to stop and save GPS data.")
    print("Access navigation data at http://localhost:8000/api/nav_data")


    try:
        while True:
            # Navigation
            current_coord, cur_heading = navigation(gps, imu, ref_coord, lat_lon_list)

            # Guidance
            distance_to_waypoint = current_coord.distance_to(waypoint_coord)
            heading_to_waypoint = current_coord.angle_to(waypoint_coord, cur_heading)
            print("Distance to goal: {:.2f} meters".format(distance_to_waypoint))
            print("Heading to goal: {:.2f} degrees".format(heading_to_waypoint))

            # Mission control
            if (distance_to_waypoint < acceptable_distance_err):
                print("Waypoint [{:.2f}, {:.2f}] reached".format(waypoint_coord.x, waypoint_coord.y))
                waypoint_coords_idx += 1
                if waypoint_coords_idx == len(waypoint_coords):
                    break
                stop_motors(ard)
                time.sleep(5)
                waypoint_coord = waypoint_coords[waypoint_coords_idx]

            # Control
            rot_speed = rot_a * np.fabs(heading_to_waypoint) + rot_b
            F_u = acc_a * distance_to_waypoint + acc_b

            print("DEBUG: rot_speed: {:.2f}", rot_speed)
            print("DEBUG: F_u: {:.2f}", F_u)
            
            # Actuator layer
            F_l = 0
            F_r = 0
            
            ## Turning
            if heading_to_waypoint > acceptable_heading_err:
                F_l = rot_speed
                print("DEBUG: Turning right")
            elif heading_to_waypoint < -acceptable_heading_err:
                F_r = rot_speed
                print("DEBUG: Turning left")

            ## Forward speed
            F_l += F_u / 2.0
            F_r += F_u / 2.0
            print("DEBUG: F_l: {:.2f}", F_l)
            print("DEBUG: F_r: {:.2f}", F_r)

            F_l = int(np.clip(F_l, 50.0, 255.0))
            F_r = int(np.clip(F_r, 50.0, 255.0))

            


            set_motor_speeds(ard, F_l, F_r)

            print(80*"=")
            time.sleep(1)

        print("All waypoints reached, mission done!")

    except KeyboardInterrupt:
        # This block will be executed if Ctrl+C is pressed
        print("\nCtrl+C pressed. Saving GPS data and exiting...")
    finally:
        # Save GPS data
        save_gps_data(lat_lon_list)
        stop_motors(ard)
        print("GPS data saved. Exiting program.")

if __name__ == '__main__':
    main_example()