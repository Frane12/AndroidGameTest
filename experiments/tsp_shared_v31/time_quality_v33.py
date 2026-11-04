#!/usr/bin/env python3
"""DRNAS TSP v3.3: full 30-second time-to-quality crossover, using verified v3.2 instrumentation.

Checkpoints from cold start; LKH event timestamps use its logged preprocessing
plus LKH trial time (approximate), whereas DRNAS uses wall-clock time.
"""
import time_quality_v32 as experiment

experiment.CHECKPOINTS = (2, 4, 6, 8, 10, 15, 20, 25, 30)

if __name__ == "__main__":
    experiment.main()
