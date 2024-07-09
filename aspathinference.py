import json
import asyncio
import random
import ipaddress
import itertools
import pickle
import os
import pyasn
import fire
import aiohttp

from functools import lru_cache
from async_lru import alru_cache
from collections.abc import Iterator
from time import perf_counter

SampledTorCircuit = tuple[int, int, str, str, str, str]
HopInfo = tuple[str, int]
TorCircuit = tuple[int, int, HopInfo, HopInfo, HopInfo, HopInfo]
CircuitASPath = tuple[int, int, str, str, str, str]

asns = None
url = ''
cache = {}
lock = asyncio.Lock()
miss_n = 0
n_error = 0


def batch(iterable, n=1):
    global miss_n
    current_size = n
    miss_n = n * 4
    speed = None
    while True:
        miss_rate = miss_n / (current_size * 4)
        hit_rate = 1 - miss_rate
        miss_rate = max(0.0001, miss_rate)  # Avoid division by zero
        current_size = int(n / miss_rate)
        print(
            f"Hit rate: {hit_rate * 100:.2f}%, Batch size {current_size}, {n_error=}{f', Delta time: {speed:.2f} line(s)/s' if speed is not None else ''}")
        miss_n = 0
        chunk = list(itertools.islice(iterable, current_size))
        if not chunk:
            return
        current_size = len(chunk)
        t_start = perf_counter()
        yield chunk
        speed = current_size / (perf_counter() - t_start)


def load_tor_circuits(tor_circuit_file: str) -> Iterator[SampledTorCircuit]:
    """
    Load Tor circuits from a file.
    :param tor_circuit_file: Path to the Tor circuits file
    :return: List of Tor circuits samples
    """
    with open(tor_circuit_file, "r") as f:
        _ = f.readline()  # Skip the header
        for line in f:
            sample_n, timestamp, *hops = line.strip().split()
            yield int(sample_n), int(timestamp), *hops


def load_ases(ases_file: str) -> dict[dict]:
    """
    Load ASes from a file.
    :param ases_file: Path to the ASes file
    :return: ASes dictionary by country
    """
    with open(ases_file, "r") as f:
        return json.load(f)


def select_clients_asn(ases: dict[dict], n: int) -> list[int]:
    """
    Select n clients AS numbers.
    :param ases: ASes dictionary
    :param n: Number of clients to select
    :return: List of clients AS numbers
    """
    random.seed(42)
    countries = random.choices(list(ases.keys()), k=n, weights=[v["weight"] for v in ases.values()])
    ases = [random.choice(ases[country]["ases"]) for country in countries]
    return ases


@lru_cache
def as2ip(asn: int) -> str:
    """
    Convert an AS number to an IP address.
    :param asn: AS number
    :return: IP address
    """
    prefixes = asns.get_as_prefixes(asn)
    if prefixes is None:
        return
    ip = next(ipaddress.ip_network(sorted(list(prefixes))[0]).hosts())
    return str(ip)


def ases_to_ips(ases_list: list[int]) -> list[HopInfo]:
    """
    Convert a list of AS numbers to a list of IP addresses at random.
    :param ases_list: List of AS numbers
    :return: List of IP addresses
    """
    ips = []
    for asn in ases_list:
        ips.append(as2ip(asn))
    return ips


def generate_as_and_ip(n: int, ases: dict[dict]) -> list[HopInfo]:
    """
    Generate n AS numbers and IP addresses.
    :param n: Number of AS numbers and IP addresses to generate
    :param ases: ASes dictionary
    :return: List of AS numbers and IP addresses
    """
    ases = select_clients_asn(ases, n)
    ips = ases_to_ips(ases)
    return list(zip(ips, ases))


def map_hop_info(cicuit: SampledTorCircuit, client_ases: list[HopInfo]) -> TorCircuit:
    """
    Map a Tor circuit to a list of AS numbers and IP addresses.
    :param cicuit: Tor circuit
    :param client_ases: List of clients AS numbers
    :return: List of AS numbers and IP addresses
    """
    sample_n, timestamp, guard_ip, _, exit_ip, destination_ip = cicuit
    client_ip, client_as = client_ases[sample_n]
    guard_as = asn_from_ip(guard_ip)
    exit_as = asn_from_ip(exit_ip)
    destination_as = asn_from_ip(destination_ip)
    return sample_n, timestamp, (client_ip, client_as), (guard_ip, guard_as), (exit_ip, exit_as), (
    destination_ip, destination_as)


@lru_cache
def asn_from_ip(ip: str) -> int:
    """
    Get the AS number from an IP address.
    :param ip: IP address
    :return: AS number
    """
    return asns.lookup(ip)[0]


# http://127.0.0.1:61002/infer?algorithm_=algorithm&prefix_=prefix&src_=src&use_known_=use_known
@alru_cache(maxsize=300000)
async def infer_path(src: int, dst: str, algorithm: str = "LUF", use_known: str = 'use_known') -> str | None:
    """
    Infer a path between two IP addresses.
    :param src: Source AS number
    :param dst: Destination IP address
    :param url: Inference server URL
    :param algorithm: Inference algorithm
    :param use_known: Use known paths
    :return: Inferred path
    """
    global miss_n
    global n_error

    if (src, dst) in cache and (cache[(src, dst)] is not None or not ignore_none):
        async with lock:
            return cache[(src, dst)]

    async with lock:
        miss_n += 1

    params = {
        "algorithm_": algorithm,
        "prefix_": dst,
        "src_": str(src),
        "use_known_": use_known
    }

    async with aiohttp.ClientSession() as client:
        retry = 0
        backoff = 3
        max_try = 4
        while retry < max_try:
            try:
                async with client.get(url, params=params, verify_ssl=False) as res:
                    if res.status != 200:
                        retry += 1
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    response = await res.text()
                    break
            except:
                # print("Connection error:", url, "retrying...", retry)
                retry += 1
                await asyncio.sleep(backoff)
                backoff *= 2
        if retry == max_try:
            async with lock:
                n_error += 1
    try:
        path = response.split('\n')[1].strip().split()[2].replace("+", "-").replace("=", "-").replace("*", "-").replace(
            "*", "-")
        result = path
    except:
        result = None

    async with lock:
        cache[(src, dst)] = result
    return result


async def map_infer_path(circuit: TorCircuit) -> CircuitASPath:
    """
    Infer a path between client and guard, exit and destination.
    :param circuit: Tor circuit
    :return: Inferred paths between client and guard, exit and destination
    """
    n_samples, timestamp, (client_ip, client_as), (guard_ip, guard_as), (exit_ip, exit_as), (
    destination_ip, destination_as) = circuit
    c2g = await infer_path(client_as, guard_ip)
    g2c = await infer_path(guard_as, client_ip)
    e2d = await infer_path(exit_as, destination_ip)
    d2e = await infer_path(destination_as, exit_ip)
    # print(n_samples, timestamp, c2g, g2c, e2d, d2e)
    return n_samples, timestamp, c2g, g2c, e2d, d2e


async def infer_all_paths(circuits: list[TorCircuit]) -> list[CircuitASPath]:
    """
    Infer all paths in a list of circuits
    :param circuits: List of circuits
    :return: List of inferred paths between client and guard, exit and destination
    """
    results = [map_infer_path(circuit) for circuit in circuits]
    results = await asyncio.gather(*results)
    return results


def as_path_infer(
        tor_circuit_file: str,
        ases_file: str,
        pyasn_file: str,
        n_samples: int,
        port: int = 61002,
        ip: str = "127.0.0.1",
        output: str | None = None,
        cache_file: str | None = None,
        load: int = 10,
        ignore_cached_none: bool = False) -> None:
    """
    Compute path compromition CDF for a given Tor path file.
    :param tor_circuit_file: Path to the Tor circuits file
    :param ases_file: Path to the ASes file
    :param pyasn_file: Path to the pyasn file
    :param n_samples: Number of samples
    :param port: Inference server port
    :param ip: Inference server IP address
    :param output: Output file
    :param cache_file: Cache file
    :param load: load on the inference server
    :param ignore_cached_none: Ignore cached None results
    :return: None
    """
    global url
    url = f"http://{ip}:{port}/infer"

    global ignore_none
    ignore_none = ignore_cached_none

    global asns
    asns = pyasn.pyasn(pyasn_file)

    print(output)
    if output is None:
        output = "aspathinference.out"

    global cache
    if cache_file is None:
        cache_file = f"aspathinference_cache.pkl"

    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            cache = pickle.load(f)

    print("Cache size:", len(cache))

    with open(output, "w") as out:
        out.write("sample_n timestamp c2g g2c e2d d2e\n")

        client_ases = load_ases(ases_file)
        client_ases = generate_as_and_ip(n_samples, client_ases)
        for circuits in batch(load_tor_circuits(tor_circuit_file), load):
            circuits = [map_hop_info(circuit, client_ases) for circuit in circuits]
            results = asyncio.run(infer_all_paths(circuits))
            results = [f"{n_samples} {timestamp} {c2g} {g2c} {e2d} {d2e}\n" for n_samples, timestamp, c2g, g2c, e2d, d2e
                       in results]
            out.writelines(results)
            with open(cache_file, "wb") as f:
                pickle.dump(cache, f)


if __name__ == '__main__':
    fire.Fire(as_path_infer)
