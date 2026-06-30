"""
api/index.py — entry point para Vercel serverless Python.
Encapsula a aplicação FastAPI com Mangum (ASGI → Lambda handler).
"""
import os
import sys

# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mangum import Mangum
from main import app  # noqa: E402

handler = Mangum(app, lifespan="auto")
