"""Roda todos os testes automáticos do Azus.

    python3 -B testes/rodar_tudo.py

Os testes usam só dados sintéticos e bancos SQLite temporários (fora do repositório).
"""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.chdir(AQUI)
r = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(AQUI, pattern="test_*.py"))
sys.exit(0 if r.wasSuccessful() else 1)
