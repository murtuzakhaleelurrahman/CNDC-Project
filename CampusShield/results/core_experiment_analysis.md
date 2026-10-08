# CampusShield Core Experimental Analysis

Congestion source: `congestion_comparison_20261008T151712Z.csv`
Failure source: `failure_recovery_20261008T152441Z.csv`

This analysis uses three paired ANRE OFF/ON repetitions and three physical-link-failure repetitions. Values are descriptive means and sample standard deviations; n=3 is too small for strong inferential claims.

## Congestion comparison

| Metric | ANRE OFF mean +/- SD | ANRE ON mean +/- SD | Change |
|---|---:|---:|---:|
| Emergency throughput | 19.101 +/- 0.088 Mbps | 35.913 +/- 0.614 Mbps | +88.01% |
| Emergency UDP loss | 69.250 +/- 0.134 percent | 41.677 +/- 1.044 percent | -39.82% |
| Emergency UDP jitter | 0.360 +/- 0.089 ms | 0.760 +/- 0.984 ms | +111.20% |
| Probe RTT | 11.220 +/- 0.127 ms | 11.364 +/- 0.069 ms | +1.28% |
| Network Health Score | 66.824 +/- 0.308 score | 66.263 +/- 0.096 score | -0.84% |
| Bulk throughput | 28.010 +/- 0.144 Mbps | 15.259 +/- 0.577 Mbps | -45.52% |
| Academic throughput | 46.398 +/- 0.311 Mbps | 42.158 +/- 0.551 Mbps | -9.14% |

Mean ANRE response time: 3.043 +/- 1.064 seconds.

## Physical link failure

| Metric | Mean +/- SD | Range |
|---|---:|---:|
| Packets lost | 13.667 +/- 3.215 packets | 10.000 to 16.000 packets |
| Service interruption | 1537.395 +/- 329.324 ms | 1161.066 to 1772.851 ms |
| Backup route convergence | 1484.930 +/- 318.667 ms | 1146.028 to 1778.509 ms |
| Primary route restoration | 10653.475 +/- 476.927 ms | 10274.418 to 11188.975 ms |

## Hypothesis evaluation

| Hypothesis | Outcome | Evidence rule |
|---|---|---|
| H1 - RTT | Not supported | Mean probe RTT with ANRE is lower than without ANRE. |
| H2 - Packet loss | Supported | Emergency UDP loss with ANRE is lower than without ANRE. |
| H3 - Jitter | Not supported | Emergency UDP jitter with ANRE is lower than without ANRE. |
| H4 - Network recovery | Not supported | Mean NHS with ANRE is higher than without ANRE. |
| H5 - Bulk trade-off | Supported | ANRE reduces bulk throughput while increasing emergency throughput. |
| H6 - Routing recovery | Supported | Every repetition used the backup route and restored the primary route. |
| H7 - Tuned OSPF | Not tested | This remains a secondary experiment. |

## Interpretation

ANRE produced the intended service trade-off: it increased emergency throughput and reduced emergency packet loss by restricting bulk traffic. The repeated measurements did not show lower mean RTT, lower mean jitter, or a higher mean NHS, so those hypotheses are not supported by this dataset. All physical-failure repetitions automatically converged to R1-R3-R2 and later restored the direct R1-R2 route, supporting the routing-recovery claim.
