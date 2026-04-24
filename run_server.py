import uvicorn
import sys
from pathlib import Path

# Add the 'backend' directory to the Python path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

# Now that the path is set, we can import the app
from main import app

if __name__ == "__main__":
    print(f"Attempting to run server from: {backend_dir}")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        app_dir=str(backend_dir)
    )
