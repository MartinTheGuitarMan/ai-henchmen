"""Agents: workers that pick their own next steps.

A minion (see `minions/`) does one bounded step the caller chose, and code checks its output. An agent owns a
goal and chooses its own steps. Chain of command: human -> agents -> minions. Agents here may only propose: they
work in a throwaway clone and hand back a patch.
"""
