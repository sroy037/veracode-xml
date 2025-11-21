from pydantic import BaseModel

class QueryRequest(BaseModel):
    query: str

class CommandResponse(BaseModel):
    command: list[str]
    output: dict
    stderr: str
    exit_code: int