import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from switch_refresh_config_import_tool.app import main


if __name__ == "__main__":
    main()
