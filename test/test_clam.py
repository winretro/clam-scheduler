import clamd

# Connect to the Docker container mapped to your local Windows network
cd = clamd.ClamdNetworkSocket(host='127.0.0.1', port=3310)

try:
    print("ClamAV Version:", cd.version())
    print("Ping Response:", cd.ping())
except Exception as e:
    print("Connection failed:", e)