import os
import json

DEFAULT_CONFIG = {
    "api_key": "",
    "model_name": "gemini-1.5-flash",
    "k_gram": 5,
    "window_size": 4,
    "similarity_threshold": 0.70,
    "complexity_threshold": 5,
    "baseline_dir": ".aegis_baselines"
}

CONFIG_FILE = "aegis.json"

def load_config():
    """Loads configuration from the local aegis.json or returns defaults."""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            print(f"Warning: Failed to parse {CONFIG_FILE}: {e}. Using defaults.")
    
    # Try fetching API key from environment if not present in config
    if not config.get("api_key"):
        config["api_key"] = os.environ.get("GEMINI_API_KEY", "")
        
    return config

def save_config(config):
    """Saves the configuration dictionary to aegis.json."""
    try:
        # Don't save environment variables if they are empty
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error: Failed to write {CONFIG_FILE}: {e}")
        return False
