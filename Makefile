NAME   := scalevector/dlt-axie-infinity-demo
VERSION := 1.0.0
TAG    := $(shell git log -1 --pretty=%h)
IMG    := ${NAME}:${TAG}
LATEST := ${NAME}:latest

has-poetry:
	poetry --version

dev: has-poetry
	# will install itself as editable module with all the extras
	poetry install

lint:
	./check-package.sh
	poetry run mypy --config-file mypy.ini .
	poetry run flake8 --max-line-length=200 .

requirements:
	poetry export -f requirements.txt --output _gen_requirements.txt --without-hashes

build-image: requirements
	docker build -f deploy/Dockerfile --build-arg=COMMIT_SHA=${TAG} --build-arg=IMAGE_VERSION="${VERSION}" . -t ${IMG}
	docker tag ${IMG} ${NAME}:${VERSION}
	docker tag ${IMG} ${LATEST}

push-image:
	docker push ${IMG}
	docker push ${LATEST}
	docker push ${NAME}:${VERSION}

has-docker-pass:
ifeq ($(DOCKER_PASS),)
	$(error you must provide DOCKER_PASS environment variable or make [target] DOCKER_PASS=... parameter)
endif

docker-login: has-docker-pass
	docker login -u scalevector -p ${DOCKER_PASS}

helm:
	-rm -r deploy/helm-axies
	mkdir -p deploy/helm-axies
	cp deploy/docker-compose.yml deploy/helm-axies.yml
	cd deploy && kompose convert -f helm-axies.yml -c --with-kompose-annotation=true --controller deployment
	rm deploy/helm-axies.yml
	python3 deploy/extract_helm_values.py deploy/helm-axies
	# render templates to verify
	helm lint --strict deploy/helm-axies
	helm template deploy/helm-axies > /dev/null
