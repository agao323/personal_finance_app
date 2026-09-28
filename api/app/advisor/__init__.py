"""The AI advisor: tools, the loop, grounding, and the model seam.

Design: docs/ADVISOR.md. Constraints it answers to: docs/SECURITY.md#ai-agent. Nothing in
this package may write household data, fetch from the network (the model API excepted),
or compute a figure that a service under `app/services/` does not already compute.
"""
