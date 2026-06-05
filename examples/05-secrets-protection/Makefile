VENV := .venv
PYTHON := $(VENV)/bin/python
PYBOX_ROOT := $(shell cd ../.. && pwd)

# Fake credential files — safe to create and delete
SSH_KEY    := $(HOME)/.ssh/id_rsa_fake
AWS_CREDS  := $(HOME)/.aws/credentials_fake
DOCKER_CFG := $(HOME)/.docker/config_fake.json
GCLOUD_CFG := $(HOME)/.config/gcloud/credentials_fake.json

.PHONY: setup attack clean

setup:
	uv venv $(VENV)
	uv pip install --quiet --python $(PYTHON) $(PYBOX_ROOT)
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo "Setup complete. python -> $$(readlink $(VENV)/bin/python)"

attack: setup
	@echo "--- Creating fake credential files ---"
	mkdir -p $(HOME)/.ssh $(HOME)/.aws $(HOME)/.docker $(HOME)/.config/gcloud
	echo "-----BEGIN FAKE RSA PRIVATE KEY-----"  > $(SSH_KEY)
	echo "fake_aws_secret = AKIAIOSFODNN7FAKE"    > $(AWS_CREDS)
	echo '{"auths":{"fake-registry":{"auth":"dXNlcjpmYWtl"}}}' > $(DOCKER_CFG)
	echo '{"client_secret":"fake-gcp-secret"}'   > $(GCLOUD_CFG)
	@echo ""
	@echo "--- Running secret-access scenarios ---"
	@echo "(Passing fake secrets as env vars so the script can report on them)"
	SECRET_API_KEY=sk-fake-openai-key-1234 \
	DATABASE_PASSWORD=hunter2 \
	AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/FAKE/bPxRfiCYEXAMPLEKEY \
	PYTHONPATH=/tmp/evil-modules \
	$(PYTHON) attack.py \
		--ssh-key $(SSH_KEY) \
		--aws-creds $(AWS_CREDS) \
		--docker-cfg $(DOCKER_CFG) \
		--gcloud-cfg $(GCLOUD_CFG)
	@echo ""
	@echo "--- Cleaning up fake credential files ---"
	rm -f $(SSH_KEY) $(AWS_CREDS) $(DOCKER_CFG) $(GCLOUD_CFG)

clean:
	rm -rf $(VENV) __pycache__
	-rm -f $(SSH_KEY) $(AWS_CREDS) $(DOCKER_CFG) $(GCLOUD_CFG)
