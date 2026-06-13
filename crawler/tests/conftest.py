import sys
from pathlib import Path

# crawler/ 를 import 경로에 올려 'from sources import ...' 및 'import crawler' 가능하게
CRAWLER_DIR = Path(__file__).resolve().parents[1]
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))
