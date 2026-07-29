"""
this file contains the YAML parser for parsing and loading the YAML configuration for corpus
"""

import yaml 
from pathlib import Path
from typing import Union

# current_working_directory = Path.cwd().absolute()

def load_config(path: Path):
    config_file_path = Path(str(path))
    if not config_file_path.exists():
        raise FileNotFoundError("cannot find config.yaml file")

    with config_file_path.open("r", encoding="utf-8") as file:
        file_content = yaml.safe_load(file)

        if file_content is None:
            raise ValueError("config.yaml file is empty")

    return file_content

if __name__ == "__main__":
    config = load_config(Path("config.yaml"))
    print(config)