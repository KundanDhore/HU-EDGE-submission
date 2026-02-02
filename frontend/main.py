"""
Frontend application runner.
Run with: streamlit run app.py
"""
import subprocess
import sys


def main():
    """Run the Streamlit frontend application"""
    try:
        subprocess.run(["streamlit", "run", "app.py"], check=True)
    except KeyboardInterrupt:
        print("\nApplication stopped.")
    except FileNotFoundError:
        print("Error: Streamlit not found. Please install dependencies:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Error running application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
