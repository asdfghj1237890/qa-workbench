"""Contract: rag_evalkit.serialization.read_json rejects nonfinite JSON constants."""

from rag_evalkit.contracts import ContractError
from rag_evalkit.serialization import read_json


def read_constant(directory, constant):
    path = directory / "report.json"
    path.write_text('{"value": ' + constant + ', "text": "繁體中文"}', encoding="utf-8")
    try:
        return read_json(path)
    except ContractError as error:
        return {"error_type": type(error).__name__, "message": str(error)}
