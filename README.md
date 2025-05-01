# MCP Client Example 

This project demonstrates a simple client-server implementation using the Model Context Protocol (MCP), which is a standardized way to connect large language models with tools and data.

## Overview

This example shows how to:
- Create an MCP server with custom tools
- Connect to the server using an MCP client
- Call tools and get responses from the server


## Project Structure

```
.
├── pyproject.toml
├── README.md
├── src
│   ├── client
│   │   └── mcp_client.py      
│   └── server
│       └── example_server.py  
```

### Installation

python 3.12

```bash
# Install dependencies
pip install -e .
```

### Running the Example

1. Start the client (which will automatically start the server):

```bash
python3 src/client/mcp_client.py
```


## Test with MCP Inspector 

```
mcp dev src/server/example_server.py
```