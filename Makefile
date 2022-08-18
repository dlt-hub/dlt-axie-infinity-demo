has-poetry:
	poetry --version

dev: has-poetry
	# will install itself as editable module with all the extras
	poetry install

lint:
	./check-package.sh
	poetry run mypy --config-file mypy.ini .
	poetry run flake8 --max-line-length=200 .
	# poetry run flake8 --max-line-length=200 tests

requirements:
	poetry export -f requirements.txt --output requirements.txt --without-hashes
