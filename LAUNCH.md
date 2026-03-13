# Launch TruthLens

The app can't bind to a port from inside Cursor's environment. Run it **in your Mac's Terminal**:

## Option 1: Double-click (if you use Terminal)

1. Open **Terminal** (Applications → Utilities → Terminal).
2. Run:
   ```bash
   /Users/jayson/Downloads/TruthLense/run_truthlens.sh
   ```
   Or drag `run_truthlens.sh` into the Terminal window and press Enter.

## Option 2: Manual commands

1. Open **Terminal**.
2. Run:
   ```bash
   cd /Users/jayson/Downloads/TruthLense
   python3 truthlens_api.py
   ```

## Then open in your browser

- **http://localhost:8080**

Leave the Terminal window open while you use the dashboard. Press `Ctrl+C` in Terminal to stop the server.
