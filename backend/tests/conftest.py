import os

# Hermetic suite: unit tests never touch a real iPhone.
os.environ.setdefault("FREETUNES_MOCK", "1")
