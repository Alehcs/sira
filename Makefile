REPO ?= https://github.com/Alehcs/sira
FREEZE ?= 1024

.PHONY: reproduce physics docker

# recompute every number in CLAIMS.md from public files, with no API keys and no paid calls
reproduce: ledger
	uv sync --frozen --group evidence
	uv run pytest -q
	uv run sira verify --ledger ledger
	uv run sira evidence --until $(FREEZE) --check

# also rerun the distance and lens-or-supernova headlines, after downloading the public snapshot from ALeRCE
physics:
	uv run sira snapshot
	uv run sira evidence --physics --until $(FREEZE)

ledger:
	git clone --quiet --depth 1 --branch ledger $(REPO) ledger

docker:
	docker build --build-arg CODE=$$(git rev-parse HEAD) -t sira .
	docker run --rm sira
