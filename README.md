ASPathInference
===============

Introduction
------------------

This is a tool for inferring the Internet AS level paths from any source AS to any destination prefixes. 
Please refer to http://rio.ecs.umass.edu/~jqiu/aspath_tech.pdf for further information.


Running with Docker
-------------------

We provide prebuilt Docker images for some dates on this repository. 
You can use the `docker-compose.yml` file to get started with a basic configuration: 10 instances of the inference 
software and a reverse web proxy to load balance the requests.

Install Docker and Docker Compose and use the following command to start the stack. 
The containers need a few seconds to start before they can accept requests. 

```shell
docker compose up -d
```

Test once it is running

```shell
curl "http://localhost:61002/infer?algorithm_=LUF&prefix_=51.91.110.66&src_=2611&use_known_=NO_FEEDBACK"
```

License
------------------

ASPathInference is released under the GNU General Public License. A copy of the license is included in the distribution. It is also available from GNU. 


Docker image
-------------------

Build the docker image for a specific time for BGP data with the BGP_DATE argument.

```shell
docker build -t as-inference:2021-12-01 --build-arg="BGP_DATE=2021-12-01-0800" --no-cache --progress=plain . 2>&1 | tee build.log
```

aspathinference script
-------------------

This script is used to request the AS paths for Tor circuits sampled by TorPS. The script also assigns AS and IP 
addresses to each TorPS client at random. The seed used for client assignment can be changed via the CLI. This client
uses caching to avoid re-requesting the same path twice while maintaining a constant load on the server. The load can be
defined via the CLI based on the number of instances running on the server. It corresponds to the number of requests the 
server can handle simultaneously. The usage of this script is as follows:

```shell
python aspathinference.py pathsim.txt client_location/weighted-ases.json pyasn.dat 10000 --ip=server-hoastname --cache_file=cache.pkl --load=30 --output=asinfer.txt
```
Where `pathsim.txt` is the output of TorPS containing each sampled circuit with the client number, timestamp, guard, 
middle, exit, and destination IPs as follows:

```text
Sample  Timestamp       Guard IP        Middle IP       Exit IP         Destination IP
0       1683072000      51.159.136.111  172.241.140.247 109.70.100.75   185.15.59.224
1       1683072000      116.202.169.30  108.18.149.65   104.244.79.50   185.15.59.224
2       1683072000      89.58.60.208    65.21.251.26    185.220.101.12  185.15.59.224
3       1683072000      185.241.208.179 185.100.86.245  185.220.101.182 185.15.59.224
4       1683072000      37.120.176.112  23.238.170.198  199.249.230.118 185.15.59.224
5       1683072000      144.76.159.218  51.158.231.136  162.247.74.217  185.15.59.224
6       1683072000      87.247.142.87   172.106.200.150 23.151.232.6    185.15.59.224
7       1683072000      54.36.205.38    104.152.209.217 185.220.101.70  185.15.59.224
.....
```

`weighted-ases.json` is the file containing the top client ASes for each of the most popular countries among Tor users, 
with each country assigned a weight corresponding to its prevalence among Tor users. Here is a snippet of such a file:

```json
{
  "RU": {
    "weight": 20.23,
    "ases": [
      "12389",
      "20485",
      "3216",
      "20764",
      "31133",
      "8359",
      "28917",
      "29076",
      "31500",
      "3267"
    ]
  },
  "US": {
    "weight": 18.04,
    "ases": [
      "3356",
      "174",
      "2914",
      "6453",
      "6939",
      "3491",
      "6461",
      "3549",
      "209",
      "701"
    ]
  }
}
```
The most popular countries among Tor users can be obtained on [Tor metric](https://metrics.torproject.org/userstats-relay-table.html)
and the top ASes of each country can be obtained by requesting the [CAIDA API](https://api.asrank.caida.org/v2/graphiql).

<details>
  <summary>CAIDA request example</summary>

```text
{
  asns(dateStart: "20230601", dateEnd: "20230601", sort: "+rank", first: 5000) {
    edges {
      node {
        date
        asn
        rank
        country {
          iso
          name
        }
      }
    }
  }
}
```
</details>

Pre-built `weighted-ases` files for Tor EOL exclusions can be found in the `client_location/` directory.

`pyasn.dat` is the mapping between AS number and IPs.
To get it for a specific date, download the data from e.g. [https://archive.routeviews.org/bgpdata/2023.05/RIBS/rib.20230517.0000.bz2](https://archive.routeviews.org/bgpdata/2023.05/RIBS/rib.20230517.0000.bz2).
Then, use pyasn to convert it:
```bash
pyasn_util_convert.py --single rib.20230517.0000.bz2 pyasn.20230517.0000.dat
```

The fourth parameter of is the number of client contained in the TorPS simulation.

<details>
  <summary>Original README</summary>

Software requirement
------------------

This tool is running on linux or other unix like systems. The following softwares are required:

 * gcc
 * python 2.4 and the development library
 * perl and LWP::Simple library



Installation
------------------

This software is a combination of binary executive codes and scripts. Sub-directory src contains c++ codes that facilitate storing and retrieving AS paths in known BGP routing tables; Sub-directory script contains scripts for path inferences service and automatic process. To use the software, please follow the three steps:

1) compile binary codes. Issue 

   ```shell
   make
   ```

  to compile all necessary binary codes.

2) collect and process data and start path inference service. Issue

   ```shell
   make run
   ```
 
   to start the scripts. The script first automatically downloads the most recent BGP tables from routeviews and RIPE RIS data repositories into subdirectory "tables", and store the AS paths in a easily accessible way. Then the scripts infer AS relationships and other information. Before the information is completely inferred, the results are stored in a temporary sub-directory "tmp". After the completion of the inference process, sub-directory "tmp" will be renamed as "data". The process could take hours. Finally, the inference service script "pathInferenceServer.py" will start on the information stored in sub-directory "data".

3) AS path inference.

   The inference server will listen on TCP port 61002 based on http protocol. The service can be queried with the library routines specified in aspathinfer.pl or aspathinfer.py. Sub-directory "example" contains two simple query examples.

   If you find the path information is outdated, please repeat step 2) to retrieve the most up-to-date tables.




Possible compiling issues
------------------

In src/PYGetSurePath.cpp, the #include header file Python.h is pointing to $INCLUDE/python2.4/Python.h. On your system, if the header file is in other position, please change the #include directory accordingly.

</details>