# Makefile for chat service

.PHONY: lint test coverage black isort pre-commit

lint:
	python -m pylint chat_service.py router.py

test:
	python -m pytest test_chat_events.py -v

coverage:
	python -m pytest --cov=chat_service.py --cov=router.py test_chat_events.py --cov-report=term-missing

black:
	python -m black chat_service.py router.py test_chat_events.py

isort:
	python -m isort chat_service.py router.py test_chat_events.py

pre-commit:
	make black isort lint

# Additional targets for the issue requirements
format: black isort

check:
	make lint test coverage
