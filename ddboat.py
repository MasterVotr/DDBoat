# ddboat_utils.py

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

Author: Your Name
Date: October 2024
Contact: your.email@example.com
"""

import sys
import os
import time
import numpy as np
from pyproj import Proj
import gpxpy.gpx
import simplekml
from datetime import datetime

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
        return f"Coordinate(x={self.x}, y={self.y})"

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
    gps = gpddrv.GpsIO()
    gps.set_filter_speed("0")  # Allow GPS measures when stationary
    return gps

def read_gps_data(gps):
    """
    Read GPS data from the GPS module.

    Parameters:
    - gps (GpsIO): An instance of the GPS I/O class.

    Returns:
    - tuple: (latitude in decimal degrees, longitude in decimal degrees)
    """
    while True:
        gll_ok, gll_data = gps.read_gll_non_blocking()
        if gll_ok:
            lat, lon = cvt_gll_ddmm_2_dd(gll_data)
            return lat, lon
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
    A_inv = np.linalg.inv(A[0])  # A is a 3D array, so we need to use A[0]
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
    # Read GPS and compass data
    # Read GPS data
    gll_ok, gll_data = gps.read_gll_non_blocking()
    if gll_ok:
        ilat, ilon = gll_data[0], gll_data[2]
        lat = float(int(ilat/100)) + (ilat%100)/60
        lon = float(int(ilon/100)) + (ilon%100)/60
        if gll_data[3] == "W":
            lon = -lon
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

    # Reference point (example coordinates)
    ref_lat = 48.199111
    ref_lon = -3.014930
    ref_coord = convert_to_utm(ref_lat, ref_lon)

    # Goal point (example coordinates)
    goal_lat = ref_lat
    goal_lon = ref_lon
    goal_coord = convert_to_utm(goal_lat, goal_lon)

    # Lists to store GPS data
    lat_lon_list = []

    while True:
        # Navigation
        current_coord, cur_heading = navigation(gps, imu, ref_coord, lat_lon_list)

        # Guidance
        distance_to_goal = current_coord.distance_to(goal_coord)
        angle_to_goal = current_coord.angle_to(goal_coord, cur_heading)

        # Control
        # Add your control logic here
        print(f"Distance to goal: {distance_to_goal:.2f} meters")
        print(f"Angle to goal: {angle_to_goal:.2f} degrees")

        time.sleep(1)

    # Log GPS data
    # log_to_gpx(lat_lon_list)
    log_to_kml(lat_lon_list)

    # # Example motor control
    # set_motor_speeds(ard, 100, -100)  # Rotate in place
    # time.sleep(2)
    # stop_motors(ard)

if __name__ == '__main__':
    main_example()