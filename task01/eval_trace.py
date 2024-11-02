#!/usr/bin/env python3

import argparse

import tqdm

from cache_replacement.policy_learning.cache.cache import Cache
from cache_replacement.policy_learning.cache.eviction_policy import BeladyScorer, GreedyEvictionPolicy
from cache_replacement.policy_learning.cache.memtrace import MemoryTrace


class CacheObserver:
    def __init__(self):
        self.cache_accesses = 0
        self.cache_misses = 0
        self.num_instructions = 1_000_000_000  # champsim simulates this number of instructions and than crashes

    def __call__(self, cache_access, eviction_decision):
        is_miss = eviction_decision.evict
        self.cache_misses += int(is_miss)
        self.cache_accesses += 1

    def compute_mpki(self):
        return (self.cache_misses / self.num_instructions) * 1000

    def compute_hit_rate(self):
        return 1.0 - self.cache_misses / self.cache_accesses


def evaluate_trace(trace_file: str, cache_config: dict) -> float:
    # Determine number of cache accesses
    num_cache_accesses = sum(1 for _ in open(trace_file))

    # Load memory trace into memory
    # Make sure the trace_file is the 'llm_access_trace.csv' file as generated by champsim
    memtrace = MemoryTrace(
        trace_file, cache_line_size=cache_config["cache_line_size"], max_look_ahead=num_cache_accesses
    )

    # Initialize Belady's optimal eviction policy
    belady_scorer = BeladyScorer(memtrace)
    belady_policy = GreedyEvictionPolicy(belady_scorer)

    # Initialize cache
    cache = Cache.from_config(cache_config, eviction_policy=belady_policy)

    # Initialize observer
    cache_observer = CacheObserver()

    # Calculate MPKI and hit rate
    with memtrace:
        for read_idx in tqdm.tqdm(range(num_cache_accesses), desc=f"trace: {trace_file}"):
            assert not memtrace.done()
            pc, address = memtrace.next()
            cache.read(pc, address, observers=[cache_observer])
    mpki = cache_observer.compute_mpki()
    hit_rate = cache_observer.compute_hit_rate()
    return mpki, hit_rate


def main(args: argparse.Namespace):
    cache_config = {"cache_line_size": 64, "capacity": 2**21, "associativity": 16}
    mpki, hit_rate = evaluate_trace(args.trace_file, cache_config)

    with open(args.output_file, "w") as file:
        file.write(f"MPKI {mpki}\n")
        file.write(f"HIT_RATE {hit_rate}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace_file", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    args = parser.parse_args()

    main(args)
