default: lint format check test

# Install dependencies
install:
    uv sync

# Run linting checks
lint:
    uv run ruff check src

# Format code
format:
	uv run ruff check --select I --fix src
	uv run ruff format src

# Run ty type checker
ty:
    uv run ty check src

# Run type checking
check:
    just lint
    just ty
    just test

# Run tests
test:
    uv run pytest tests

# Remove build artifacts
clean:
    rm -rf dist


# Build the package and check that the .obo data file is included
build:
    uv build
    @echo "--- Wheel contents (*.obo files) ---"
    @python3 -c "import zipfile, glob; [print('\n'.join(f for f in zipfile.ZipFile(w).namelist() if f.endswith('.obo'))) for w in glob.glob('dist/*.whl')]"
