
import os
import sys
import time
import traceback
import subprocess
from pathlib import Path

import win32service
import win32serviceutil
import win32event
import servicemanager


# ============================================================
# VIDATHA CONFIGURATION
# ============================================================

BACKEND_DIR = Path(r"F:\MeetNotes\MeetNotes\backend")

PYTHON_EXE = (
    BACKEND_DIR / ".venv311" / "Scripts" / "python.exe"
)

APP_FILE = BACKEND_DIR / "app.py"

LOG_DIR = BACKEND_DIR.parent / "logs"

SERVICE_LOG = LOG_DIR / "vidatha-service-manager.log"
APP_LOG = LOG_DIR / "vidatha-app.log"


# ============================================================
# WINDOWS SERVICE
# ============================================================

class VidathaService(win32serviceutil.ServiceFramework):

    _svc_name_ = "VidathaPythonService"

    _svc_display_name_ = "Vidatha AI Backend"

    _svc_description_ = (
        "Runs and monitors the Vidatha FastAPI backend."
    )

    def __init__(self, args):

        super().__init__(args)

        self.stop_event = win32event.CreateEvent(
            None, 0, 0, None
        )

        self.process = None

    # --------------------------------------------------------
    # LOGGING
    # --------------------------------------------------------

    def log(self, message):

        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            timestamp = time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            with open(
                SERVICE_LOG,
                "a",
                encoding="utf-8"
            ) as file:

                file.write(
                    f"{timestamp} - {message}\n"
                )

        except Exception:
            servicemanager.LogErrorMsg(
                "Vidatha service logging failed: "
                + traceback.format_exc()
            )

    # --------------------------------------------------------
    # STOP SERVICE
    # --------------------------------------------------------

    def SvcStop(self):

        self.ReportServiceStatus(
            win32service.SERVICE_STOP_PENDING
        )

        self.log("Windows requested service shutdown.")

        win32event.SetEvent(self.stop_event)

        if (
            self.process is not None
            and self.process.poll() is None
        ):

            self.log(
                f"Stopping backend PID: {self.process.pid}"
            )

            self.process.terminate()

    # --------------------------------------------------------
    # SERVICE ENTRY POINT
    # --------------------------------------------------------

    def SvcDoRun(self):

        try:

            # Inform Windows immediately that the service
            # has entered the running state.
            self.ReportServiceStatus(
                win32service.SERVICE_RUNNING
            )

            self.log("----------------------------------------")
            self.log("VIDATHA WINDOWS SERVICE STARTED")
            self.log(f"Python: {PYTHON_EXE}")
            self.log(f"Backend: {APP_FILE}")
            self.log(f"Working directory: {BACKEND_DIR}")
            self.log(f"Service account: {os.environ.get('USERNAME')}")
            self.log("----------------------------------------")

            servicemanager.LogInfoMsg(
                "Vidatha AI Backend service started."
            )

            self.run_backend()

        except Exception:

            error_details = traceback.format_exc()

            self.log(
                "FATAL SERVICE ERROR:\n" + error_details
            )

            servicemanager.LogErrorMsg(
                "Vidatha service failed:\n" + error_details
            )

        finally:

            self.log("VIDATHA WINDOWS SERVICE EXITED.")

    # --------------------------------------------------------
    # BACKEND PROCESS MONITOR
    # --------------------------------------------------------

    def run_backend(self):

        LOG_DIR.mkdir(parents=True, exist_ok=True)

        if not PYTHON_EXE.is_file():

            raise FileNotFoundError(
                f"Python executable not found: {PYTHON_EXE}"
            )

        if not APP_FILE.is_file():

            raise FileNotFoundError(
                f"FastAPI application not found: {APP_FILE}"
            )

        self.log("Python executable verified.")
        self.log("FastAPI application verified.")

        while True:

            # Check whether Windows requested shutdown.
            if win32event.WaitForSingleObject(
                self.stop_event, 0
            ) == win32event.WAIT_OBJECT_0:

                self.log("Shutdown requested before launch.")
                return

            self.log("Starting Vidatha app.py...")

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            with open(
                APP_LOG,
                "a",
                encoding="utf-8"
            ) as app_log:

                app_log.write(
                    "\n\n========== VIDATHA STARTING ==========\n"
                )
                app_log.flush()

                self.process = subprocess.Popen(

                    [
                        str(PYTHON_EXE),
                        str(APP_FILE)
                    ],

                    cwd=str(BACKEND_DIR),

                    env=env,

                    stdout=app_log,

                    stderr=subprocess.STDOUT,

                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                self.log(
                    f"Backend process launched. PID: "
                    f"{self.process.pid}"
                )

                # Monitor the backend until it exits or
                # Windows requests a service shutdown.
                while self.process.poll() is None:

                    result = win32event.WaitForSingleObject(
                        self.stop_event,
                        1000
                    )

                    if result == win32event.WAIT_OBJECT_0:

                        self.log(
                            "Shutdown requested. Terminating backend."
                        )

                        self.process.terminate()

                        try:

                            self.process.wait(timeout=30)

                        except subprocess.TimeoutExpired:

                            self.log(
                                "Backend did not stop in 30 seconds. "
                                "Forcing termination."
                            )

                            self.process.kill()
                            self.process.wait()

                        self.log("Backend stopped successfully.")

                        self.process = None

                        return

                exit_code = self.process.returncode

                self.log(
                    f"Backend exited. Exit code: {exit_code}"
                )

            self.process = None

            # Restart after unexpected backend termination.
            self.log(
                "Backend restart scheduled after 10 seconds."
            )

            result = win32event.WaitForSingleObject(
                self.stop_event,
                10000
            )

            if result == win32event.WAIT_OBJECT_0:

                self.log("Shutdown requested during restart delay.")
                return


# ============================================================
# SERVICE COMMAND HANDLER
# ============================================================

if __name__ == "__main__":

    win32serviceutil.HandleCommandLine(
        VidathaService
    )
