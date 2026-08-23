from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from mcpgateway.utils.token_scoping import validate_server_access

app = FastAPI()

class RPCRequest(BaseModel):
    method: str
    params: dict

@app.post('/rpc')
async def handle_rpc(request: Request, rpc_request: RPCRequest):
    server_id = rpc_request.params.get('server_id')
    if server_id:
        token, payload = request.state._jwt_verified_payload
        token_scopes = payload.get('scopes', {})
        if not validate_server_access(token_scopes, server_id):
            return HTTPException(status_code=403, detail={'code': -32600, 'message': 'Forbidden'})
    # Handle the RPC request as usual
    pass