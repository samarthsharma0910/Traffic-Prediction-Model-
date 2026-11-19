"""
One-shot setup: create DB, seed zones across India, train the ML model.
Run once (and again whenever you want to retrain):  python setup.py
"""
from cities import build_zones
from database import init_database, load_zones, seed_locations
from ml_model import train


def main():
    print("[1/3] Initialising database...")
    init_database()
    print("[2/3] Seeding monitoring zones across India...")
    n = seed_locations(build_zones())
    print(f"      {n} zones in Location table")
    print("[3/3] Training ML model (this takes a few minutes)...")
    train(load_zones())
    print("\nDone. Start the app with:  python app.py   ->  http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
