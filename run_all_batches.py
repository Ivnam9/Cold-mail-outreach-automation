from pathlib import Path
import subprocess
import sys

batches = sorted(Path("data").glob("batch_real_*.csv"))

for batch in batches:
    subprocess.run(
        [sys.executable, "src/send/send_batch.py", "--batch", str(batch)],
        check=True,
    )
