# Benchmark: ULB credit-card fraud (real data)

Generated 2026-11-12 18:18 UTC by `scripts/benchmark_public_dataset.py`.

- Dataset: ULB Credit Card Fraud Detection (OpenML 1597) - 284,807 transactions, 492 fraud (0.173 %).
- Test split: 85,443 transactions, 148 fraud. The model is fitted on legitimate training rows only.
- A random detector would score average precision 0.0017.
- *FraudGuard features* are the live scorer's amount features (amount, amount-to-average, amount z-score). OpenML's copy omits the `Time` column, so the hour and day-of-week features are unavailable. The rules (velocity, impossible travel, per-account z-score) need account ids and locations, which this dataset lacks.

| Setting | Features | Average precision | ROC-AUC |
|---|---|---|---|
| FraudGuard features | 3 | 0.003 | 0.532 |
| Full features (V1-V28) | 29 | 0.152 | 0.944 |

## Analyst alert budget

If analysts can review a fixed share of traffic, the highest-scoring transactions are sent first:

| Setting | Review share | Alerts | Fraud caught | Precision | Recall |
|---|---|---|---|---|---|
| FraudGuard features | 0.10 % | 85 | 0 | 0.00 | 0.00 |
| FraudGuard features | 0.25 % | 214 | 0 | 0.00 | 0.00 |
| FraudGuard features | 0.50 % | 427 | 1 | 0.00 | 0.01 |
| FraudGuard features | 1.00 % | 854 | 3 | 0.00 | 0.02 |
| Full features (V1-V28) | 0.10 % | 85 | 30 | 0.35 | 0.20 |
| Full features (V1-V28) | 0.25 % | 214 | 43 | 0.20 | 0.29 |
| Full features (V1-V28) | 0.50 % | 427 | 64 | 0.15 | 0.43 |
| Full features (V1-V28) | 1.00 % | 854 | 87 | 0.10 | 0.59 |

## Reading the results

Amount on its own carries almost no signal in this dataset: with FraudGuard's amount-based features and a population-wide baseline the model scores ROC-AUC 0.53 (0.5 is chance) and average precision 0.003, against 0.0017 for a random detector. Fraudulent and legitimate amounts overlap heavily, so a single baseline for everyone cannot separate them. On the dataset's 28 behavioural features the same algorithm reaches ROC-AUC 0.94 and average precision 0.152. Two conclusions follow. First, per-account baselines matter: FraudGuard compares each amount with that account's own spending history, which this anonymised dataset cannot provide. Second, the ML score is rightly a supporting signal (weight 0.30) next to explainable rules that use account history and location; richer features (device, merchant category, behaviour) would improve detection more than a different model would.
