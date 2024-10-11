from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import requests
import time
import threading

app = Flask(__name__)
socketio = SocketIO(app)

# Function to fetch data from the API
def get_nav_data():
    url = "http://172.20.25.205:8000/api/nav_data"
    try:
        # response = requests.get(url)
        # response.raise_for_status()  # Check if the request was successful
        sample_data = {"position":{"lat":48.199245,"lon":-3.01448666666667},"angle_to_ref":-148.722521384542,"distance_to_ref":36.1536436868404,"timestamp":"2024-10-11T13:03:26.220674","compass_heading":34.4051067235188}
        # data = response.json()  # Parse the JSON response
        return sample_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from the server: {e}")
        return None

# Background task to continuously fetch and emit nav data
def background_data_fetcher():
    while True:
        data = get_nav_data()
        if data:
            # Emit the data to all connected clients
            socketio.emit('nav_data', data)
        time.sleep(0.5)  # Fetch data every 0.5 seconds

@app.route('/')
def index():
    return render_template('index.html')

# Start the background thread when the server starts
@socketio.on('connect')
def start_background_task():
    print("Client connected")
    threading.Thread(target=background_data_fetcher, daemon=True).start()

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5001)
