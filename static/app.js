// static/app.js

console.log('app.js is running');

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM fully loaded and parsed');

    // Establish a connection with the backend server via Socket.IO
    const socket = io();

    // Initialize variables
    let mapInitialized = false;
    let map;
    let currentMarker = null;
    let pathLine = null;
    let goalArrow = null;
    let headingArrow = null;
    // Removed arrowhead variables
    // let goalArrowHead = null;
    // let headingArrowHead = null;

    let gpsDataHistory = [];

    // Map control variables
    let userInteracted = false;
    let isLiveMode = true; // true for live mode, false for historic mode

    // UI Elements
    const latitudeEl = document.getElementById('latitude');
    const longitudeEl = document.getElementById('longitude');
    const compassHeadingEl = document.getElementById('compass_heading');
    const angleToRefEl = document.getElementById('angle_to_ref');
    const distanceToGoalEl = document.getElementById('distance_to_goal');
    const clearDataButton = document.getElementById('clear_data_button');
    const ipAddressInput = document.getElementById('ip_address');
    const setIpButton = document.getElementById('set_ip_button');
    const pollingRateInput = document.getElementById('polling_rate');
    const setPollingRateButton = document.getElementById('set_polling_rate_button');
    const modeIndicator = document.getElementById('mode_indicator');
    const modeSwitch = document.getElementById('mode_switch');

    // Timeline Slider
    const slider = document.getElementById('timeline_slider');
    noUiSlider.create(slider, {
        start: [0],
        range: {
            'min': 0,
            'max': 1
        },
        step: 1,
        tooltips: true,
        format: {
            to: function (value) {
                return Math.floor(value);
            },
            from: function (value) {
                return Number(value);
            }
        }
    });

    slider.setAttribute('disabled', true);
    slider.style.display = 'none'; // Hide slider initially

    // Function to update mode indicator
    function updateModeIndicator() {
        modeIndicator.textContent = isLiveMode ? 'Live' : 'Historic';

        if (isLiveMode) {
            // Update to latest data
            if (gpsDataHistory.length > 0) {
                const lastData = gpsDataHistory[gpsDataHistory.length - 1];
                updateMap(lastData);
                updateUI(lastData);
            }
        }
    }

    // Mode switch event listener
    modeSwitch.addEventListener('change', () => {
        isLiveMode = !modeSwitch.checked; // Assume checked is Historic mode
        updateModeIndicator();

        if (isLiveMode) {
            // Live mode
            slider.setAttribute('disabled', true);
            slider.style.display = 'none';
        } else {
            // Historic mode
            slider.removeAttribute('disabled');
            slider.style.display = 'block';
            updateSlider(); // Ensure slider is updated when switching to historic mode
        }
    });

    // Slider event listeners
    slider.noUiSlider.on('update', function (values, handle) {
        if (gpsDataHistory.length > 0 && !isLiveMode) {
            const index = parseInt(values[handle]);
            const data = gpsDataHistory[index];
            updateMap(data, true, index);
            updateUI(data);
        }
    });

    // Socket.IO event handlers
    socket.on('connect', () => {
        console.log('Socket.IO client connected');
    });

    socket.on('disconnect', () => {
        console.log('Socket.IO client disconnected');
    });

    socket.on('connect_error', (error) => {
        console.error('Socket.IO connection error:', error);
    });

    socket.on('gps_data_update', (data) => {
        console.log('Received gps_data_update:', data);
        gpsDataHistory.push(data);

        if (isLiveMode) {
            updateSlider(); // Update the slider with new data
            updateMap(data);
            updateUI(data);
        }
        // Do not update the slider in historic mode to prevent it from expanding
    });

    socket.on('history_data', (data) => {
        console.log('Received history_data:', data);
        gpsDataHistory = data;
        if (data.length > 0) {
            const lastData = data[data.length - 1];
            initializeMap(lastData.position.lat, lastData.position.lon);
            updateMap(lastData);
            updateUI(lastData);
            updateSlider();
        }
    });

    socket.on('polling_interval_updated', (data) => {
        alert(`Polling interval set to ${data.interval} seconds`);
    });

    socket.on('error', (message) => {
        console.error('Error message received:', message);
        alert(message.message);
    });

    // Initialize the map
    function initializeMap(lat, lon) {
        if (!mapInitialized) {
            map = L.map('map').setView([lat, lon], 13);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);

            // Map interaction events
            map.on('movestart', () => {
                userInteracted = true;
            });

            mapInitialized = true;
        }
    }

    // Function to normalize angles between 0 and 360 degrees
    function normalizeAngle(angle) {
        return (angle % 360 + 360) % 360;
    }

    // Function to calculate destination point given distance and bearing
    function calculateDestinationPoint(lat, lon, bearing, distance) {
        const R = 6371e3; // Earth's radius in meters
        const φ1 = lat * Math.PI / 180;
        const λ1 = lon * Math.PI / 180;
        const θ = bearing * Math.PI / 180;
        const δ = distance / R;

        const sinφ2 = Math.sin(φ1) * Math.cos(δ) + Math.cos(φ1) * Math.sin(δ) * Math.cos(θ);
        const φ2 = Math.asin(sinφ2);

        const y = Math.sin(θ) * Math.sin(δ) * Math.cos(φ1);
        const x = Math.cos(δ) - Math.sin(φ1) * sinφ2;
        const λ2 = λ1 + Math.atan2(y, x);

        return {
            lat: φ2 * 180 / Math.PI,
            lon: λ2 * 180 / Math.PI
        };
    }

    // Removed createArrowhead function since we no longer use arrowheads

    // Update the map with new data
    function updateMap(data, isReplay = false, replayIndex = null) {
        const latlng = [data.position.lat, data.position.lon];

        // Initialize map if not already initialized
        if (!mapInitialized) {
            initializeMap(latlng[0], latlng[1]);
        }

        // Update current position marker
        if (currentMarker) {
            currentMarker.setLatLng(latlng);
        } else {
            currentMarker = L.marker(latlng).addTo(map);
        }

        // Calculate endpoint for heading line
        const headingLength = 100; // Line length in meters
        const headingBearing = normalizeAngle(data.compass_heading);
        const headingPosition = calculateDestinationPoint(
            data.position.lat,
            data.position.lon,
            headingBearing,
            headingLength
        );

        // Remove existing heading line if it exists
        if (headingArrow) {
            map.removeLayer(headingArrow);
            headingArrow = null;
        }

        // Draw line for current heading
        headingArrow = L.polyline([latlng, [headingPosition.lat, headingPosition.lon]], {
            color: 'blue',
            weight: 2,
            opacity: 0.8,
        }).addTo(map);

        // Calculate the bearing towards the goal
        let bearingToGoal = normalizeAngle(data.compass_heading + data.angle_to_ref);

        // Calculate the goal position
        const goalPosition = calculateDestinationPoint(
            data.position.lat,
            data.position.lon,
            bearingToGoal,
            data.distance_to_ref
        );

        // Remove existing goal line if it exists
        if (goalArrow) {
            map.removeLayer(goalArrow);
            goalArrow = null;
        }

        // Draw line to goal
        goalArrow = L.polyline([latlng, [goalPosition.lat, goalPosition.lon]], {
            color: 'green',
            weight: 2,
            opacity: 0.8,
        }).addTo(map);

        // Update path line
        if (isReplay && replayIndex !== null) {
            const replayData = gpsDataHistory.slice(0, replayIndex + 1);
            updatePathLine(replayData);
        } else {
            updatePathLine(gpsDataHistory);
        }

        // Auto zoom and center to include all points if the user hasn't interacted
        if (!userInteracted) {
            const bounds = L.latLngBounds(gpsDataHistory.map(d => [d.position.lat, d.position.lon]));
            map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    // Update the path line
    function updatePathLine(data) {
        if (pathLine) {
            map.removeLayer(pathLine);
        }
        const latlngs = data.map(d => [d.position.lat, d.position.lon]);

        // Draw the path line without gradient
        pathLine = new L.Polyline(latlngs, {
            color: 'red',
            weight: 5,
            opacity: 1,
            dashArray: '10, 10' // Makes the line dashed
        }).addTo(map);
    }

    // Update the UI elements with new data
    function updateUI(data) {
        latitudeEl.textContent = data.position.lat.toFixed(6);
        longitudeEl.textContent = data.position.lon.toFixed(6);
        compassHeadingEl.textContent = data.compass_heading.toFixed(2);
        angleToRefEl.textContent = data.angle_to_ref.toFixed(2);
        distanceToGoalEl.textContent = data.distance_to_ref.toFixed(2);
    }

    // Update the timeline slider
    function updateSlider() {
        if (gpsDataHistory.length > 0 && isLiveMode) {
            slider.noUiSlider.updateOptions({
                range: {
                    'min': 0,
                    'max': gpsDataHistory.length - 1
                }
            });
            slider.noUiSlider.set(gpsDataHistory.length - 1);
        }

        if (isLiveMode) {
            slider.setAttribute('disabled', true);
            slider.style.display = 'none';
        } else {
            slider.removeAttribute('disabled');
            slider.style.display = 'block';
        }
    }

    // Clear data functionality
    clearDataButton.addEventListener('click', () => {
        fetch('/clear_data', { method: 'POST' })
            .then(response => {
                if (response.ok) {
                    gpsDataHistory = [];
                    if (pathLine) {
                        map.removeLayer(pathLine);
                        pathLine = null;
                    }
                    if (currentMarker) {
                        map.removeLayer(currentMarker);
                        currentMarker = null;
                    }
                    if (goalArrow) {
                        map.removeLayer(goalArrow);
                        goalArrow = null;
                    }
                    if (headingArrow) {
                        map.removeLayer(headingArrow);
                        headingArrow = null;
                    }
                    slider.noUiSlider.updateOptions({
                        range: {
                            'min': 0,
                            'max': 1
                        }
                    });
                    slider.noUiSlider.set(0);
                    slider.setAttribute('disabled', true);
                    slider.style.display = 'none';
                    alert('GPS data history cleared.');
                } else {
                    alert('Failed to clear GPS data.');
                }
            })
            .catch(error => {
                console.error('Error clearing data:', error);
                alert('An error occurred while clearing GPS data.');
            });
    });

    // Set IP Address functionality
    setIpButton.addEventListener('click', () => {
        const ipAddress = ipAddressInput.value.trim() || '127.0.0.1';
        fetch('/set_data_source_ip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip_address: ipAddress })
        }).then(response => {
            if (response.ok) {
                alert(`Data source IP set to ${ipAddress}`);
                // Clear existing data since data source has changed
                gpsDataHistory = [];
                if (pathLine) {
                    map.removeLayer(pathLine);
                    pathLine = null;
                }
                if (currentMarker) {
                    map.removeLayer(currentMarker);
                    currentMarker = null;
                }
                if (goalArrow) {
                    map.removeLayer(goalArrow);
                    goalArrow = null;
                }
                if (headingArrow) {
                    map.removeLayer(headingArrow);
                    headingArrow = null;
                }
                slider.noUiSlider.updateOptions({
                    range: {
                        'min': 0,
                        'max': 1
                    }
                });
                slider.noUiSlider.set(0);
                slider.setAttribute('disabled', true);
                slider.style.display = 'none';
            } else {
                alert('Failed to set data source IP.');
            }
        }).catch(error => {
            console.error('Error setting data source IP:', error);
            alert('An error occurred while setting the data source IP.');
        });
    });

    // Set Polling Rate functionality
    setPollingRateButton.addEventListener('click', () => {
        const pollingRate = parseFloat(pollingRateInput.value);
        if (isNaN(pollingRate) || pollingRate < 0.1) {
            alert('Please enter a valid polling interval (minimum 0.1 seconds).');
            return;
        }
        socket.emit('set_polling_interval', { interval: pollingRate });
    });
});
