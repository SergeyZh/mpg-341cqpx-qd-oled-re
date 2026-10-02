REPO_ROOT := $(abspath ../..)
BUILD ?= $(REPO_ROOT)/out/u7005
PYTHON ?= $(REPO_ROOT)/.venv/bin/python
ENV := $(REPO_ROOT)/tools/u7005-env.sh
.PHONY: all verify test clean
all:
	$(ENV) cmake -S . -B $(BUILD) -G Ninja
	$(ENV) cmake --build $(BUILD)
	$(PYTHON) tools/package.py $(BUILD)/u7005-code.bin -o $(BUILD)
test:
	$(PYTHON) -m pytest -q tests
verify: all test
	$(PYTHON) tools/check_image.py $(BUILD)
clean:
	$(ENV) cmake --build $(BUILD) --target clean
