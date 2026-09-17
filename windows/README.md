# Oceanova Crawler Topside Application

Desktop control and monitoring application for the Oceanova underwater crawler.

The application provides:

* DualSense controller input
* Crawler motor control
* Live crawler video
* Telemetry and system status
* Connection monitoring and automatic reconnection
* Snapshot capture
* Video recording
* Persistent user configuration
* A graphical settings interface

---

## Code Structure

The application is split into several components with a shared `State` object.

```text

src/
│
├── main.py                    # Qt + asyncio startup/shutdown
│
├── state.py                   # Shared runtime state
├── config.py                  # Defaults + persistent config
│
├── connection_manager.py      # WebSockets, video, recording
├── controller.py              # DualSense input
├── helpers.py                 # Pure utility functions
│
└── gui/
    │
    ├── __init__.py
    │
    ├── main_window.py         # Window + navigation + timers
    │
    ├── control_page.py        # Crawler control screen
    │
    ├── video_widget.py        # Live video + recording controls
    │
    ├── settings_dialog.py     # IP + recording directory
    │
    ├── planning_page.py       # Planning controls
    │
    └── planning_view.py       # Grid + polygon renderer

```

---

## Communication Between Components

The application uses a shared `State` object.

A typical startup sequence is:

```text
main.py
   │
   ├── load_user_config()
   │
   ├── create State
   │
   ├── create ConnectionManager(state)
   │
   ├── create DualSense(state, connection)
   │
   └── start GUI
```

During normal operation:

```text
              State / UserConfig
                      ▲
                      │
       ┌──────────────┼──────────────┐
       │              │              │
       │              │              │
      GUI       ConnectionManager  Controller
       │              │              │
       │              │              │
       ▼              ▼              ▼
     User          Raspberry Pi   DualSense
    input          WebSockets      input
```

The `State` object provides a common view of the current application state.

---

# User Configuration

User configuration is stored outside the executable so that it can be changed without rebuilding the application.

The default location is:

```text
Linux:
~/OceanovaCrawler/user_configuration.json

Windows:
C:\Users\<username>\OceanovaCrawler\user_configuration.json
```

The recording directory is also user-configurable.

For example:

```json
{
    "pi_ip": "192.168.88.20",
    "record_dir": "D:\\CrawlerData\\recordings"
}
```

If the configuration file does not exist, the application falls back to the defaults defined in `config.py`.

The configuration is updated when the user presses `ENTER = Apply` in the settings window.

---

# Requirements

`requirements.txt` contains third-party Python packages required by the application.

PyInstaller automatically packages the imported Python dependencies from the active Python environment.

---

# Creating Windows Executable

*Note: PyInstaller does not support cross-platform installation so to create the Windows executable, run PyInstaller on a Windows machine.*

PyInstaller should be run from the `crawler-/windows` directory.

For example:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install pyinstaller

pyinstaller `
    --onefile `
    --windowed `
    --name OceanovaCrawler `
    --paths src `
    --add-data "icons;icons" `
    src/main.py
```

This creates

```text
dist/
└── OceanovaCrawler.exe
```

The resulting executable can be distributed to other compatible Windows machines without requiring Python or the Python dependencies to be installed.

The target machines still need to satisfy any requirements imposed by hardware drivers, such as the DualSense/controller support.

---

# Rebuilding After Code Changes

Whenever Python code or resources are changed, rebuild the executable.

For a simple rebuild:

```bash
pyinstaller `
    --onefile `
    --windowed `
    --name OceanovaCrawler `
    --paths src `
    --add-data "icons;icons" `
    src/main.py
```

If you encounter stale build files or unexpected packaging behaviour, perform a clean build:

```bash
pyinstaller \
    --clean \
    --noconfirm \
    --onefile \
    --windowed \
    --name OceanovaCrawler \
    --paths src \
    --add-data "icons;icons" \
    src/main.py
```

For a more complete clean rebuild, the generated directories can also be removed first:

```powershell
Remove-Item -Recurse -Force build, dist
Remove-Item -Force OceanovaCrawler.spec
```

---

# Summary

The main responsibilities of each module are:

| File                    | Responsibility                                           |
| ----------------------- | -------------------------------------------------------- |
| `main.py`               | Application startup, shutdown and orchestration          |
| `state.py`              | Shared runtime application state                         |
| `config.py`             | Defaults, constants and persistent user configuration    |
| `connection_manager.py` | Raspberry Pi communication, video, recording and control |
| `controller.py`         | DualSense input and motor command calculation            |
| `gui/`                  | Pyside6 interface and user interaction                   |
| `requirements.txt`      | Python package dependencies                              |

