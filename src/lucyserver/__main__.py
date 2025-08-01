from .server import app

import uvicorn
uvicorn.run("lucyserver.server:app", host="0.0.0.0",  port=8000, reload=True)