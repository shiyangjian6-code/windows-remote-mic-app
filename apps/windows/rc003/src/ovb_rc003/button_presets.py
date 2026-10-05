"""Three ordinary-button snapshots over the existing flat runtime view.

The mic, physical key identity, retired combination data and all voice settings
remain shared. Switching publishes a single key_bindings.json atomic replace;
the existing bridge reload owns the safe boundary for in-flight input.
"""
from copy import deepcopy

STORE = "button_presets"
FIELDS = ("bindings", "secondary_bindings", "display_notes")
COUNT = 3
MAX_NAME_LENGTH = 24


def _index(value):
    if type(value) is not int or not 0 <= value < COUNT:
        raise ValueError("预设编号无效。")
    return value


def _name(value):
    if (not isinstance(value, str) or not value.strip()
            or len(value.strip()) > MAX_NAME_LENGTH
            or any(ord(char) < 32 for char in value)):
        raise ValueError("预设名称需为 1–24 个字符，不能包含换行。")
    return value.strip()


def _capture(document):
    return {field: {key: deepcopy(value) for key, value in document.get(field, {}).items()
                    if key != "mic"} for field in FIELDS}


def ensure(document):
    """Initialize legacy settings in memory only; never mutate caller data."""
    result = deepcopy(document)
    if STORE not in result:
        snapshot = _capture(result)
        result[STORE] = {"schema": 1, "active": 0, "slots": [
            {"name": f"预设 {index + 1}", **deepcopy(snapshot)} for index in range(COUNT)]}
    store = result[STORE]
    if (not isinstance(store, dict) or set(store) != {"schema", "active", "slots"}
            or type(store["schema"]) is not int or store["schema"] != 1
            or not isinstance(store["slots"], list) or len(store["slots"]) != COUNT):
        raise ValueError("按键预设数据无效，原配置未更改。")
    _index(store["active"])
    for slot in store["slots"]:
        if not isinstance(slot, dict) or set(slot) != {"name", *FIELDS}:
            raise ValueError("按键预设内容不完整。")
        _name(slot["name"])
        for field in FIELDS:
            if (not isinstance(slot[field], dict) or "mic" in slot[field]
                    or any(not isinstance(k, str) or not isinstance(v, dict)
                           for k, v in slot[field].items())):
                raise ValueError("按键预设内容无效。")
    return result


def sync(document):
    """Capture ordinary edits into the active slot before an existing save."""
    result = ensure(document)
    store = result[STORE]
    store["slots"][store["active"]].update(_capture(result))
    return result


def _apply(document, index):
    store = document[STORE]
    slot = store["slots"][index]
    for field in FIELDS:
        shared = {key: deepcopy(value) for key, value in document.get(field, {}).items()
                  if key == "mic"}
        document[field] = {**deepcopy(slot[field]), **shared}
    store["active"] = index
    return document


def switch(document, index):
    return _apply(sync(document), _index(index))


def rename(document, index, name):
    result = sync(document)
    result[STORE]["slots"][_index(index)]["name"] = _name(name)
    return result


def copy_slot(document, source, target):
    source, target = _index(source), _index(target)
    result = sync(document)
    store = result[STORE]
    original_name = store["slots"][target]["name"]
    store["slots"][target] = {**deepcopy(store["slots"][source]), "name": original_name}
    if target == store["active"]:
        _apply(result, target)
    return result
