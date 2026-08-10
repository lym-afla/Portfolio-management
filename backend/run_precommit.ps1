# Activate virtual environment and run pre-commit
& ".\venv\Scripts\Activate.ps1"
python -m pip install pre-commit
pre-commit run --all-files
