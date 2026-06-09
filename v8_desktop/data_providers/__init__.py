"""Normalized data providers for the stock advisor.

Provider modules should return plain dicts/DataFrames using the same field names
as engine/ expects.  They are intentionally kept outside engine/ so the V9
scoring core stays frozen while data quality improves.
"""
