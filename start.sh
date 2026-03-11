#!/usr/bin/env bash

echo "DUCKHUNT - [CLI]"

check_venv () {
    if [ -d ".venv" ]; then
        run_app
        return
    fi

    echo "Criando ambiente virtual..."
    python3 -m venv .venv

    if [ $? -ne 0 ]; then
        echo "Erro ao criar ambiente virtual."
        read -p "Pressione ENTER para sair..."
        exit 1
    fi

    install_dependencies
}

install_dependencies () {
    echo "Verificando dependencias..."
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
}

run_app () {
    .venv/bin/python app.py
    read -p "Pressione ENTER para sair..."
}

check_venv