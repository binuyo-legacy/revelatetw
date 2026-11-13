"""The service list: verses lined up before the service. Stored as JSON."""
import json
import os


class ServiceList:
    def __init__(self):
        self.items = []   # each: {"ref": "John 3:16", "translation": "KJV"}

    def add(self, ref, translation):
        item = {"ref": ref, "translation": translation}
        if item not in self.items:
            self.items.append(item)
            return True
        return False

    def remove(self, index):
        if 0 <= index < len(self.items):
            del self.items[index]

    def move(self, index, delta):
        """Move an item up (-1) or down (+1). Returns its new index."""
        j = index + delta
        if 0 <= index < len(self.items) and 0 <= j < len(self.items):
            self.items[index], self.items[j] = self.items[j], self.items[index]
            return j
        return index

    def clear(self):
        self.items = []

    def save(self, path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "items": self.items}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path):
        sl = cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for it in data.get("items", []):
                if isinstance(it, dict) and isinstance(it.get("ref"), str) and isinstance(it.get("translation"), str):
                    sl.items.append({"ref": it["ref"], "translation": it["translation"]})
        except (OSError, ValueError, AttributeError):
            pass
        return sl
