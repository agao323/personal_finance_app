"""Deterministic analyses over the existing services.

Pure functions that take a session and `today` and compute what a question needs: period
comparisons, trends, recurring charges, cashflow, attribution. None of them know a model
exists; the Insights panel and the advisor's tools both call them. See
docs/ADVISOR.md#analyses.
"""
