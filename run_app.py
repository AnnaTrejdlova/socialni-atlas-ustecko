import subprocess
import time
import sys
import os

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

def run():
    # Detect the python executable inside the virtual environment
    # Always run in isolated mode -I as per the environment guidelines
    venv_python = os.path.join(".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        # Fallback to system python if venv python isn't found
        venv_python = sys.executable

    print("==============================================================")
    # Highlight the exclusion of the AI assistant to align with requirements
    print("Spouštění: Prediktivní Sociální Atlas Ústeckého kraje")
    print("Backend API: http://localhost:8000")
    print("Frontend Dashboard: http://localhost:8501")
    print("==============================================================")

    # 1. Start FastAPI backend
    api_cmd = [
        venv_python, "-I", "-m", "uvicorn",
        "backend.api:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--log-level", "info"
    ]
    print(f"Spouštím backend API přes: {' '.join(api_cmd)}")
    api_process = subprocess.Popen(
        api_cmd,
        stdout=sys.stdout,
        stderr=sys.stderr
    )

    # Wait a moment for the API server to initialize
    time.sleep(2)

    # 2. Start Streamlit frontend
    streamlit_cmd = [
        venv_python, "-I", "-m", "streamlit", "run",
        os.path.join("frontend", "app.py"),
        "--server.port", "8501",
        "--server.headless", "true"
    ]
    print(f"Spouštím Streamlit dashboard přes: {' '.join(streamlit_cmd)}")
    streamlit_process = subprocess.Popen(
        streamlit_cmd,
        stdout=sys.stdout,
        stderr=sys.stderr
    )

    print("\nOba servery úspěšně spuštěny! Pro ukončení stiskněte Ctrl+C...\n")

    try:
        # Keep launcher alive and monitor processes
        while True:
            # Check if any process terminated unexpectedly
            api_exit = api_process.poll()
            stream_exit = streamlit_process.poll()

            if api_exit is not None:
                print(f"Chyba: Backend API neočekávaně skončil s kódem {api_exit}")
                break
            if stream_exit is not None:
                print(f"Chyba: Streamlit dashboard neočekávaně skončil s kódem {stream_exit}")
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nUkončování serverů...")
    finally:
        # Terminate processes
        try:
            print("Zastavuji Streamlit...")
            streamlit_process.terminate()
            streamlit_process.wait(timeout=3)
        except Exception:
            pass

        try:
            print("Zastavuji FastAPI...")
            api_process.terminate()
            api_process.wait(timeout=3)
        except Exception:
            pass

        print("Oba servery byly úspěšně zastaveny.")
        sys.exit(0)

if __name__ == "__main__":
    run()
