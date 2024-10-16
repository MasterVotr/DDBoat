# app.py

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import threading
import requests
import time
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Use threading mode
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

data_source_ip = '127.0.0.1'  # Default IP
data_url = f'http://{data_source_ip}:8000/api/nav_data'
polling_interval = 0.5  # Default polling interval in seconds

gps_data_history = []

# Set up logging
logging.basicConfig(level=logging.INFO)

def fetch_gps_data():
    global data_url, polling_interval
    while True:
        try:
            logging.info(f"Fetching data from {data_url}")
            response = requests.get(data_url, timeout=1)
            if response.status_code == 200:
                data = response.json()

                # Append to history
                gps_data_history.append(data)

                # Emit to clients
                socketio.emit('gps_data_update', data)
                logging.info(f"Emitted gps_data_update: {data}")
            else:
                logging.error('Failed to retrieve data from the source.')
                socketio.emit('error', {'message': 'Failed to retrieve data from the source.'})
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching data: {e}")
            socketio.emit('error', {'message': 'Unable to connect to the data source.'})
        time.sleep(polling_interval)

@socketio.on('connect')
def handle_connect():
    logging.info('Client connected')
    emit('history_data', gps_data_history)

@socketio.on('set_polling_interval')
def handle_set_polling_interval(data):
    global polling_interval
    interval = data.get('interval')
    if interval:
        try:
            polling_interval = max(0.1, float(interval))
            emit('polling_interval_updated', {'interval': polling_interval})
            logging.info(f"Polling interval set to {polling_interval} seconds")
        except ValueError:
            emit('error', {'message': 'Invalid polling interval'})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/set_data_source_ip', methods=['POST'])
def set_data_source_ip():
    global data_source_ip, data_url
    data = request.get_json()
    data_source_ip = data.get('ip_address', '127.0.0.1')
    data_url = f'http://{data_source_ip}:8000/api/nav_data'
    logging.info(f"Data source IP set to {data_source_ip}")
    # Clear existing data when IP is changed
    global gps_data_history
    gps_data_history = []
    return ('', 204)

@app.route('/clear_data', methods=['POST'])
def clear_data():
    global gps_data_history
    gps_data_history = []
    logging.info("GPS data history cleared")
    return ('', 204)

if __name__ == '__main__':
    # Start the background thread
    thread = threading.Thread(target=fetch_gps_data)
    thread.daemon = True
    thread.start()

    # Run the Flask development server
    socketio.run(app, host='0.0.0.0', port=5000)
