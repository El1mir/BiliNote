from pathlib import Path

p = Path(r"backend/app/routers/note.py")
s = p.read_text(encoding="utf-8")

def sub(old: str, new: str, label: str) -> None:
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    s = s.replace(old, new, 1)

sub(
    "    model_name: str\n    provider_id: str\n",
    "    model_name: Optional[str] = None\n    provider_id: Optional[str] = None\n",
    "VideoRequest model fields",
)
sub(
    "        stored[key] = getattr(value, \"value\", value)\n    return stored\n",
    "        stored[key] = getattr(value, \"value\", value)\n"
    "    stored.pop(\"model_name\", None)\n"
    "    stored.pop(\"provider_id\", None)\n"
    "    return stored\n",
    "strip legacy model fields from storage",
)
sub(
    "    if not model_name or not provider_id:\n"
    "        raise HTTPException(status_code=400, detail=\"请选择模型和提供者\")\n",
    "    try:\n"
    "        active_model = resolve_active_model()\n"
    "        model_name = active_model[\"model_name\"]\n"
    "        provider_id = active_model[\"provider_id\"]\n"
    "    except RuntimeError as exc:\n"
    "        raise HTTPException(status_code=400, detail=str(exc)) from exc\n",
    "resolve current model in run_note_task",
)
sub(
    "        \"model_name\": model_name,\n"
    "        \"provider_id\": provider_id,\n",
    "",
    "remove model ids from parked kwargs",
)
sub(
    "    model_name: str\n    provider_id: str\n",
    "    model_name: Optional[str] = None\n    provider_id: Optional[str] = None\n",
    "BatchGenerateRequest model fields",
)
sub(
    "        if not data.model_name or not data.provider_id:\n"
    "            return R.error(msg=\"请选择模型和提供者\", code=400)\n",
    "        resolve_active_model()\n",
    "remove batch model validation",
)
p.write_text(s, encoding="utf-8")
print("patched note.py")
