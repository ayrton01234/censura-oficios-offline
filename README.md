# Censura Automatica de Oficios (Offline)

Aplicacao desktop offline em Python, Tkinter e PyMuPDF para ler oficios em PDF, identificar itens nas secoes de solicitacoes e gerar PDFs individuais por solicitante aplicando tarja preta nos demais itens.

## Como executar

pip install pymupdf pyinstaller
python sistema_censura_offline.py

## Como gerar o .exe

python -m PyInstaller --onefile --windowed --name "CensuraOficios" sistema_censura_offline.py
