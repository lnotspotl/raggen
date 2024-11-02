#!/usr/bin/env python3

import argparse
import os
import tqdm
from collections import namedtuple

import pandas as pd

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
    memtrace = MemoryTrace(trace_file, cache_line_size=cache_config["cache_line_size"], max_look_ahead=num_cache_accesses)

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
    # Find all available traces
    trace_folders = [
        item for item in os.listdir(args.input_folder) if os.path.isdir(os.path.join(args.input_folder, item))
    ]
    traces = list()
    Trace = namedtuple("Trace", ["name", "path"])
    for trace_folder in trace_folders:
        folder_path = os.path.join(args.input_folder, trace_folder)
        trace = "llc_access_trace.csv"
        trace_path = os.path.join(folder_path, trace)
        assert os.path.isfile(trace_path), f"llc_access_trace.csv does not exist in {folder_path}"
        traces.append(Trace(name=f"{trace_folder}/{trace}", path=trace_path))

    # Just one cache config - might want to evaluate MPKI for multiple cache configurations
    cache_config = {"cache_line_size": 64, "capacity": 2**21, "associativity": 16}

    stats = list()
    TraceStatistics = namedtuple("TraceStatistics", ["trace", "mpki", "hit_rate"])

    for trace in traces:
        print(f"Evaluating MPKI for {trace.name}")
        mpki, hit_rate = evaluate_trace(trace.path, cache_config)
        stats.append(TraceStatistics(trace.name, mpki, hit_rate))
        print(f"{trace.name} | MPKI: {mpki} | HIT RATE: {hit_rate}")
        print("-" * 80)

    # Turn into a pandas frame and then to markdown
    df = pd.DataFrame(stats)
    result_file = os.path.join(args.output_folder, "mpki.csv")
    df.to_csv(result_file, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_folder", type=str, default="inputs")
    parser.add_argument("--output_folder", type=str, default="outputs")
    args = parser.parse_args()

    main(args)
