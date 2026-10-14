"""A minimal MCP client: what an agent does with `fobis mcp`, one request per line on the server's stdin.

python3 tools/mcp_client.py list                   the tools, read-only ones marked
python3 tools/mcp_client.py call TOOL '{"k": "v"}'   call one tool, print its text result
"""

import json
import subprocess
import sys

server = subprocess.Popen(["fobis", "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def request(ident, method, params=None):
    message = {"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}}
    server.stdin.write(json.dumps(message) + "\n")
    server.stdin.flush()
    return json.loads(server.stdout.readline())


hello = request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "demo"}})
server.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
if sys.argv[1] == "list":
    info = hello["result"]["serverInfo"]
    print(f"{info['name']}: protocol {hello['result']['protocolVersion']}")
    for tool in request(2, "tools/list")["result"]["tools"]:
        mark = "read-only" if tool["annotations"].get("readOnlyHint") else "writes"
        print(f"  {tool['name']:<20} {mark:<10} {tool['title']}")
else:
    reply = request(2, "tools/call", {"name": sys.argv[2], "arguments": json.loads(sys.argv[3])})["result"]
    print("error" if reply.get("isError") else "result", "of", sys.argv[2])
    print(reply["content"][0]["text"])
server.stdin.close()
server.wait()
