# CampusShield Core Experimental Analysis

Congestion source: `congestion_comparison_20261024T060539Z.csv`
Failure source: `failure_recovery_20261024T070725Z.csv`
OSPF source: `ospf_optimization_20261025T154113Z.csv`

The congestion analysis uses 10 matched repetitions across 3 scenario(s). Values report sample standard deviation and two-sided 95% Student-t confidence intervals.

## Congestion comparison

| Metric | Basic static | Tuned static | Adaptive ANRE |
|---|---:|---:|---:|
| Emergency throughput | 19.410 +/- 0.023 Mbps [95% CI 19.393 to 19.427] | 53.309 +/- 0.140 Mbps [95% CI 53.209 to 53.409] | 45.416 +/- 3.015 Mbps [95% CI 43.259 to 47.572] |
| Emergency UDP loss | 68.572 +/- 0.040 percent [95% CI 68.544 to 68.601] | 11.289 +/- 0.182 percent [95% CI 11.159 to 11.420] | 25.656 +/- 5.015 percent [95% CI 22.068 to 29.243] |
| Emergency UDP jitter | 0.094 +/- 0.044 ms [95% CI 0.062 to 0.125] | 0.061 +/- 0.008 ms [95% CI 0.055 to 0.066] | 0.058 +/- 0.015 ms [95% CI 0.047 to 0.069] |
| EF probe RTT | 8.547 +/- 0.622 ms [95% CI 8.101 to 8.992] | 10.172 +/- 0.112 ms [95% CI 10.092 to 10.252] | 9.713 +/- 0.678 ms [95% CI 9.227 to 10.198] |
| Congestion NHS | 42.033 +/- 0.598 score [95% CI 41.605 to 42.460] | 56.724 +/- 1.001 score [95% CI 56.008 to 57.440] | 53.381 +/- 1.892 score [95% CI 52.027 to 54.734] |
| Bulk throughput | 28.659 +/- 0.036 Mbps [95% CI 28.633 to 28.685] | 9.545 +/- 0.016 Mbps [95% CI 9.534 to 9.557] | 13.302 +/- 1.665 Mbps [95% CI 12.111 to 14.492] |
| Academic throughput | 47.730 +/- 0.068 Mbps [95% CI 47.681 to 47.778] | 33.423 +/- 0.049 Mbps [95% CI 33.388 to 33.458] | 37.177 +/- 1.687 Mbps [95% CI 35.970 to 38.383] |
| Recovery NHS | 87.737 +/- 0.302 score [95% CI 87.521 to 87.953] | 87.806 +/- 0.289 score [95% CI 87.599 to 88.013] | 87.860 +/- 0.244 score [95% CI 87.685 to 88.035] |
| NHS recovery change | 45.704 +/- 0.773 score [95% CI 45.152 to 46.257] | 31.082 +/- 1.041 score [95% CI 30.338 to 31.826] | 34.480 +/- 1.799 score [95% CI 33.193 to 35.766] |
| Emergency queue drops | 75135.900 +/- 1753.632 packets [95% CI 73881.515 to 76390.285] | 3526.200 +/- 231.704 packets [95% CI 3360.461 to 3691.939] | 21187.500 +/- 7343.636 packets [95% CI 15934.544 to 26440.456] |
| Peak emergency backlog | 1490000.000 +/- 0.000 bytes [95% CI 1490000.000 to 1490000.000] | 1490000.000 +/- 0.000 bytes [95% CI 1490000.000 to 1490000.000] | 1490000.000 +/- 0.000 bytes [95% CI 1490000.000 to 1490000.000] |

## Adaptive comparisons

| Metric | ANRE vs basic static | ANRE vs tuned static |
|---|---:|---:|
| Emergency throughput | +133.98% | -14.81% |
| Emergency UDP loss | -62.59% | +127.25% |
| Emergency UDP jitter | -37.99% | -4.61% |
| EF probe RTT | +13.64% | -4.51% |
| Congestion NHS | +27.00% | -5.89% |
| Bulk throughput | -53.59% | +39.35% |
| Academic throughput | -22.11% | +11.23% |
| Recovery NHS | +0.14% | +0.06% |
| NHS recovery change | -24.56% | +10.93% |
| Emergency queue drops | -71.80% | +500.86% |
| Peak emergency backlog | +0.00% | +0.00% |

## Physical link failure

| Metric | Mean, SD and 95% CI | Range |
|---|---:|---:|
| Packets lost | 17.000 +/- 0.471 packets [95% CI 16.663 to 17.337] | 16.000 to 18.000 packets |
| Service interruption | 1887.547 +/- 48.815 ms [95% CI 1852.629 to 1922.465] | 1778.565 to 1984.314 ms |
| Backup route convergence | 1892.073 +/- 37.598 ms [95% CI 1865.179 to 1918.967] | 1825.413 to 1948.264 ms |
| Primary route restoration | 10479.833 +/- 18.020 ms [95% CI 10466.943 to 10492.723] | 10460.488 to 10524.204 ms |

## OSPF optimization

| Metric | Default OSPF | Tuned OSPF |
|---|---:|---:|
| Packets lost | 313.000 +/- 0.667 packets [95% CI 312.523 to 313.477] | 24.800 +/- 0.422 packets [95% CI 24.498 to 25.102] |
| Service interruption | 32816.542 +/- 61.007 ms [95% CI 32772.904 to 32860.180] | 2697.388 +/- 46.550 ms [95% CI 2664.091 to 2730.685] |
| Backup route convergence | 32615.573 +/- 79.824 ms [95% CI 32558.474 to 32672.671] | 2521.234 +/- 53.082 ms [95% CI 2483.264 to 2559.204] |
| Primary route restoration | 9316.351 +/- 112.537 ms [95% CI 9235.852 to 9396.850] | 337.067 +/- 18.930 ms [95% CI 323.526 to 350.608] |

## Hypothesis evaluation

| Hypothesis | Outcome | Evidence rule |
|---|---|---|
| H1 - RTT | Not supported | Mean EF-marked probe RTT with ANRE is lower than basic static QoS. |
| H2 - Packet loss | Supported | Emergency UDP loss with ANRE is lower than basic static QoS. |
| H3 - Jitter | Supported | Emergency UDP jitter with ANRE is lower than basic static QoS. |
| H4 - Network recovery | Supported | ANRE mean NHS increases from congestion to the recovery phase. |
| H5 - Bulk trade-off | Supported | ANRE increases emergency throughput while restricting bulk traffic. |
| H6 - Routing recovery | Supported | Every failure repetition uses the backup route and restores the primary. |
| H7 - Tuned OSPF | Supported | Tuned mean interruption 2697.388 ms versus default 32816.542 ms (+91.78% improvement). |

## Interpretation

The three-arm design compares ANRE with both the original basic static allocation and a stronger fixed emergency-priority allocation. The healthy, congestion, and recovery phases also expose controller response and recovery behavior instead of measuring only a constant overload. Hypotheses are reported directly from the measured directions above; confidence intervals show the uncertainty between repetitions.
