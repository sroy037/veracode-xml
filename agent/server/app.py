from fastapi import FastAPI
from models import QueryRequest, CommandResponse
from llm_router import route_query_to_command
from command_executor import run_veracli
from parser import parse_output

app = FastAPI(title="Veracli Agent API")

@app.post("/query", response_model=CommandResponse)
def process_query(payload: QueryRequest):
    # 1. convert NL → CLI
    cmd = route_query_to_command(payload.query)

    # 2. run
    stdout, stderr, code = run_veracli(cmd)

    # 3. parse output
    parsed = parse_output(cmd[0], stdout)

    return CommandResponse(
        command=cmd,
        output=parsed,
        stderr=stderr,
        exit_code=code
    )