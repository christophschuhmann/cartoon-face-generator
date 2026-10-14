"""CLI compatibility entry point."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from cartoon_face.cli import main
if __name__=="__main__":
    sys.argv.insert(1,"preprocess")
    main()
