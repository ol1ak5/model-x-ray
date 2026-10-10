import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.base import BaseStore
from langgraph.store.sqlite import SqliteStore

from model_x_ray.spreadsheet.engine import Workbook
from model_x_ray.state import Finding, ModelMap, Override


def sqlite_checkpointer(path: str) -> SqliteSaver:
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def sqlite_store(path: str) -> SqliteStore:
    store = SqliteStore(sqlite3.connect(path, check_same_thread=False, isolation_level=None))
    store.setup()
    return store


class ModelMemory:
    def __init__(self, store: BaseStore) -> None:
        self._store = store

    @staticmethod
    def _namespace(kind: str, spreadsheet_id: str) -> tuple[str, str]:
        return (kind, spreadsheet_id.replace(".", "_"))

    def model_map(self, spreadsheet_id: str, revision: str) -> ModelMap | None:
        item = self._store.get(self._namespace("models", spreadsheet_id), revision)
        return item.value if item else None

    def save_model_map(self, spreadsheet_id: str, revision: str, model_map: ModelMap) -> None:
        self._store.put(self._namespace("models", spreadsheet_id), revision, dict(model_map))

    def overrides(self, spreadsheet_id: str, book: Workbook) -> list[Override]:
        stored = [item.value for item in self._store.search(self._namespace("overrides", spreadsheet_id), limit=1000)]
        return [o for o in stored if str(book.raw(o["cell"])) == o["content"]]

    def add_override(self, spreadsheet_id: str, override: Override) -> None:
        self._store.put(self._namespace("overrides", spreadsheet_id), override["cell"], dict(override))

    def findings(self, spreadsheet_id: str) -> list[Finding]:
        return [item.value for item in self._store.search(self._namespace("findings", spreadsheet_id), limit=1000)]

    def add_finding(self, spreadsheet_id: str, finding: Finding) -> None:
        self._store.put(self._namespace("findings", spreadsheet_id), finding["cell"], dict(finding))
