.PHONY: demo-tape deploy-backend deploy-frontend setup generate train-prediction train-anomaly survival profile explain scenarios counterfactuals conformal stress-grid test cedar-test train-all run-all clean

VENV_PY ?= python3

setup:
	$(VENV_PY) -m venv .venv
	.venv/bin/pip install -q -r training/requirements.txt

generate:
	$(VENV_PY) training/generate_data.py

train-prediction:
	$(VENV_PY) training/train_prediction_models.py

train-anomaly:
	$(VENV_PY) training/train_anomaly_models.py

survival:
	$(VENV_PY) training/survival_analysis.py

profile:
	$(VENV_PY) training/profile_data.py

explain:
	$(VENV_PY) training/explainability.py

scenarios:
	$(VENV_PY) training/scenario_segments.py

counterfactuals:
	$(VENV_PY) training/counterfactuals.py

conformal:
	$(VENV_PY) training/conformal_intervals.py

stress-grid:
	$(VENV_PY) scripts/precompute_stress_grid.py

demo-tape:
	$(VENV_PY) scripts/build_demo_tape.py

deploy-backend:
	cd infra && sam build && sam deploy

deploy-frontend:
	scripts/deploy_frontend.sh

test:
	$(VENV_PY) -m pytest tests/ -v

cedar-test:
	node backend/cedar_gate/test_policies.mjs

# Full pipeline, in dependency order: data -> core models -> everything
# that reads those trained models. Roughly 60-90 seconds end to end at
# the default 5,000-loan demo scale.
train-all: generate train-prediction train-anomaly
	$(MAKE) survival
	$(MAKE) profile
	$(MAKE) explain
	$(MAKE) scenarios
	$(MAKE) counterfactuals
	$(MAKE) conformal
	$(MAKE) stress-grid

run-all: train-all test cedar-test

clean:
	rm -rf data/raw .venv
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
