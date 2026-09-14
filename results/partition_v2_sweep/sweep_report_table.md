# Partition V2 Sweep Summary

| Rank | Run | Reduction vs Generic | Reduction vs V1 | Weight Balance | Instance Balance | Crossing Proxy |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `arch0p2_wb0p9` | 67.2% | 55.1% | 0.940 | 0.989 | 6219 |
| 2 | `arch0p1_wb0p9` | 65.5% | 52.7% | 0.922 | 0.987 | 6543 |
| 3 | `arch0p2_wb0p95` | 61.8% | 47.7% | 0.985 | 0.893 | 7245 |
| 4 | `arch0p1_wb0p95` | 60.6% | 46.1% | 0.982 | 0.880 | 7457 |
| 5 | `arch0p8_wb0p9` | 57.8% | 42.2% | 0.904 | 0.970 | 8000 |

Default run `arch0p4_wb0p95` is a conservative main setting: it keeps proxy-weight balance above 0.95 while still strongly reducing crossing proxy.
