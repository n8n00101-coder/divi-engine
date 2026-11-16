"""gpupool — a pool of free-GPU compute providers for the voice engine.

One adapter interface (submit lines -> poll -> download takes), a
scheduler that splits a job's sentences across the providers that are
alive, and automatic failover: when a provider errors, times out or
hits its quota, its unfinished lines move to the next alive provider
(Actions CPU runners are the final fallback leg). Quality rules are
NOT touched here — every provider runs the engine's own batch mode
with the locked voice and the locked ship gates. See GPUPOOL.md.
"""
