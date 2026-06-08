"""
main.py — Entry point para Railway.
Importa la app de api/main.py
"""
import sys
import os

# Asegura que el directorio raíz esté en el path
sys.path.insert(0, os.path.dirname(__file__))

from api.main import app  # noqa: F401 — Railway busca 'app' aquí
