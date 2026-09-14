# Publication Figure Summary

| Setting | Run | Reduction vs Generic | Reduction vs V1 | Weight Balance | Instance Balance | Crossing Proxy |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Best reduction | `arch0p2_wb0p9` | 67.2% | 55.1% | 0.940 | 0.989 | 6219 |
| Default | `arch0p4_wb0p95` | 54.7% | 38.0% | 0.959 | 0.906 | 8585 |
| Strict balance best | `arch0p8_wb0p98` | 42.8% | 21.8% | 0.980 | 0.842 | 10827 |

The default setting is used as the conservative main result because it maintains proxy-weight balance above 0.95 while substantially reducing crossing proxy.
